"""City model: components and hourly population.

    P(x, h, tau) = s_C1(h, tau) N(x) + sum_{c in C2..C5, C7} s_c(h, tau) D_c(x) + s_C6(h, tau) T(x)

N      residents (GHS-POP 2025, 100 m)
D_c    residents redistributed to the destinations of activity class c (gravity.allocate)
T      people travelling, estimated from trip person-time assigned to the road and rail
       network for each day type (network.py, 02_calculate_in_transit_population.py).
       The fallback uses the mean of resident and work-destination distributions,
       smoothed with a Gaussian of SIGMA_TRAVEL.
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

import stage_1_data_inputs.configuration as configuration
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
    transit: str = "gauss"       # people travelling (C6): 'network' = road / rail assignment of 04_intermediate/demo/stage_3/in_transit_population/<stem>.npz
                                 # (02_calculate_in_transit_population.py) where present, else the v1 approximation; 'gauss' = v1 approximation

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
                for k2, v2 in val.items():
                    if isinstance(v2, dict):
                        q.restday.setdefault(k2, {}).update(v2)
                    else:
                        q.restday[k2] = v2
            elif key in ("d0", "attractor", "kind", "beta"):
                classes = set(q.d0)
                per_class = isinstance(val, dict) and len(val) > 0 and set(val) <= classes
                cur = getattr(q, key)
                if per_class:
                    if isinstance(cur, dict):
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
    Experiments: DYNAMIC_POPULATION_BUILDINGS_DIR and DYNAMIC_POPULATION_PLACES_AMAP_DIR replace 04_intermediate/demo/stage_2/buildings/floor_area_by_use and 04_intermediate/demo/stage_2/point_of_interest_counts/china."""
    N = np.load(configuration.ghsl_file("pop", stem)).astype(np.float64)
    V = np.load(configuration.ghsl_file("vol_nres", stem)).astype(np.float64)
    P = {}
    p = configuration.POI_OVERTURE / f"{stem}.npz"
    if p.exists():
        with np.load(p) as z:
            P = {k: z[k].astype(np.float64) for k in z.files}
    o = configuration.POI_OSM / f"{stem}.npz"
    if o.exists():                       # OpenStreetMap POIs
        with np.load(o) as z:
            for k in z.files:
                P[f"OSM_{k}"] = z[k].astype(np.float64)
    a = Path(os.environ.get("DYNAMIC_POPULATION_PLACES_AMAP_DIR") or (configuration.POI_CHINA)) / f"{stem}.npz"
    if a.exists():                       # Amap POIs (tools/amap, China)
        with np.load(a) as z:
            for k in z.files:
                P[f"AMAP_{k}"] = z[k].astype(np.float64)
    h = configuration.ghsl_file("height", stem)
    if h.exists():
        P["_H"] = np.load(h).astype(np.float64)
    vt = configuration.ghsl_file("vol", stem)
    if vt.exists():
        P["_VT"] = np.load(vt).astype(np.float64)
    b = Path(os.environ.get("DYNAMIC_POPULATION_BUILDINGS_DIR") or (configuration.FLOOR_AREA)) / f"{stem}.npz"
    if b.exists():
        with np.load(b) as z:
            fa = z["fa"].astype(np.float64)
        for i in range(7):
            P[f"FA_C{i + 1}"] = fa[i]
        if fa.shape[0] > 7:
            P["FA_UNK"] = fa[7]
        if fa.shape[0] > 8:
            P["FA_IND"] = fa[8]
    P["_N"] = N
    return N, V, P


POI_CLASSES = ("C2", "C3", "C4", "C5", "C6")


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
    return r * unk


def poi_layer(source: str, cls: str, P, V, shop_w=None):
    """POI counts of the class from one source or the sum of several ('overture', 'osm',
    'amap', 'overture+osm', ...). 'auto': Amap where the city has Amap POIs (China, s08);
    otherwise Overture, plus OpenStreetMap where Overture has fewer than 1 POI per 1,000
    residents and OpenStreetMap has more POIs than Overture.
    shop_w (C2, Amap layers with the work-place / shop split from China POI prep): the C2 POIs of
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


def attractor_layer(spec: dict, cls: str, V, P):
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
    sig = float(spec.get("poi_sigma_m", 0.0))
    if sig > 0 and poi.sum() > 0:
        poi = _gf(poi, sig / 100.0, mode="constant")
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


ACTIVITY_CLASSES = ("C2", "C3", "C4", "C5", "C7")


def attractor(name, cls: str, V, P):
    if isinstance(name, dict) and name and set(name) <= set(ACTIVITY_CLASSES):
        name = name[cls]                      # one specification per activity class (model v4): the one of `cls`
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
    """Person-time of the trips on the road and rail network (02_calculate_in_transit_population.py), normalised to the
    domain population, or None."""
    f = configuration.NETWORK / f"{stem}.npz"
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
    if T is None:              # v1: between home and work place, smoothed
        T = gaussian_filter(0.5 * N + 0.5 * out["C2"], SIGMA_TRAVEL_M / cell, mode="constant")
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

