"""Building floor area by use on the 100 m city grid (destination attractors).

For every Overture building (release 2026-10-21.0) in the model domain:

  use (classes C1..C7, in this order of evidence)
    1. OpenBuildingMap occupancy of the OBM building whose internal point lies in the
       footprint (largest one if several), unless UNK or agricultural; mixed classes are
       split by floor area (rules/mixed_use.json);
    2. the building's own Overture class, then subtype (rules/classification_rules.json);
    3. in China, when available, the Amap AOI parcel that contains the internal point
       (external AOI boundaries or circular pseudo-parcels derived from the AOI centre
       and area; the smallest overlapping pseudo-parcel takes precedence);
       then the Overture land-use polygon that contains
       it (OSM land use; several polygons -> priority C3 > C4 > C5 > C6 > C2 > C1 > C7);
    4. otherwise unknown use: kept as a separate layer (index 7, 'UNK'); the model splits it
       into residential and non-residential floor area with the GHSL non-residential share of
       the built volume of the cell (model.split_unknown).
  output: fa [9, ny, nx] float32, m2 of gross floor area of C1..C7 (use known), UNK, and IND
  (the part of C2 in industrial buildings: OBM IND*, Overture class factory / industrial /
  manufacture / warehouse or subtype industrial, OSM land use industrial).
  storeys (ordered fallback rules)
    Overture num_floors; else height / 3 m (Overture height, then OBM HHT, then the GHSL
    2018 average net building height of the 100 m cell, each only if >= 2 m); else OBM exact
    storeys H:n; else the city median of the building's class (>= 30 buildings) or of the
    city; else the middle of an OBM storey range; else 1.
  floor area = footprint area (local equal-area projection) x storeys, assigned to the 100 m
  cell of the building's internal point; footprints larger than 2,500 m2 are split over the
  cells they cover in proportion to the intersection area.

"""
from __future__ import annotations

import gc
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import shapely
from pyproj import Transformer

from stage_2_100m_layers.building_sources import open_building_map as obmmod
from stage_2_100m_layers.building_sources.open_building_map_reader import Reader as OBMReader
from stage_2_100m_layers.building_sources.overture_reader import Reader as OvReader
from stage_2_100m_layers.cities import grid_of

RULES = Path(__file__).resolve().parent / "building_sources" / "rules"
PRIORITY = [3, 4, 5, 6, 2, 1, 7]
STOREY = 3.0
SPLIT_M2 = 2500.0      # footprints larger than this are split over the cells they cover
# evidence that a C2 building is industrial (factory, warehouse): kept as layer 9 (subset of C2)
IND_CLASS = {"factory", "industrial", "manufacture", "warehouse"}
IND_SUBTYPE = {"industrial"}
IND_LANDUSE = {"industrial"}


def load_rules():
    rules = json.loads((RULES / "classification_rules.json").read_text(encoding="utf-8"))
    mixed = json.loads((RULES / "mixed_use.json").read_text(encoding="utf-8"))["fractions"]
    return rules, mixed


def _proj(geoms, tr):
    return shapely.transform(geoms, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))


def _code(series, table):
    s = pd.Series(series).fillna("").astype(str).str.strip().str.lower().map(table)
    out = np.zeros(len(s), np.int8)
    m = s.notna().to_numpy()
    out[m] = s[m].str[1:].astype(int).to_numpy()
    return out


def landuse(ov: OvReader, bbox, tr, rules):
    tab = ov.extract("land_use", bbox)
    if tab is None or not tab.num_rows:
        return None
    cls = pd.Series(tab.column("class").to_pylist()).fillna("").astype(str).str.lower()
    sub = pd.Series(tab.column("subtype").to_pylist()).fillna("").astype(str).str.lower()
    code = _code(cls + "|" + sub, rules["land_use_pair"])
    c2 = _code(cls, rules["land_use_class"]); code = np.where(code == 0, c2, code)
    c3 = _code(sub, rules["land_use_subtype"]); code = np.where(code == 0, c3, code)
    keep = code > 0
    if not keep.any():
        return None
    g = shapely.from_wkb(np.asarray(tab.column("geometry").to_pylist(), dtype=object)[keep])
    g = _proj(g, tr)
    bad = ~shapely.is_valid(g)
    if bad.any():
        g[bad] = shapely.make_valid(g[bad])
    rank = np.array([PRIORITY.index(c) if c in PRIORITY else 99 for c in range(8)])
    ind = cls.isin(IND_LANDUSE).to_numpy()[keep]
    return {"geoms": g, "code": code[keep], "ind": ind, "tree": shapely.STRtree(g), "rank": rank}


def load_aoi(stem: str, tr):
    """Amap AOI parcels of a Chinese city (the Amap AOI import step), as land-use evidence that comes
    before the OSM land use: {"geoms", "code", "ind", "tree", "rank"} or None."""
    import stage_1_data_inputs.configuration as configuration
    f = configuration.AOI_AMAP / f"{stem}.parquet"
    if not f.exists():
        return None
    import geopandas as gpd
    a = gpd.read_parquet(f)
    a = a[a.cls.astype(str).str.match(r"^C[1-7]$")]
    if not len(a):
        return None
    g = _proj(a.geometry.values, tr)
    bad = ~shapely.is_valid(g)
    if bad.any():
        g[bad] = shapely.make_valid(g[bad])
    code = a.cls.str[1:].astype(int).to_numpy().astype(np.int8)
    rank = np.array([PRIORITY.index(c) if c in PRIORITY else 99 for c in range(8)])
    out = {"geoms": g, "code": code, "ind": a.industrial.astype(bool).to_numpy(), "tree": shapely.STRtree(g), "rank": rank}
    if "area" in a.columns:          # pseudo-parcels (centre + area): where several overlap, the smallest decides
        out["prank"] = a["area"].to_numpy(float)
    return out


def landuse_at(pts, lu):
    """-> (class code 1..7 or 0, industrial flag) of the land-use polygon of every point."""
    out = np.zeros(len(pts), np.int8); ind = np.zeros(len(pts), bool)
    if lu is None or not len(pts):
        return out, ind
    pi, gi = lu["tree"].query(pts, predicate="within")
    if not len(pi):
        return out, ind
    codes = lu["code"][gi]
    r = lu["prank"][gi] if "prank" in lu else lu["rank"][codes]
    order = np.lexsort((r, pi))
    _, first = np.unique(pi[order], return_index=True)
    sel = order[first]
    out[pi[sel]] = codes[sel]
    ind[pi[sel]] = lu["ind"][gi[sel]]
    return out, ind


def iter_buildings(ov: OvReader, bbox, chunk=8):
    from stage_2_100m_layers.building_sources.overture_reader import THEMES
    theme, typ, cols, kind = THEMES["building"]
    rg = ov.row_groups("building", bbox)
    for path, g in rg.groupby("path"):
        rgs = g.rg.to_numpy()
        for part in np.array_split(rgs, max(1, int(np.ceil(len(rgs) / chunk)))):
            t = ov._read(path, part, cols, bbox, kind)
            if t.num_rows:
                yield t


def city_floor_area(row: dict, ov: OvReader, obm_reader: OBMReader, height: np.ndarray | None, rules, mixed, log=None):
    """-> (fa [7, ny, nx] float32 m2, stats dict)."""
    t0 = time.time()
    g = grid_of(row)
    crs = g.crs
    bbox = g.lonlat_bounds(0.003)
    tr = Transformer.from_crs(4326, crs, always_xy=True)
    lu = landuse(ov, bbox, tr, rules)
    aoi = load_aoi(row["stem"], tr)
    obm_df, oinfo = obm_reader.extract_city(bbox, crs)
    nobm = len(obm_df)
    n_obm_buildings = int(nobm)
    if nobm:
        # compact per-building OBM arrays (codes into small tables of unique values)
        occ_codes, occ_uni = pd.factorize(obm_df["occupancy"].astype(object).fillna(""), sort=False)
        occ_uni = obmmod.normalise(np.asarray(occ_uni, dtype=object))
        usable_uni = obmmod.usable_occupancy(occ_uni, rules)
        ind_uni = pd.Series(occ_uni).str.startswith("IND").to_numpy()
        h_codes, h_uni = pd.factorize(obm_df["height"].astype(object).fillna(""), sort=False)
        ex_u, lo_u, hi_u, hm_u = obmmod.parse_height(np.asarray(h_uni, dtype=object))
        ox = obm_df["x"].to_numpy(float); oy = obm_df["y"].to_numpy(float)
        oarea = obm_df["area"].to_numpy(float)
        oid = pd.factorize(obm_df["obm_id"])[0]
        ordx = np.argsort(ox, kind="stable"); oxs = ox[ordx]
        del obm_df
        gc.collect()
    # share table: index 0..6 = pure class c+1; further rows for OBM mixed occupancies
    lut = [np.eye(7)[i] for i in range(7)]
    lut_ix = {}
    recs = {k: [] for k in ("cell", "area", "share", "main", "floors", "lo", "hi", "method", "ind", "w", "first")}
    n_read = n_under = n_split = 0
    for t in iter_buildings(ov, bbox):
        n_read += t.num_rows
        under = np.asarray(t.column("is_underground").to_pylist(), dtype=object)
        under = np.array([bool(u) if u is not None else False for u in under])
        geoms = shapely.from_wkb(np.asarray(t.column("geometry").to_pylist(), dtype=object))
        ok = ~under & ~shapely.is_missing(geoms) & ~shapely.is_empty(geoms)
        n_under += int(under.sum())
        if not ok.any():
            continue
        gg = _proj(geoms[ok], tr)
        bad = ~shapely.is_valid(gg)
        if bad.any():
            gg[bad] = shapely.make_valid(gg[bad])
        area = shapely.area(gg)
        pts = shapely.point_on_surface(gg)
        r, c = g.index(shapely.get_x(pts), shapely.get_y(pts))
        keep = (area > 0) & (r >= 0)
        if not keep.any():
            continue
        idx_ok = np.flatnonzero(ok)[keep]
        gg, area, pts, r, c = gg[keep], area[keep], pts[keep], r[keep], c[keep]
        n = len(gg)
        cls_s = pd.Series(t.column("class").to_pylist()).iloc[idx_ok].reset_index(drop=True)
        sub_s = pd.Series(t.column("subtype").to_pylist()).iloc[idx_ok].reset_index(drop=True)
        nf = pd.to_numeric(pd.Series(t.column("num_floors").to_pylist()).iloc[idx_ok], errors="coerce").to_numpy(float)
        hov = pd.to_numeric(pd.Series(t.column("height").to_pylist()).iloc[idx_ok], errors="coerce").to_numpy(float)
        # OBM match: OBM internal points inside the chunk envelope, then point-in-footprint
        pick = np.full(n, -1, np.int64)
        if nobm:
            bx0, by0, bx1, by1 = shapely.total_bounds(gg)
            i0, i1 = np.searchsorted(oxs, [bx0, bx1], side="left")[0], np.searchsorted(oxs, bx1, side="right")
            cand = ordx[i0:i1]
            cand = cand[(oy[cand] >= by0) & (oy[cand] <= by1)]
            if len(cand):
                sub_df = pd.DataFrame({"area": oarea[cand], "obm_id": oid[cand]})
                pk, _ = obmmod.match(gg, sub_df, shapely.points(ox[cand], oy[cand]))
                pick = np.where(pk >= 0, cand[np.maximum(pk, 0)], -1)
        share = np.full(n, -1, np.int64); method = np.zeros(n, np.int8)   # 1 obm 2 class 3 subtype 4 land use 5 default
        isind = np.zeros(n, bool)
        m = pick >= 0
        if m.any():
            usable = np.zeros(n, bool); usable[m] = usable_uni[occ_codes[pick[m]]]
            if usable.any():
                occ = occ_uni[occ_codes[pick[usable]]]
                for o in pd.unique(occ):
                    if o not in lut_ix:
                        _, sh = obmmod.class_shares(np.array([o]), rules, mixed)
                        lut_ix[o] = len(lut); lut.append(sh[0])
                share[usable] = np.array([lut_ix[o] for o in occ]); method[usable] = 1
                isind[usable] = ind_uni[occ_codes[pick[usable]]]
        own = _code(cls_s, rules["class"]); rest = share < 0
        s = rest & (own > 0); share[s] = own[s] - 1; method[s] = 2
        isind[s] = cls_s.fillna("").astype(str).str.lower().isin(IND_CLASS).to_numpy()[s]
        ownst = _code(sub_s, rules["subtype"]); rest = share < 0
        s = rest & (ownst > 0); share[s] = ownst[s] - 1; method[s] = 3
        isind[s] = sub_s.fillna("").astype(str).str.lower().isin(IND_SUBTYPE).to_numpy()[s]
        rest = share < 0
        if rest.any() and aoi is not None:          # Amap AOI parcels (China), before the OSM land use
            ac, ai = landuse_at(pts[rest], aoi)
            ri = np.flatnonzero(rest)
            s = ac > 0
            share[ri[s]] = ac[s] - 1; method[ri[s]] = 6
            isind[ri[s]] = ai[s]
        rest = share < 0
        if rest.any():
            luc, lui = landuse_at(pts[rest], lu)
            ri = np.flatnonzero(rest)
            s = luc > 0
            share[ri[s]] = luc[s] - 1; method[ri[s]] = 4
            isind[ri[s]] = lui[s]
        rest = share < 0; share[rest] = 0; method[rest] = 5
        # storeys known directly
        h = np.where(np.isfinite(hov) & (hov >= 2), hov, np.nan)
        if m.any():
            hm = np.full(n, np.nan); hm[m] = hm_u[h_codes[pick[m]]]
            h = np.where(np.isnan(h) & np.isfinite(hm) & (hm >= 2), hm, h)
        if height is not None:
            hg = height[r, c].astype(float)
            h = np.where(np.isnan(h) & (hg >= 2), hg, h)
        fl = np.where(np.isfinite(nf) & (nf >= 1), np.round(nf), np.nan)
        fl = np.where(np.isnan(fl) & np.isfinite(h), np.maximum(1, np.round(h / STOREY)), fl)
        ex = np.full(n, np.nan); lo = np.full(n, np.nan); hi = np.full(n, np.nan)
        if m.any():
            hc = h_codes[pick[m]]
            ex[m] = ex_u[hc]; lo[m] = lo_u[hc]; hi[m] = hi_u[hc]
        fl = np.where(np.isnan(fl) & np.isfinite(ex) & (ex >= 1), np.round(ex), fl)
        lut_arr = np.array(lut)
        main = lut_arr[share].argmax(axis=1) + 1
        isind = isind & (main == 2)
        # large footprints: split the building over the cells it covers, by intersection area
        rows_i = np.arange(n); cell = (r * g.nx + c).astype(np.int64); w = np.ones(n, np.float32); first = np.ones(n, bool)
        big = np.flatnonzero(area > SPLIT_M2)
        if len(big):
            bi_l, ce_l, fr_l = [], [], []
            b = shapely.bounds(gg[big])
            c0 = np.clip(np.floor((b[:, 0] - g.x0) / g.cell).astype(np.int64), 0, g.nx - 1)
            c1 = np.clip(np.floor((b[:, 2] - g.x0) / g.cell).astype(np.int64), 0, g.nx - 1)
            r0 = np.clip(np.floor((g.y1 - b[:, 3]) / g.cell).astype(np.int64), 0, g.ny - 1)
            r1 = np.clip(np.floor((g.y1 - b[:, 1]) / g.cell).astype(np.int64), 0, g.ny - 1)
            for j, i in enumerate(big):
                if r0[j] == r1[j] and c0[j] == c1[j]:
                    continue
                rr, cc = np.meshgrid(np.arange(r0[j], r1[j] + 1), np.arange(c0[j], c1[j] + 1), indexing="ij")
                rr = rr.ravel(); cc = cc.ravel()
                boxes = shapely.box(g.x0 + cc * g.cell, g.y1 - (rr + 1) * g.cell, g.x0 + (cc + 1) * g.cell, g.y1 - rr * g.cell)
                ia = shapely.area(shapely.intersection(gg[i], boxes))
                tot = ia.sum()
                if tot <= 0:
                    continue
                sel = ia > 0
                bi_l.append(np.full(int(sel.sum()), i)); ce_l.append(rr[sel] * g.nx + cc[sel]); fr_l.append(ia[sel] / tot)
            if bi_l:
                rep = np.concatenate(bi_l)
                split = np.zeros(n, bool); split[rep] = True
                n_split += int(split.sum())
                keep_i = np.flatnonzero(~split)
                fst = np.r_[True, rep[1:] != rep[:-1]]
                rows_i = np.concatenate([keep_i, rep]); cell = np.concatenate([cell[keep_i], np.concatenate(ce_l)])
                w = np.concatenate([np.ones(len(keep_i), np.float32), np.concatenate(fr_l).astype(np.float32)])
                first = np.concatenate([np.ones(len(keep_i), bool), fst])
        recs["cell"].append(cell); recs["area"].append((area[rows_i] * w).astype(np.float32))
        recs["share"].append(share[rows_i].astype(np.int32)); recs["main"].append(main[rows_i].astype(np.int8))
        recs["floors"].append(fl[rows_i].astype(np.float32)); recs["lo"].append(lo[rows_i].astype(np.float32))
        recs["hi"].append(hi[rows_i].astype(np.float32))
        recs["method"].append(method[rows_i]); recs["ind"].append(isind[rows_i]); recs["w"].append(w); recs["first"].append(first)
        del gg, geoms, pts, t
        gc.collect()
    stats = {"stem": row["stem"], "read": int(n_read), "underground": int(n_under), "obm_buildings": n_obm_buildings,
             "split_buildings": int(n_split)}
    if not recs["cell"]:
        stats.update(buildings=0, seconds=round(time.time() - t0, 1))
        return np.zeros((9,) + g.shape, np.float32), stats
    R = {k: np.concatenate(v) for k, v in recs.items()}
    fl = R["floors"].astype(float)
    known = np.isfinite(fl)
    kf = known & R["first"]                 # medians over buildings, not over the cell pieces of split buildings
    city_med = float(np.median(fl[kf])) if kf.any() else np.nan
    for cc in range(1, 8):
        sel = np.isnan(fl) & (R["main"] == cc)
        if not sel.any():
            continue
        kc = kf & (R["main"] == cc)
        if kc.sum() >= 30:
            fl[sel] = np.round(np.median(fl[kc]))
        elif np.isfinite(city_med):
            fl[sel] = np.round(city_med)
    sel = np.isnan(fl) & np.isfinite(R["lo"]) & np.isfinite(R["hi"])
    fl[sel] = np.maximum(1, np.round((R["lo"][sel] + R["hi"][sel]) / 2))
    fl[np.isnan(fl)] = 1
    lut_arr = np.array(lut)
    gross = R["area"].astype(float) * fl
    unknown = R["method"] == 5
    fa = np.zeros((9, g.ny * g.nx), np.float64)
    for k in range(7):
        w = np.where(unknown, 0.0, gross * lut_arr[R["share"], k])
        nz = w > 0
        if nz.any():
            fa[k] = np.bincount(R["cell"][nz], weights=w[nz], minlength=g.ny * g.nx)
    if unknown.any():                       # layer 8: floor area of buildings without any use evidence
        fa[7] = np.bincount(R["cell"][unknown], weights=gross[unknown], minlength=g.ny * g.nx)
    isind = R["ind"] & ~unknown             # layer 9: C2 floor area of industrial buildings (subset of layer 2)
    if isind.any():
        fa[8] = np.bincount(R["cell"][isind], weights=(gross * lut_arr[R["share"], 1])[isind], minlength=g.ny * g.nx)
    meth = np.bincount(R["method"], weights=R["w"], minlength=7)[1:] / R["w"].sum()
    stats.update(buildings=int(R["first"].sum()), footprint_km2=float(R["area"].sum() / 1e6), gross_km2=float(gross.sum() / 1e6),
                 share_obm=float(meth[0]), share_own_class=float(meth[1]), share_own_subtype=float(meth[2]),
                 share_land_use=float(meth[3]), share_default=float(meth[4]), share_aoi=float(meth[5]), floors_known=float(known[R["first"]].mean()),
                 gross_by_class_km2=[float(x / 1e6) for x in fa.sum(1)], obm_seconds=oinfo.get("seconds"),
                 seconds=round(time.time() - t0, 1))
    return fa.reshape((9,) + g.shape).astype(np.float32), stats
