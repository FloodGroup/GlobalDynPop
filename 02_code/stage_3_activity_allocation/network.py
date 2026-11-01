"""People in transit on the road and rail network (component C6, model v2).

Trips between zones of the city (adaptive square zones, starting at 2 km, the gravity model of the city with the
country's kernels, all activity classes weighted by the country's time-use day) are assigned to
their fastest route on the Overture road and rail network (all-or-nothing assignment):

  roads   motorway ... unclassified, fixed class-specific speeds (ROAD_KMH; study-defined settings);
  rail    standard gauge, metro, light rail, tram, monorail (RAIL_KMH); entered and left at
          stations (Overture infrastructure: railway / subway stations and halts) within
          WALK_TO_STATION_M of the zone centre, walking plus a boarding penalty;
  access  every zone is joined to the ACCESS_K nearest road nodes (local streets at LOCAL_KMH,
          detour factor DETOUR) and to its stations.

The person-time of every edge (flow x travel time) is placed on the 100 m cells the edge crosses;
access, egress and travel within a zone are placed on the streets of the zone (all road classes,
by length; the baseline omits local person-time in zones with no streets). T is scaled to sum to the domain population,
like the other components. Without a usable network the v1 approximation is returned
(smoothed mean of the residents and the work destinations).
"""
from __future__ import annotations

import math
import time

import numpy as np
import pyproj
import shapely
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

# Fixed effective speeds in km/h. No time-varying congestion model is applied.
# Parameter values and sources: 06_docs/methods/stage_3_activity_allocation.md.
ROAD_KMH = {"motorway": 45.0, "trunk": 35.0, "primary": 28.0, "secondary": 24.0, "tertiary": 20.0, "unclassified": 18.0}
LOCAL_CLASSES = {"residential", "living_street", "service", "unknown", "track", "pedestrian", "footway", "path", "steps",
                 "cycleway", "bridleway", "sidewalk", "crosswalk", None}
RAIL_KMH = {"standard_gauge": 45.0, "narrow_gauge": 30.0, "subway": 35.0, "light_rail": 25.0, "monorail": 30.0, "tram": 15.0}
STATION_CLASSES = ("railway_station", "subway_station", "railway_halt")
LOCAL_KMH = 12.0
WALK_KMH = 4.5
DETOUR = 1.3
BOARD_MIN = 5.0
WALK_TO_STATION_M = 1200.0
SNAP_STATION_M = 250.0
ACCESS_K = 6
SAMPLE_M = 25.0
MAX_TRIP_H = 3.0


ZONE_MIN_CELLS = 20          # 2 km
ZONE_MAX = 1000


def zone_size(grid) -> int:
    """Zone side in 100 m cells: 2 km, larger for large domains (at most about ZONE_MAX zones).
    Trips within a zone travel on its local streets; 2 km zones keep the assignment of all 1,904
    cities within a few hours (the cost grows with zones x network nodes)."""
    k = ZONE_MIN_CELLS
    while (grid.nx / k) * (grid.ny / k) > ZONE_MAX:
        k += 5
    return k


def _project(geoms, grid):
    tr = pyproj.Transformer.from_crs(4326, grid.crs, always_xy=True)
    return shapely.transform(geoms, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))


def _samples(geoms, at0, at1, lengths, step=SAMPLE_M):
    """Points every `step` m along the pieces [at0, at1] of the lines -> (piece, x, y, length share)."""
    plen = lengths * (at1 - at0)
    n = np.maximum(1, np.ceil(plen / step).astype(np.int64))
    piece = np.repeat(np.arange(len(n)), n)
    k = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    frac = at0[piece] + (k + 0.5) / n[piece] * (at1 - at0)[piece]
    pts = shapely.line_interpolate_point(geoms[piece], frac, normalized=True)
    xy = shapely.get_coordinates(pts)
    return piece, xy[:, 0], xy[:, 1], 1.0 / n[piece]


def _cells(grid, x, y):
    r, c = grid.index(x, y)
    return np.where(r >= 0, r * grid.nx + c, -1)


def _street_length(seg, grid, chunk=200_000):
    """Metres of street (every road class) per 100 m cell; geometries decoded chunk by chunk."""
    import pyarrow.compute as pc
    street = np.zeros(grid.nx * grid.ny)
    roads = seg.filter(pc.equal(seg.column("subtype"), "road"))
    for a in range(0, roads.num_rows, chunk):
        g = shapely.from_wkb(roads.column("geometry").slice(a, chunk).to_numpy(zero_copy_only=False))
        g = g[shapely.get_type_id(g) == 1]
        if not len(g):
            continue
        g = _project(g, grid)
        L = shapely.length(g)
        lp, lx, ly, lw = _samples(g, np.zeros(len(g)), np.ones(len(g)), L, step=50.0)
        cell = _cells(grid, lx, ly)
        ok = cell >= 0
        street += np.bincount(cell[ok], weights=(L[lp] * lw)[ok], minlength=street.size)
        del g, L, lp, lx, ly, lw, cell
    return street.reshape(grid.shape)


def build_from_table(seg, sta, grid):
    """Routing graph of the major roads and the rail lines (pieces between consecutive connectors),
    sample points of the pieces, metres of street per cell and station positions. Works on the
    Arrow table without converting it to Python objects (memory: Tokyo has 2.4 million segments)."""
    import pandas as pd
    import pyarrow as pa
    import pyarrow.compute as pc
    cls = seg.column("class"); sub = seg.column("subtype")
    is_road = pc.and_(pc.equal(sub, "road"), pc.is_in(cls, pa.array(list(ROAD_KMH))))
    is_rail = pc.and_(pc.equal(sub, "rail"), pc.is_in(cls, pa.array(list(RAIL_KMH))))
    maj = seg.filter(pc.fill_null(pc.or_(is_road, is_rail), False))
    geoms = shapely.from_wkb(maj.column("geometry").to_numpy(zero_copy_only=False))
    ok = shapely.get_type_id(geoms) == 1
    maj = maj.filter(pa.array(ok)); geoms = _project(geoms[ok], grid)
    L = shapely.length(geoms)
    mcls = np.asarray(maj.column("class").to_pylist(), dtype=object)
    msub = np.asarray(maj.column("subtype").to_pylist(), dtype=object)
    speed = np.array([ROAD_KMH[c] if s == "road" else RAIL_KMH[c] for c, s in zip(mcls, msub)])
    rail = msub == "rail"
    con = maj.column("connectors").combine_chunks()
    seg_of = pc.list_parent_indices(con).to_numpy()
    flat = pc.list_flatten(con)
    cid = pc.struct_field(flat, "connector_id").to_numpy(zero_copy_only=False)
    at = np.clip(pc.struct_field(flat, "at").to_numpy(zero_copy_only=False).astype(float), 0.0, 1.0)
    o = np.lexsort((at, seg_of))
    seg_of, cid, at = seg_of[o], cid[o], at[o]
    codes = pd.factorize(pd.Series(cid, dtype=object))[0].astype(np.int64) if len(cid) else np.zeros(0, np.int64)
    del cid
    same = np.r_[seg_of[1:] == seg_of[:-1], False]
    a = np.nonzero(same)[0]
    p_seg, p_u, p_v, p_at0, p_at1 = seg_of[a], codes[a], codes[a + 1], at[a], at[a + 1]
    keep = (p_at1 > p_at0) & (p_u != p_v)
    p_seg, p_u, p_v, p_at0, p_at1 = p_seg[keep], p_u[keep], p_v[keep], p_at0[keep], p_at1[keep]
    p_len = L[p_seg] * (p_at1 - p_at0)
    p_time = p_len / (speed[p_seg] / 3.6) / 3600.0
    p_rail = rail[p_seg]
    n_nodes = int(codes.max()) + 1 if len(codes) else 0
    node_xy = np.full((n_nodes, 2), np.nan)
    if n_nodes:
        first = np.unique(codes, return_index=True)[1]
        pts = shapely.line_interpolate_point(geoms[seg_of[first]], at[first], normalized=True)
        node_xy[codes[first]] = shapely.get_coordinates(pts)
    rail_node = np.zeros(n_nodes, bool); road_node = np.zeros(n_nodes, bool)
    rail_node[p_u[p_rail]] = True; rail_node[p_v[p_rail]] = True
    road_node[p_u[~p_rail]] = True; road_node[p_v[~p_rail]] = True
    if len(p_seg):
        sp, sx, sy, sw = _samples(geoms[p_seg], p_at0, p_at1, L[p_seg])
        s_cell = _cells(grid, sx, sy)
        del sx, sy
    else:
        sp = s_cell = np.zeros(0, np.int64); sw = np.zeros(0)
    n_major = int(len(geoms))
    del geoms, maj, con, flat
    street = _street_length(seg, grid)
    st = np.zeros((0, 2))
    if sta is not None and sta.num_rows:
        sg = shapely.from_wkb(sta.column("geometry").to_numpy(zero_copy_only=False))
        st = shapely.get_coordinates(_project(shapely.centroid(sg), grid))
    return {"n_nodes": n_nodes, "node_xy": node_xy, "rail_node": rail_node, "road_node": road_node,
            "p_u": p_u, "p_v": p_v, "p_time": p_time, "p_len": p_len, "p_rail": p_rail,
            "s_piece": sp, "s_cell": s_cell, "s_w": sw, "street": street, "stations": st,
            "n_major_segments": n_major}


GRAPH_FORMAT = 1


def save_graph(path, G, meta: dict | None = None):
    """Write the routing graph of build_from_table to a compressed .npz (the road and rail network input of
    a city). Lossless: integer arrays are stored in 32 bits where they fit, the sample weights as sample
    counts per piece (s_w = 1 / n, s_piece = repeat(arange, n)), all other values unchanged."""
    import json
    from pathlib import Path
    path = Path(path)
    n_pieces = len(G["p_u"])
    s_n = np.bincount(np.asarray(G["s_piece"], np.int64), minlength=n_pieces).astype(np.int64)
    assert np.array_equal(np.repeat(np.arange(n_pieces), s_n), G["s_piece"]), "samples not ordered by piece"
    assert np.array_equal(1.0 / s_n[G["s_piece"]], G["s_w"]), "sample weights are not 1 / samples per piece"
    i32 = lambda a: np.asarray(a, np.int64).astype(np.int32) if (len(a) == 0 or int(np.max(np.abs(a))) < 2**31 - 1) else np.asarray(a, np.int64)
    m = {"format": GRAPH_FORMAT, **(meta or {})}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.stem}.tmp.npz")
    np.savez_compressed(tmp, n_nodes=np.int64(G["n_nodes"]), node_xy=G["node_xy"], rail_node=G["rail_node"],
                        road_node=G["road_node"], p_u=i32(G["p_u"]), p_v=i32(G["p_v"]), p_time=G["p_time"], p_len=G["p_len"],
                        p_rail=G["p_rail"], s_n=s_n.astype(np.int32), s_cell=i32(G["s_cell"]), street=G["street"],
                        stations=G["stations"], n_major_segments=np.int64(G["n_major_segments"]), meta=json.dumps(m, sort_keys=True))
    tmp.replace(path)
    return path


def load_graph(path):
    """Read a graph written by save_graph; returns the same dictionary as build_from_table."""
    import json
    with np.load(path, allow_pickle=False) as z:
        s_n = z["s_n"].astype(np.int64)
        G = {"n_nodes": int(z["n_nodes"]), "node_xy": z["node_xy"], "rail_node": z["rail_node"], "road_node": z["road_node"],
             "p_u": z["p_u"].astype(np.int64), "p_v": z["p_v"].astype(np.int64), "p_time": z["p_time"], "p_len": z["p_len"],
             "p_rail": z["p_rail"], "s_cell": z["s_cell"].astype(np.int64), "street": z["street"], "stations": z["stations"],
             "n_major_segments": int(z["n_major_segments"]), "meta": json.loads(str(z["meta"]))}
    G["s_piece"] = np.repeat(np.arange(len(s_n)), s_n)
    G["s_w"] = 1.0 / s_n[G["s_piece"]]
    return G


def zone_od(N, A_list, weights, kernels, grid, kz):
    """Zone populations, centres and the trip matrix sum_c w_c T^c (production constrained)."""
    ny, nx = N.shape
    by, bx = -(-ny // kz), -(-nx // kz)

    def agg(a):
        p = np.zeros((by * kz, bx * kz)); p[:ny, :nx] = a
        return p.reshape(by, kz, bx, kz).sum((1, 3)).ravel()
    Nz = agg(N)
    yy, xx = np.meshgrid(np.arange(by), np.arange(bx), indexing="ij")
    cx = grid.x0 + (xx.ravel() + 0.5) * kz * grid.cell
    cy = grid.y1 - (yy.ravel() + 0.5) * kz * grid.cell
    # population-weighted centre within each zone
    Xc, Yc = np.meshgrid(grid.centres()[0], grid.centres()[1])
    wx, wy = agg(N * Xc), agg(N * Yc)
    has = Nz > 0
    cx = np.where(has, wx / np.where(has, Nz, 1), cx); cy = np.where(has, wy / np.where(has, Nz, 1), cy)
    D = np.hypot(cx[:, None] - cx[None, :], cy[:, None] - cy[None, :])
    np.fill_diagonal(D, 0.52 * kz * grid.cell)               # mean distance within a square
    T = np.zeros_like(D)
    for A, w, (kf, radius) in zip(A_list, weights, kernels):
        Az = agg(A)
        F = kf(D) * (D <= radius)
        Zi = F @ Az
        ok = (Zi > 0) & (Nz > 0)
        T[ok] += w * (Nz[ok] / Zi[ok])[:, None] * F[ok] * Az[None, :]
    return Nz, cx, cy, T


try:
    from numba import njit

    @njit(cache=True)
    def _tree_flow(order, pred, demand):
        """Flow on the tree edge into every node: the demand of its subtree (nodes in order of
        decreasing distance). demand: (n_nodes, k)."""
        f = demand.copy()
        for v in order:
            p = pred[v]
            if p >= 0:
                for j in range(f.shape[1]):
                    f[p, j] += f[v, j]
        return f
    @njit(cache=True)
    def _heap_push(hd, hv, n, d, v):
        i = n
        hd[i] = d; hv[i] = v
        while i > 0:
            p = (i - 1) >> 1
            if hd[p] <= hd[i]:
                break
            hd[p], hd[i] = hd[i], hd[p]
            hv[p], hv[i] = hv[i], hv[p]
            i = p
        return n + 1

    @njit(cache=True)
    def _heap_pop(hd, hv, n):
        d, v = hd[0], hv[0]
        n -= 1
        hd[0] = hd[n]; hv[0] = hv[n]
        i = 0
        while True:
            l = 2 * i + 1
            if l >= n:
                break
            r = l + 1
            c = r if (r < n and hd[r] < hd[l]) else l
            if hd[i] <= hd[c]:
                break
            hd[c], hd[i] = hd[i], hd[c]
            hv[c], hv[i] = hv[i], hv[c]
            i = c
        return d, v, n

    @njit(cache=True)
    def _sp_flow(indptr, indices, data, src, limit, K0, Tsrc, edge_pt, dist, pred, pe, done, order, f, hd, hv):
        """One origin: Dijkstra from node src (binary heap, distances up to limit), then the flow of
        the sink demand Tsrc (n_zones, k) down the shortest-path tree, person-time (flow x edge
        time) added to edge_pt (n_edges, k). Returns the reached flags of the sinks."""
        n = indptr.shape[0] - 1
        nk = Tsrc.shape[1]
        for i in range(n):
            dist[i] = np.inf; pred[i] = -1; pe[i] = -1; done[i] = False
        dist[src] = 0.0
        hn = _heap_push(hd, hv, 0, 0.0, src)
        cnt = 0
        while hn > 0:
            d, u, hn = _heap_pop(hd, hv, hn)
            if done[u]:
                continue
            if d > limit:
                break
            done[u] = True
            order[cnt] = u
            cnt += 1
            for e in range(indptr[u], indptr[u + 1]):
                v = indices[e]
                if done[v]:
                    continue
                nd = d + data[e]
                if nd < dist[v]:
                    dist[v] = nd; pred[v] = u; pe[v] = e
                    hn = _heap_push(hd, hv, hn, nd, v)
        for j in range(cnt):
            v = order[j]
            for kk in range(nk):
                f[v, kk] = 0.0
        nz = Tsrc.shape[0]
        reached = np.zeros(nz, np.bool_)
        for z in range(nz):
            v = K0 + z
            if done[v]:
                reached[z] = True
                for kk in range(nk):
                    f[v, kk] = Tsrc[z, kk]
        for j in range(cnt - 1, 0, -1):
            v = order[j]
            e = pe[v]
            p = pred[v]
            w = data[e]
            for kk in range(nk):
                fv = f[v, kk]
                if fv != 0.0:
                    edge_pt[e, kk] += fv * w
                    f[p, kk] += fv
        return reached

    FAST_SP = True
except ImportError:                                           # slower fallback without numba
    FAST_SP = False

    def _tree_flow(order, pred, demand):
        f = demand.copy()
        for v in order:
            p = pred[v]
            if p >= 0:
                f[p] += f[v]
        return f


import os as _os
_FAST_OK = _os.environ.get("DYNAMIC_POPULATION_NET_SCIPY", "") != "1"       # DYNAMIC_POPULATION_NET_SCIPY=1: the scipy path (reference)


def assign(G, grid, Nz, cx, cy, Tods, kz, log=None):
    """All-or-nothing assignment of the trip matrices Tods (list, e.g. workday and rest day).
    Returns one 100 m person-time array per matrix and statistics."""
    t0 = time.time()
    nzn = len(Nz)
    nG = G["n_nodes"]
    S0, K0 = nG, nG + nzn                     # zone source and sink nodes
    rows, cols, wts, kinds, pids = [], [], [], [], []
    # network edges, both directions
    rows += [G["p_u"], G["p_v"]]; cols += [G["p_v"], G["p_u"]]; wts += [G["p_time"], G["p_time"]]
    pid = np.arange(len(G["p_u"]))
    pids += [pid, pid]; kinds += [np.zeros(len(pid), np.int8)] * 2
    # access to roads
    zone_xy = np.c_[cx, cy]
    acc_rows, acc_cols, acc_t, acc_zone = [], [], [], []
    road_idx = np.nonzero(G["road_node"])[0]
    if len(road_idx):
        tree = cKDTree(G["node_xy"][road_idx])
        d, j = tree.query(zone_xy, k=min(ACCESS_K, len(road_idx)))
        if d.ndim == 1:
            d, j = d[:, None], j[:, None]
        for z in range(nzn):
            for dd, jj in zip(d[z], j[z]):
                if np.isfinite(dd):
                    acc_zone.append(z); acc_cols.append(road_idx[jj]); acc_t.append(dd * DETOUR / (LOCAL_KMH / 3.6) / 3600.0)
    acc_zone = np.asarray(acc_zone, np.int64); acc_cols = np.asarray(acc_cols, np.int64); acc_t = np.asarray(acc_t)
    # access to rail through stations
    st = G["stations"]
    rz, rn, rt = [], [], []
    rail_idx = np.nonzero(G["rail_node"])[0]
    if len(st) and len(rail_idx):
        rtree = cKDTree(G["node_xy"][rail_idx])
        ds, js = rtree.query(st, k=1, distance_upper_bound=SNAP_STATION_M)
        ok = np.isfinite(ds)
        st_node = rail_idx[js[ok]]; st_xy = st[ok]
        if len(st_node):
            ztree = cKDTree(zone_xy)
            for s, (sx, sy) in zip(st_node, st_xy):
                for z in ztree.query_ball_point((sx, sy), WALK_TO_STATION_M):
                    dist = math.hypot(cx[z] - sx, cy[z] - sy)
                    rz.append(z); rn.append(s); rt.append(dist * DETOUR / (WALK_KMH / 3.6) / 3600.0)
    rz = np.asarray(rz, np.int64); rn = np.asarray(rn, np.int64); rt = np.asarray(rt)
    board = BOARD_MIN / 60.0
    # source -> network (access; boarding penalty for rail), network -> sink (egress)
    rows += [S0 + acc_zone, acc_cols, S0 + rz, rn]
    cols += [acc_cols, K0 + acc_zone, rn, K0 + rz]
    wts += [acc_t, acc_t, rt + board, rt]
    na, nr = len(acc_zone), len(rz)
    kinds += [np.full(na, 1, np.int8), np.full(na, 2, np.int8), np.full(nr, 1, np.int8), np.full(nr, 2, np.int8)]
    pids += [acc_zone, acc_zone, rz, rz]                      # zone of the access / egress edge
    # direct link source -> own sink for trips within a zone
    rows.append(S0 + np.arange(nzn)); cols.append(K0 + np.arange(nzn)); wts.append(np.full(nzn, 0.52 * kz * grid.cell * DETOUR / (LOCAL_KMH / 3.6) / 3600.0))
    kinds.append(np.full(nzn, 3, np.int8)); pids.append(np.arange(nzn))
    r = np.concatenate(rows).astype(np.int64); c = np.concatenate(cols).astype(np.int64)
    w = np.concatenate(wts); k = np.concatenate(kinds); p = np.concatenate(pids).astype(np.int64)
    w = np.maximum(w, 1e-9)
    ntot = nG + 2 * nzn
    # one edge per node pair (the fastest)
    key = r * ntot + c
    o = np.lexsort((w, key))
    key, r, c, w, k, p = key[o], r[o], c[o], w[o], k[o], p[o]
    first = np.r_[True, key[1:] != key[:-1]]
    key, r, c, w, k, p = key[first], r[first], c[first], w[first], k[first], p[first]
    M = csr_matrix((w, (r, c)), shape=(ntot, ntot))
    nk = len(Tods)
    piece_pt = np.zeros((len(G["p_u"]), nk))
    zone_local = np.zeros((nzn, nk))
    unreached = np.zeros(nk)
    origins = np.nonzero((Nz > 0) & (sum(T.sum(1) for T in Tods) > 0))[0]
    if FAST_SP and _FAST_OK:
        # one pass per origin in numba (same shortest paths as scipy's dijkstra; no dense outputs, no sorting)
        M.sort_indices()
        assert np.array_equal(M.indices, c) and np.array_equal(np.diff(M.indptr), np.bincount(r, minlength=ntot))
        indptr, indices, data = M.indptr.astype(np.int64), M.indices.astype(np.int64), M.data.astype(np.float64)
        nE = len(data)
        edge_pt = np.zeros((nE, nk))
        dist = np.empty(ntot); pred = np.empty(ntot, np.int64); pe = np.empty(ntot, np.int64)
        done = np.empty(ntot, np.bool_); order = np.empty(ntot, np.int64); fbuf = np.zeros((ntot, nk))
        hd = np.empty(nE + 1); hv = np.empty(nE + 1, np.int64)
        TT = np.stack(Tods, axis=-1)                         # (zones, zones, k)
        for q, i in enumerate(origins):
            Tsrc = np.ascontiguousarray(TT[i])
            reached = _sp_flow(indptr, indices, data, S0 + i, MAX_TRIP_H, K0, Tsrc, edge_pt, dist, pred, pe, done, order, fbuf, hd, hv)
            miss = ~reached
            if miss.any():                                   # no route: travel on local streets, straight line
                dmiss = np.hypot(cx[miss] - cx[i], cy[miss] - cy[i]) * DETOUR / (LOCAL_KMH / 3.6) / 3600.0
                for kk, T in enumerate(Tods):
                    unreached[kk] += T[i][miss].sum()
                    zone_local[i, kk] += 0.5 * (T[i][miss] * dmiss).sum()
                    np.add.at(zone_local[:, kk], np.nonzero(miss)[0], 0.5 * T[i][miss] * dmiss)
            if log and q % 400 == 0:
                log(f"    assignment {q + 1}/{len(origins)} origins ({time.time() - t0:.0f} s)")
        m0 = k == 0
        for kk in range(nk):
            piece_pt[:, kk] = np.bincount(p[m0], weights=edge_pt[m0, kk], minlength=len(G["p_u"]))
            zone_local[:, kk] += np.bincount(p[~m0], weights=edge_pt[~m0, kk], minlength=nzn)
        origins_loop = []
    else:
        origins_loop = origins
    batch = 8
    for b0 in range(0, len(origins_loop), batch):
        ob = origins_loop[b0:b0 + batch]
        dist, pred = dijkstra(M, directed=True, indices=S0 + ob, return_predecessors=True, limit=MAX_TRIP_H)
        for q, i in enumerate(ob):
            di, pi = dist[q], pred[q]
            dem = np.zeros((ntot, nk))
            for kk, T in enumerate(Tods):
                dem[K0:K0 + nzn, kk] = T[i]
            reach = np.isfinite(di)
            miss = ~reach[K0:K0 + nzn]
            if miss.any():                                   # no route: travel on local streets, straight line
                dmiss = np.hypot(cx[miss] - cx[i], cy[miss] - cy[i]) * DETOUR / (LOCAL_KMH / 3.6) / 3600.0
                for kk, T in enumerate(Tods):
                    unreached[kk] += T[i][miss].sum()
                    zone_local[i, kk] += 0.5 * (T[i][miss] * dmiss).sum()
                    np.add.at(zone_local[:, kk], np.nonzero(miss)[0], 0.5 * T[i][miss] * dmiss)
                dem[K0:K0 + nzn][miss] = 0.0
            nodes = np.nonzero(reach)[0]
            order = nodes[np.argsort(-di[nodes], kind="stable")]
            f = _tree_flow(order, pi.astype(np.int64), dem)
            v = nodes[pi[nodes] >= 0]
            pv = pi[v].astype(np.int64)
            fv = f[v]
            pos = np.searchsorted(key, pv * ntot + v)
            ek, ep = k[pos], p[pos]
            dt = (di[v] - di[pv])[:, None]
            pt = fv * dt
            m = ek == 0
            if m.any():
                np.add.at(piece_pt, ep[m], pt[m])
            m = ek > 0                                          # access, egress, within the zone
            if m.any():
                np.add.at(zone_local, ep[m], pt[m])
        if log and (b0 // batch) % 50 == 0:
            log(f"    assignment {min(b0 + batch, len(origins_loop))}/{len(origins_loop)} origins ({time.time() - t0:.0f} s)")
    # person-time -> cells
    out = []
    ncell = grid.nx * grid.ny
    sc, sp, sw = G["s_cell"], G["s_piece"], G["s_w"]
    ok = sc >= 0
    street = G["street"]
    kz_ = kz
    ny, nx = grid.shape
    by, bx = -(-ny // kz_), -(-nx // kz_)
    zr = (np.arange(ny) // kz_)[:, None] * bx + (np.arange(nx) // kz_)[None, :]
    st_z = np.bincount(zr.ravel(), weights=street.ravel(), minlength=by * bx)
    for kk in range(nk):
        a = np.bincount(sc[ok], weights=(piece_pt[sp[ok], kk] * sw[ok]), minlength=ncell).reshape(grid.shape)
        loc = zone_local[:, kk]
        share = np.where(st_z[zr] > 0, street / np.where(st_z[zr] > 0, st_z[zr], 1.0), np.nan)
        a += np.where(np.isfinite(share), share * loc[zr], 0.0)
        out.append(a)
    stats = {"origins": int(len(origins)), "zones": int(nzn), "nodes": int(nG), "pieces": int(len(G["p_u"])),
             "stations_used": int(len(np.unique(rn))) if len(rn) else 0, "seconds": round(time.time() - t0, 1),
             "network_share": [float(piece_pt[:, kk].sum() / max(piece_pt[:, kk].sum() + zone_local[:, kk].sum(), 1e-12))
                               for kk in range(nk)],
             "rail_share": [float(piece_pt[G["p_rail"], kk].sum() / max(piece_pt[:, kk].sum(), 1e-12)) for kk in range(nk)],
             "unreached_trip_share": [float(unreached[kk] / max(Tods[kk].sum(), 1e-12)) for kk in range(nk)]}
    return out, zone_local, stats, st_z
