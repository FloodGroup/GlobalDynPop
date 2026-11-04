"""City model: components and hourly population.

    P(x, h, tau) = s_C1(h, tau) N(x) + sum_{c in C2..C5, C7} s_c(h, tau) D_c(x) + s_C6(h, tau) T(x)

N      residents (GHS-POP 2025, 100 m)
D_c    residents redistributed to the destinations of activity class c (gravity.allocate)
T      people travelling: person-time of trips assigned to the road and rail network.
       The Gaussian fallback uses the mean of the origin and work-destination distributions,
       smoothed with a Gaussian of SIGMA_TRAVEL (people in transit are between home and destination)
s_c    hourly activity-location shares of the country (timeuse), tau = workday / rest day

Every component sums to the domain population, the shares sum to 1 for every hour, so the
domain total is the same at every hour (closed domain).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

import stage_1_data_inputs.configuration as config
from stage_3_activity_allocation.gravity import allocate, kernel

SIGMA_TRAVEL_M = 1000.0


@dataclass
class Params:
    """Per activity class: kernel kind ('exp' | 'pow'), cut-off / decay length d0 (m),
    power-law exponent beta, and attractor ('poi' | 'nres' | 'mix')."""
    d0: dict = field(default_factory=lambda: {"C2": 30000.0, "C3": 10000.0, "C4": 20000.0, "C5": 10000.0, "C7": 10000.0})
    attractor: dict = field(default_factory=lambda: {"C2": "poi", "C3": "poi", "C4": "poi", "C5": "poi", "C7": "poi"})
    kind: dict | str = field(default_factory=lambda: {"C2": "pow", "C3": "pow", "C4": "pow", "C5": "pow", "C7": "pow"})
    beta: dict = field(default_factory=lambda: {"C2": 1.5, "C3": 2.0, "C4": 1.5, "C5": 2.0, "C7": 2.0})
    radius_factor: float = 6.0
    max_radius_m: float = 100000.0
    c7_like: str = "C5"          # attractor class used for 'other'
    restday: dict = field(default_factory=dict)   # overrides for rest days, e.g. {"d0": {"C5": 30000}, "beta": {...}}
    country: dict = field(default_factory=dict)   # overrides by ISO3 code, e.g. {"CHN": {"d0": {"C2": 10000}}} (also "restday")
    transit: str = "gauss"       # people travelling (C6): 'network' = road / rail assignment of 04_intermediate/network/<stem>.npz
                                 # (s05b_network.py) where present, else the Gaussian approximation; 'gauss' = Gaussian approximation
    transit_water_mask: bool = False   # people travelling are not placed on permanent water (share of the cell
                                       # covered, 01_inputs/basemap/landcover); the rest of the layer is rescaled to the same total

    def k(self, c):
        return self.kind[c] if isinstance(self.kind, dict) else self.kind

    def for_country(self, iso3: str | None) -> "Params":
        """Copy with the overrides of one country applied (keys as in the JSON: d0, beta, kind,
        attractor, restday); the result has no country table left."""
        import copy
        q = copy.deepcopy(self)
        ov = self.country.get(iso3 or "", {}) if self.country else {}
        for key, val in ov.items():
            if key == "restday" and isinstance(val, dict):
                for k2, nested_value in val.items():
                    if isinstance(nested_value, dict):
                        q.restday.setdefault(k2, {}).update(nested_value)
                    else:
                        q.restday[k2] = nested_value
            elif key in ("d0", "attractor", "kind", "beta"):
                classes = set(q.d0)
                per_class = isinstance(val, dict) and len(val) > 0 and set(val) <= classes
                cur = getattr(q, key)
                if per_class:
                    if isinstance(cur, dict):
                        if key == "attractor":
                            for cls, override in val.items():
                                if isinstance(cur.get(cls), dict) and isinstance(override, dict):
                                    cur[cls] = {**cur[cls], **copy.deepcopy(override)}
                                else:
                                    cur[cls] = copy.deepcopy(override)
                        else:
                            cur.update(val)
                    else:
                        setattr(q, key, {c: cur for c in q.d0} | val)
                else:                      # one value or one destination specification for every class
                    setattr(q, key, {c: copy.deepcopy(val) for c in q.d0})
            elif hasattr(q, key):
                setattr(q, key, val)
        q.country = {}
        return q

    def for_daytype(self, daytype: str) -> "Params":
        """Copy with the rest-day overrides applied (daytype 'restday', 'saturday', 'sunday')."""
        import copy
        q = copy.deepcopy(self)
        if daytype in ("restday", "saturday", "sunday") and self.restday:
            for key, val in self.restday.items():
                if key in ("d0", "attractor", "kind", "beta") and isinstance(val, dict):
                    cur = getattr(q, key)
                    if isinstance(cur, dict):
                        cur.update(val)
                    else:
                        setattr(q, key, {c: cur for c in q.d0} | val)
                elif hasattr(q, key):
                    setattr(q, key, val)
        q.restday = {}
        return q


def load_layers(stem: str):
    """N residents, V non-residential volume (m3), P dict of the other layers: POI counts by
    class ('C2'..'C6'), floor area by use ('FA_C1'..'FA_C7', 'FA_UNK'), GHSL total built
    volume ('_VT'), GHSL height ('_H') and the residents again ('_N', for the POI weight).
    Experiments: DYNAMIC_POPULATION_BUILDINGS_DIR and DYNAMIC_POPULATION_PLACES_AMAP_DIR replace 01_inputs/buildings/floor_area and 01_inputs/poi/china."""
    N = np.load(config.ghsl_file("pop", stem)).astype(np.float64)
    V = np.load(config.ghsl_file("vol_nres", stem)).astype(np.float64)
    P = {}
    p = config.POI_OVERTURE / f"{stem}.npz"
    if p.exists():
        with np.load(p) as z:
            P = {k: z[k].astype(np.float64) for k in z.files}
    o = config.POI_OSM / f"{stem}.npz"
    if o.exists():                       # OpenStreetMap POIs (s07_osm_pois.py)
        with np.load(o) as z:
            for k in z.files:
                P[f"OSM_{k}"] = z[k].astype(np.float64)
    a = Path(os.environ.get("DYNAMIC_POPULATION_PLACES_AMAP_DIR") or (config.POI_CHINA)) / f"{stem}.npz"
    if a.exists():                       # Amap POIs (tools/amap, China)
        with np.load(a) as z:
            for k in z.files:
                P[f"AMAP_{k}"] = z[k].astype(np.float64)
    h = config.ghsl_file("height", stem)
    if h.exists():
        P["_H"] = np.load(h).astype(np.float64)
    vt = config.ghsl_file("vol", stem)
    if vt.exists():
        P["_VT"] = np.load(vt).astype(np.float64)
    b = Path(os.environ.get("DYNAMIC_POPULATION_BUILDINGS_DIR") or (config.FLOOR_AREA)) / f"{stem}.npz"
    if b.exists():
        with np.load(b) as z:
            fa = z["fa"].astype(np.float64)
        for i in range(7):
            P[f"FA_C{i + 1}"] = fa[i]
        if fa.shape[0] > 7:
            P["FA_UNK"] = fa[7]
        if fa.shape[0] > 8:
            P["FA_IND"] = fa[8]
    # share of every cell covered by permanent water (01_inputs/basemap/landcover, s11_landcover.py: at least
    # two of ESA WorldCover 2021, JRC Global Surface Water and OpenStreetMap water polygons not flagged as intermittent)
    w = config.BASEMAP / "landcover" / f"{stem}.npz"
    if w.exists():
        with np.load(w) as z:
            W = z["pw"].astype(np.float64) / 100.0
        if W.shape == N.shape:
            P["_W"] = W
    q = config.BASEMAP / "outdoor" / f"{stem}.npz"            # share covered by outdoor recreation land use
    if q.exists():
        with np.load(q) as z:
            Q = z["outdoor"].astype(np.float64) / 100.0
        if Q.shape == N.shape:
            P["_Q"] = Q
    # GlobalBuildingAtlas footprint and volume of every cell (10_prepare_buildings_open_space.py) and its open space
    # by type (streets, parking, squares, parks, grass, sports grounds, campus grounds, construction sites, other)
    gc_ = config.GBA_CELLS / f"{stem}.npz"
    if config.LOAD_GBA and gc_.exists():
        with np.load(gc_) as z:
            if z["foot_m2"].shape == N.shape:
                P["_GF"] = z["foot_m2"].astype(np.float64)
                P["_GV"] = z["vol_m3"].astype(np.float64)
    os_ = config.OPEN_SPACE / f"{stem}.npz"
    if config.LOAD_OS and os_.exists():
        with np.load(os_) as z:
            P["_OS"] = {k: z[k].astype(np.float64) for k in z.files if k != "meta" and z[k].shape == N.shape}
    # Open space of every cell = land share (no permanent water) minus the building footprint (using the
    # GlobalBuildingAtlas footprint, or the fallback GHS-BUILT-V volume / GHS-BUILT-H height)
    land = 1.0 - P.get("_W", 0.0)
    if "_GF" in P:
        fp = P["_GF"] / 1.0e4
    elif "_VT" in P and "_H" in P:
        fp = np.where(P["_VT"] > 0, P["_VT"] / np.maximum(P["_H"], 3.0), 0.0) / 1.0e4
    else:
        fp = np.zeros_like(N)
    P["_U"] = np.clip(land - np.clip(fp, 0.0, 1.0), 0.0, 1.0)
    win = w_indoor_of(stem)                    # share of the day spent indoors (01_inputs/time_use/w_indoor)
    if win is not None:
        P["_WIN"] = win
    # built-up cells as in the land-use layer (s10_land_use.py): floor area >= 500 m2 or GHSL volume >= 1,500 m3
    fa_keys = [k for k in ("FA_C1", "FA_C2", "FA_C3", "FA_C4", "FA_C5", "FA_C6", "FA_C7", "FA_UNK") if k in P]
    floor = sum(P[k] for k in fa_keys) if fa_keys else np.zeros_like(N)
    vt = P.get("_GV", P.get("_VT", np.zeros_like(N)))      # GlobalBuildingAtlas volume
    P["_B"] = ((floor >= 500.0) | (vt >= 1500.0)).astype(np.float64)
    P["_N"] = N
    return N, V, P


POI_CLASSES = ("C2", "C3", "C4", "C5", "C6")
_WIN_TABLE = {}


def w_indoor_of(stem: str):
    """W_indoor of the city: share of the day spent inside buildings (01_inputs/time_use/w_indoor/w_indoor_cities.csv,
    columns stem, iso3 and w_indoor; another table with GDP_WINDOOR). A domain that is not in the table
    (e.g. a validation domain) takes the median of its country (ISO code in the stem), else the median of all cities.
    None without the table."""
    if not _WIN_TABLE:
        f = Path(os.environ.get("GDP_WINDOOR") or (config.TIMEUSE / "w_indoor" / "w_indoor_cities.csv"))
        if not f.exists():
            return None
        import pandas as pd
        t = pd.read_csv(f, encoding="utf-8-sig")
        _WIN_TABLE["stem"] = {str(a): float(b) for a, b in zip(t["stem"], t["w_indoor"])}
        _WIN_TABLE["iso"] = t.groupby("iso3")["w_indoor"].median().to_dict()
        _WIN_TABLE["all"] = float(t["w_indoor"].median())
    v = _WIN_TABLE["stem"].get(stem)
    if v is None:
        parts = stem.split("_")
        v = _WIN_TABLE["iso"].get(parts[1] if len(parts) > 2 else "", _WIN_TABLE["all"])
    return float(v)


def poi_density(P) -> float:
    """POIs (all activity classes) per 1,000 residents of the domain."""
    n = sum(float(P[c].sum()) for c in POI_CLASSES if c in P)
    return n / max(float(P["_N"].sum()) / 1000.0, 1e-9) if "_N" in P else 0.0


def poi_weight(P, half: float = 5.0, wmax: float = 0.5) -> float:
    """Weight of the POI layer in the floor-area/POI mixture, by the POI coverage of the city:
    w = wmax * rho / (rho + half), rho = POIs per 1,000 residents."""
    rho = poi_density(P)
    return wmax * rho / (rho + half)


def nonres_unknown(P, V):
    """Non-residential part of the floor area of buildings without use evidence: FA_UNK times
    the GHSL non-residential share of the built volume of the cell (0 where GHSL has no
    built volume)."""
    unk = P.get("FA_UNK")
    if unk is None:
        return None
    VT = P.get("_VT")
    if VT is None:
        return np.zeros_like(unk)
    r = np.where(VT > 0, np.clip(V / np.where(VT > 0, VT, 1.0), 0.0, 1.0), 0.0)
    if "_GV" in P:
        # cells where GHSL has (almost) no built volume but GlobalBuildingAtlas has buildings (missing GHSL
        # tiles, recent construction) take the non-residential share of the cells of the city with a GHSL volume, or,
        # if GHSL has hardly any volume in the city, the non-residential share of the floor area of known use
        GV = P["_GV"]
        ok = (VT > 0.25 * GV) & (GV > 0)
        if ok.sum() > 0.5 * max(int((GV > 0).sum()), 1):
            r_city = float(np.clip(V[ok].sum() / max(VT[ok].sum(), 1e-9), 0.0, 1.0))
        else:
            known = [P[k] for k in ("FA_C1", "FA_C2", "FA_C3", "FA_C4", "FA_C5", "FA_C6", "FA_C7") if k in P]
            tot = sum(float(a.sum()) for a in known)
            r_city = 1.0 - float(P["FA_C1"].sum()) / tot if known and tot > 0 and "FA_C1" in P else 0.3
        r = np.where(ok, r, r_city)
    return r * unk


def poi_layer(source: str, cls: str, P, V, shop_w=None):
    """POI counts of the class from one source or the sum of several ('overture', 'osm',
    'amap', 'overture+osm', ...). 'auto': Amap where the city has Amap POIs (China, s08);
    otherwise Overture, plus OpenStreetMap where Overture has fewer than 1 POI per 1,000
    residents and OpenStreetMap has more POIs than Overture.
    shop_w (C2, Amap layers with the work-place / shop split of s08_cnpoi.py): the C2 POIs of
    work places (AMAP_C2W) and of shops and personal services (AMAP_C2S) are normalised
    separately and mixed with weights 1 - shop_w and shop_w (the shares of work and of shopping /
    services in the time at C2 places), keeping the total count; None: plain counts."""
    if source == "auto" and sum(float(P[f"AMAP_{c}"].sum()) for c in POI_CLASSES if f"AMAP_{c}" in P) > 0:
        source = "amap"
    if source in ("auto", "auto_noamap"):        # auto_noamap: the rule below even where the city has Amap POIs
        ov = sum(float(P[c].sum()) for c in POI_CLASSES if c in P)
        osm = sum(float(P[f"OSM_{c}"].sum()) for c in POI_CLASSES if f"OSM_{c}" in P)
        npop = float(P["_N"].sum()) / 1000.0 if "_N" in P else 1.0
        source = "overture+osm" if (ov / max(npop, 1e-9) < 1.0 and osm > ov) else "overture"
    out = np.zeros_like(V)
    for src in source.split("+"):
        key = {"overture": cls, "osm": f"OSM_{cls}", "amap": f"AMAP_{cls}"}[src]
        if src == "amap" and cls == "C2" and shop_w is not None and "AMAP_C2W" in P and "AMAP_C2S" in P:
            W, S = P["AMAP_C2W"], P["AMAP_C2S"]
            if W.sum() > 0 and S.sum() > 0:
                tot = float(W.sum() + S.sum())
                out = out + tot * ((1.0 - float(shop_w)) * W / W.sum() + float(shop_w) * S / S.sum())
                continue
        if key in P:
            out = out + P[key]
    return out


def attractor_spec(spec: dict, cls: str, V, P):
    """Destination layer from a specification (dict), raised to the attractiveness exponent alpha:
    A = (A0 / sum A0) ** alpha, A0 from attractor_layer (alpha = 1: A0 itself). The exponent is the destination
    attractiveness exponent of the Huff model: alpha > 1 concentrates the visitors in the most attractive cells."""
    A = attractor_layer(spec, cls, V, P)
    a = float(spec.get("alpha", 1.0))
    if a != 1.0:
        s = float(A.sum())
        if s > 0:
            A = np.power(A / s, a)
    return A


def _attractor_core(spec: dict, cls: str, V, P):
    """Destination layer from a specification (dict):
      fa        weight of floor area of the class (1) - 0 for POIs only
      ind_w     weight of industrial floor area relative to other C2 floor area (C2 only; 1)
      unk_w     weight of the non-residential part of unknown-use floor area (C2 only; 0 = off)
      poi_w     weight of POIs in the mixture: number, or 'auto<half>' (poi_weight; 0.5)
      poi_sigma_m  Gaussian smoothing of the POI counts before use (0)
      poi_source   'overture' (default), 'osm', 'amap' or sums such as 'overture+osm'
      shop_w    C2 with Amap POIs: weight of shops / personal services against work places (poi_layer)
      mode      'mix'  (1 - w) fa / sum(fa) + w poi / sum(poi)
                'prod' fa * (poi_s / mean(poi_s over cells with floor area) + eps)
      eps       floor of the POI factor in 'prod' (0.1)
      gamma     exponent of the POI factor in 'prod' (1); cap: upper bound of the factor (none)
      alpha     attractiveness exponent, applied by attractor_spec (1)"""
    from scipy.ndimage import gaussian_filter as _gf
    fa = P.get(f"FA_{cls}", np.zeros_like(V)).copy()
    if cls == "C2":
        if "FA_IND" in P and spec.get("ind_w", 1.0) != 1.0:
            fa -= (1.0 - float(spec["ind_w"])) * P["FA_IND"]
        uw = float(spec.get("unk_w", 0.0))
        if uw > 0:
            nu = nonres_unknown(P, V)
            if nu is not None:
                fa += uw * nu
    fa = np.maximum(fa, 0.0)
    poi = poi_layer(spec.get("poi_source", "overture"), cls, P, V, shop_w=spec.get("shop_w"))
    raw = poi
    sig = float(spec.get("poi_sigma_m", 0.0))
    if sig > 0 and poi.sum() > 0:
        poi = _gf(poi, sig / 100.0, mode="constant")
    pm = spec.get("poi_mask")
    if pm and "_B" in P:
        # the smoothed POI layer only on the cells that can host the activity: built-up cells and the cells of
        # the POIs themselves ('host'), and also outdoor recreation land ('host_outdoor', leisure and other activities)
        M = np.maximum(P["_B"], (raw > 0).astype(np.float64)) if pm in ("host", "host_outdoor") else P["_B"].copy()
        if pm == "host_outdoor" and "_Q" in P:
            M = np.maximum(M, (P["_Q"] > 0).astype(np.float64))
        poi = poi * M
    if fa.sum() <= 0 and poi.sum() <= 0:
        return V
    mode = spec.get("mode", "mix")
    if mode in ("prod", "prodmix"):
        if fa.sum() <= 0:
            return poi
        if poi.sum() <= 0:
            return fa
        m = float(poi[fa > 0].mean()) or 1.0
        fac = poi / m + float(spec.get("eps", 0.1))
        if "cap" in spec:                       # upper bound of the centrality factor
            fac = np.minimum(fac, float(spec["cap"]))
        g = float(spec.get("gamma", 1.0))       # concave transform of the centrality factor
        pr = fa * (fac ** g if g != 1.0 else fac)
        if mode == "prod":
            return pr
        # prodmix: centrality-weighted floor area mixed with the raw POI layer
        raw = poi_layer(spec.get("poi_source", "overture"), cls, P, V, shop_w=spec.get("shop_w"))
        w = float(spec.get("poi_w", 0.5))
        return (1 - w) * pr / pr.sum() + w * raw / max(raw.sum(), 1e-12)
    w = spec.get("poi_w", 0.5)
    if isinstance(w, str):
        w = poi_weight(P, half=float(w[4:] or 5.0)) if w.startswith("auto") else float(w)
    w = float(w) if float(spec.get("fa", 1.0)) > 0 else 1.0
    if poi.sum() <= 0:
        return fa
    if fa.sum() <= 0 or w >= 1:
        return poi
    return (1 - w) * fa / fa.sum() + w * poi / poi.sum()


def attractor_layer(spec: dict, cls: str, V, P):
    """Destination layer from a specification (dict); see _attractor_core for the building and POI part. outdoor_w   share of the destinations on outdoor recreation land use (parks, playgrounds, sports grounds,
                  pedestrian squares, gardens; 01_inputs/basemap/outdoor), in proportion to its land area; the rest
                  keeps the building and POI layer (0 = off)
      water_mask  destinations are not placed on water: the layer is multiplied by the land share of every cell"""
    A = _attractor_core(spec, cls, V, P)
    wo = float(spec.get("outdoor_w", 0.0))
    if wo > 0 and "_Q" in P:
        Q = P["_Q"] * (1.0 - P.get("_W", 0.0))
        if Q.sum() > 0 and A.sum() > 0:
            A = (1.0 - wo) * A / A.sum() + wo * Q / Q.sum()
    if spec.get("water_mask") and "_W" in P:
        A = A * (1.0 - P["_W"])
    if spec.get("two_pool") and P.get("_WIN") is None:
        raise ValueError("two_pool destinations need W_indoor of the city (01_inputs/time_use/w_indoor/w_indoor_cities.csv)")
    if spec.get("two_pool") and spec.get("outdoor_pool") and "_OS" in P and A.sum() > 0:
        return _two_pool_destinations(spec, cls, A, P)
    if spec.get("two_pool") and "_U" in P and A.sum() > 0:
        # the untyped open-space method: indoor pool (buildings and POIs, weight W_indoor) and outdoor pool (weight 1 - W_indoor): the open
        # space of the cells (no buildings, no permanent water) of the urban fabric around the indoor destinations
        # (Gaussian, outdoor_sigma_m), for leisure and other activities half of it on outdoor recreation land (parks,
        # sports grounds, squares)
        w_in = float(P["_WIN"])
        a_in = A / A.sum()
        near = gaussian_filter(a_in, float(spec.get("outdoor_sigma_m", 300.0)) / 100.0, mode="constant")
        # open space of the urban fabric only: cells with indoor destinations (buildings, POIs) and outdoor recreation
        # land; not cropland, natural vegetation, wetlands or bare land without buildings
        fabric = (a_in > 0) | ((P["_Q"] > 0) if "_Q" in P else False)
        a_out = P["_U"] * near * fabric
        if cls == "C5" and "_Q" in P:
            Q = P["_Q"] * (1.0 - P.get("_W", 0.0))
            if Q.sum() > 0 and a_out.sum() > 0:
                a_out = 0.5 * a_out / a_out.sum() + 0.5 * Q / Q.sum()
        if a_out.sum() > 0:
            A = w_in * a_in + (1.0 - w_in) * a_out / a_out.sum()
    return A


def _two_pool_destinations(spec: dict, cls: str, A, P):
    """indoor pool (buildings and POIs, weight W_indoor of the city) and outdoor pool (weight 1 - W_indoor)
    on the open space of the cells by type. spec["outdoor_pool"][cls] = {"near": {type: share}, "free": {type: share},
    (a key "type1+type2" gives one share to several types together, in proportion to their summed area)
    "free_share": f}: a share 1 - f of the outdoor pool goes to the types of "near" with their shares (time spent in the
    outdoor micro-environments, 01_inputs/time_use/outdoor_microenvironments), each in proportion to its area in the
    cells of the urban fabric around the indoor destinations (Gaussian, outdoor_sigma_m); a share f to the types of
    "free" in proportion to their area anywhere in the domain (parks, sports grounds and squares as destinations of
    leisure). A type without area near the destinations gives its share to the others; without any, the pool falls
    back on the open space of the untyped open-space method."""
    w_in = float(P["_WIN"])
    a_in = A / A.sum()
    OS = P["_OS"]
    pool = spec["outdoor_pool"]
    rule = pool if ("near" in pool or "free" in pool) else (pool.get(cls) or pool.get({"C7": "C5"}.get(cls, cls)) or {})
    near = gaussian_filter(a_in, float(spec.get("outdoor_sigma_m", 300.0)) / 100.0, mode="constant")
    rec = sum(OS.get(k, 0.0) for k in ("park", "rec", "plaza"))
    fabric = (a_in > 0) | (rec > 0) if np.ndim(rec) else (a_in > 0)

    def mix(shares, weight):
        parts = []
        for k, s in (shares or {}).items():
            keys = [t for t in k.split("+") if t in OS]    # "a+b": one share for the types a and b together
            if s > 0 and keys:
                x = sum(OS[t] for t in keys) * weight
                if x.sum() > 0:
                    parts.append((float(s), x / x.sum()))
        tot = sum(s for s, _ in parts)
        return (sum(s * x for s, x in parts) / tot) if tot > 0 else None

    f = float(rule.get("free_share", 0.0))
    a_near = mix(rule.get("near"), near * fabric)
    if a_near is None and rule.get("fallback"):           # e.g. schools without mapped grounds: the shares of adults
        a_near = mix(rule["fallback"], near * fabric)
    a_free = mix(rule.get("free"), np.ones_like(a_in)) if f > 0 else None
    if a_near is None and "_U" in P:                     # no typed open space near the destinations: untyped open space
        u = P["_U"] * near * fabric
        a_near = u / u.sum() if u.sum() > 0 else None
    if a_near is None and a_free is None:
        return A
    if a_free is None:
        a_out = a_near
    elif a_near is None:
        a_out = a_free
    else:
        a_out = (1.0 - f) * a_near + f * a_free
    return w_in * a_in + (1.0 - w_in) * a_out


ACTIVITY_CLASSES = ("C2", "C3", "C4", "C5", "C7")


def attractor(name, cls: str, V, P):
    if isinstance(name, dict) and name and set(name) <= set(ACTIVITY_CLASSES):
        name = name[cls]                      # one specification per activity class (activity-specific): the one of `cls`
    if isinstance(name, dict):
        if name.get("blend"):                 # e.g. {"blend": {"C5": 0.5}, ...}: mixture with the layer of another class
            base = {k: v for k, v in name.items() if k != "blend"}
            A = attractor_spec(base, cls, V, P)
            A = A / max(A.sum(), 1e-12)
            wsum = 0.0
            mix = np.zeros_like(A)
            for c2, w in name["blend"].items():
                B = attractor_spec(base, c2, V, P)
                mix += float(w) * B / max(B.sum(), 1e-12)
                wsum += float(w)
            return (1 - wsum) * A + mix
        return attractor_spec(name, cls, V, P)
    """Destination layer of activity class `cls`:
    nres      GHSL non-residential volume
    poi       Overture POIs of the class
    mix       equal mixture of the normalised poi and nres layers
    fa        floor area of the class (use known)
    fa_poi    equal mixture of the normalised fa and poi layers
    fau       fa, plus for work (C2) the non-residential part of the floor area of unknown use
    fau_poi   equal mixture of normalised fau and poi
    fau_poiw<half>  mixture with POI weight poi_weight(P, half) (default half 5 POIs / 1,000)
    nresh<g>  nres x (GHSL height / 10 m)^g"""
    poi = P.get(cls, np.zeros_like(V))
    if name == "nres":
        return V
    if name == "poi":
        return poi
    if name == "mix":            # equal-weight mixture of the two normalised layers
        return poi / max(poi.sum(), 1e-12) + V / max(V.sum(), 1e-12)
    if name == "fa":             # gross floor area of the class (buildings.py)
        return P.get(f"FA_{cls}", np.zeros_like(V))
    if name == "fa_poi":         # equal-weight mixture of floor area and POIs of the class
        fa = P.get(f"FA_{cls}", np.zeros_like(V))
        return fa / max(fa.sum(), 1e-12) + poi / max(poi.sum(), 1e-12)
    if name.startswith("fau"):
        fa = P.get(f"FA_{cls}", np.zeros_like(V))
        if cls == "C2":
            nu = nonres_unknown(P, V)
            if nu is not None:
                fa = fa + nu
        if name == "fau":
            return fa
        if name == "fau_poi":
            w = 0.5
        elif name.startswith("fau_poiw"):
            w = poi_weight(P, half=float(name[8:] or 5.0))
        else:
            raise ValueError(name)
        if fa.sum() <= 0 and poi.sum() <= 0:
            return V                  # no buildings and no POIs of the class: GHSL non-residential volume
        if poi.sum() <= 0:
            return fa
        if fa.sum() <= 0:
            return poi
        return (1 - w) * fa / fa.sum() + w * poi / poi.sum()
    if name.startswith("nresh"):  # non-residential volume x (building height / 10 m)^gamma, e.g. 'nresh1'
        gamma = float(name[5:] or 1)
        H = P.get("_H", np.full_like(V, 10.0))
        return V * np.power(np.maximum(H, 1.0) / 10.0, gamma)
    raise ValueError(name)


def iso3_of(stem: str) -> str:
    """ISO3 code of a city from its stem ('00572_FIN_Helsinki' -> 'FIN')."""
    parts = stem.split("_")
    return parts[1] if len(parts) > 1 else ""


def network_transit(stem: str, daytype: str, shape):
    """Person-time of the trips on the road and rail network (s05b_network.py), normalised to the
    domain population, or None."""
    f = config.NETWORK / f"{stem}.npz"
    if not f.exists():
        return None
    key = "T_restday" if daytype in ("restday", "saturday", "sunday") else "T_workday"
    with np.load(f, allow_pickle=True) as z:
        if key not in z.files:
            return None
        T = z[key].astype(np.float64)
    return T if T.shape == tuple(shape) else None


def components(stem: str, params: Params | None = None, cell: float = 100.0, layers=None, _memo=None, daytype: str = "workday"):
    params = params or Params()
    if params.country:
        params = params.for_country(iso3_of(stem))
    N, V, P = layers or load_layers(stem)
    out = {"N": N}
    stay_tot = np.zeros_like(N)
    max_cells = int(np.ceil(np.hypot(*N.shape)))
    memo = {} if _memo is None else _memo
    for c, d0 in params.d0.items():
        acls = params.c7_like if c == "C7" else c
        kind = params.k(c)
        key = (json.dumps(params.attractor[c], sort_keys=True), acls, kind, float(d0), float(params.beta.get(c, 1.0)),
               params.radius_factor, params.max_radius_m)
        if key not in memo:
            A = attractor(params.attractor[c], acls, V, P)
            radius = min(params.radius_factor * d0, params.max_radius_m) if kind == "pow" else params.radius_factor * d0
            k = kernel(d0, cell, radius_m=radius, kind=kind, beta=params.beta.get(c, 1.0), max_cells=max_cells)
            memo[key] = allocate(N, A, k)
        D, stay = memo[key]
        out[c] = D + stay          # residents without any reachable destination stay at home
        stay_tot += stay
    T = network_transit(stem, daytype, N.shape) if getattr(params, "transit", "gauss") == "network" else None
    out["_transit"] = "network" if T is not None else "gauss"
    if T is None:              # Gaussian fallback: between home and work place, smoothed
        T = gaussian_filter(0.5 * N + 0.5 * out["C2"], SIGMA_TRAVEL_M / cell, mode="constant")
    if getattr(params, "transit_water_mask", False) and "_W" in P:   # nobody travels on water cells
        T = T * (1.0 - P["_W"])
    T = T * (N.sum() / max(T.sum(), 1e-12))
    out["C6"] = T
    out["_stay_share"] = float(stay_tot.sum() / max(N.sum() * len(params.d0), 1e-12))
    return out


def components_daytypes(stem: str, params: Params | None = None, daytypes=("workday", "restday"), layers=None):
    """{daytype: components}; classes whose destination layer and kernel are the same on both
    day types are computed once."""
    params = (params or Params()).for_country(iso3_of(stem))
    layers = layers or load_layers(stem)
    memo = {}
    return {dt: components(stem, params.for_daytype(dt), layers=layers, _memo=memo, daytype=dt) for dt in daytypes}


def hourly(comp: dict, shares: np.ndarray, hours=range(24)) -> np.ndarray:
    """shares: (24, 7) for C1..C7. Returns (len(hours), ny, nx)."""
    keys = ["N", "C2", "C3", "C4", "C5", "C6", "C7"]
    out = []
    for h in hours:
        s = shares[h]
        P = np.zeros_like(comp["N"])
        for i, k in enumerate(keys):
            if s[i] > 0:
                P += s[i] * comp[k]
        out.append(P)
    return np.stack(out)

def params_from(spec: dict) -> Params:
    """Build Params from a plain dict (e.g. population_allocation_parameters.json leaves used by the network step)."""
    p = Params()
    for k, v in spec.items():
        if k in ("d0", "attractor", "kind", "beta"):
            per_class = isinstance(v, dict) and set(v) <= {"C2", "C3", "C4", "C5", "C7"}
            getattr(p, k).update(v) if per_class else setattr(p, k, {c: v for c in p.d0})
        elif hasattr(p, k):
            setattr(p, k, v)
    return p

