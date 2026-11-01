"""OpenBuildingMap (OBM) occupancy and height for Overture buildings.

Input: the OBM buildings of a city as returned by open_building_map_reader.Reader.extract_city (internal
point in the city's UTM zone, footprint area, occupancy, height code, OBM id).

Matching: an OBM building is assigned to the Overture footprint that contains its internal
point (point_on_surface); when several OBM buildings fall in one Overture footprint, the
largest one (then the smaller OBM id) is used. Dynamic_POP's original matching program is
not part of its code package (P2-3); a local OBM matching check compares this rule with
the OBM ids stored in the original step-04 buildings of the three sample cities.

Use (as in the original step 03): an OBM occupancy other than UNK and the agricultural
codes AGR* decides the class through classification_rules.json["obm"]; generic MIX and
MIX1-MIX6 are split by floor area with configuration/mixed_use.json (MIX -> C7; MIX1/4 C1 70 %
C2 30 %; MIX2/6 C1 30 % C2 70 %; MIX3/5 C2).

Heights (OBM "height" field, GEM building taxonomy v3): H:n storeys above ground (exact),
HBET:a-b a range of storeys, HHT:x height in metres; basement codes (HBEX, HBAPP, HBBET)
are not used because the other height sources (Overture, 3D-GloBFP) are above ground.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

_NUM = r"(?:\d+(?:\.\d*)?|\.\d+)"
CONFIG = Path(__file__).resolve().parent / "rules" / "mixed_use.json"


def points(df: pd.DataFrame):
    return shapely.points(df["x"].to_numpy(float), df["y"].to_numpy(float))


def match(geoms, obm_df: pd.DataFrame, obm_pts=None):
    """Row of obm_df for every building (-1 if none) and the number of OBM points inside."""
    n = len(geoms)
    pick = np.full(n, -1, dtype=np.int64)
    count = np.zeros(n, dtype=np.int64)
    if obm_pts is None:
        obm_pts = points(obm_df) if len(obm_df) else np.array([], dtype=object)
    if not len(obm_pts) or not n:
        return pick, count
    tree = shapely.STRtree(geoms)
    pi, bi = tree.query(obm_pts, predicate="within")
    if not len(pi):
        return pick, count
    np.add.at(count, bi, 1)
    area = obm_df["area"].to_numpy(float)
    ids = obm_df["obm_id"].to_numpy()
    order = np.lexsort((ids[pi], -area[pi], bi))
    _, first = np.unique(bi[order], return_index=True)
    sel = order[first]
    pick[bi[sel]] = pi[sel]
    return pick, count


def normalise(occ) -> np.ndarray:
    return pd.Series(np.asarray(occ, dtype=object)).fillna("").astype(str).str.strip().str.upper().to_numpy()


def usable_occupancy(occ_upper: np.ndarray, rules: dict) -> np.ndarray:
    o = pd.Series(occ_upper)
    ok = (o != "") & (o != "UNK") & (o != "NAN") & ~o.str.startswith("AGR") & o.str.lower().isin(rules["open_building_map"].keys())
    return ok.to_numpy()


def class_shares(occ_upper: np.ndarray, rules: dict, mixed: dict | None = None):
    """-> (main class 1..7 used for statistics, shares [n, 7]) for usable OBM occupancies."""
    mixed = mixed or json.loads(CONFIG.read_text(encoding="utf-8"))["fractions"]
    n = len(occ_upper)
    shares = np.zeros((n, 7))
    lut = {}
    for o in pd.unique(occ_upper):
        c = rules["open_building_map"][o.lower()]
        s = np.zeros(7)
        if c == "MIX":
            for k, v in mixed[o if o in mixed else "MIX"].items():
                s[int(k[1:]) - 1] += v
        else:
            s[int(c[1:]) - 1] = 1.0
        lut[o] = s
    for o, s in lut.items():
        shares[occ_upper == o] = s
    main = shares.argmax(axis=1) + 1
    return main, shares


def parse_height(values):
    """-> (exact storeys H:n, range low, range high, height in metres HHT) as float arrays."""
    values = pd.Series(np.asarray(values, dtype=object)).fillna("").astype(str).to_numpy()
    table = {}
    for v in pd.unique(values):
        ex = lo = hi = hm = np.nan
        for tag in str(v).upper().split("+"):
            tag = tag.strip()
            m = re.fullmatch(rf"H\s*:\s*({_NUM})", tag)
            if m:
                ex = float(m.group(1)) if not np.isfinite(ex) else max(ex, float(m.group(1)))
                continue
            m = re.fullmatch(rf"HBET\s*:\s*({_NUM})\s*-\s*({_NUM})", tag)
            if m:
                a, b = float(m.group(1)), float(m.group(2))
                if 0 <= a <= b:
                    lo, hi = a, b
                continue
            m = re.fullmatch(rf"HHT\s*:\s*({_NUM})", tag)
            if m and float(m.group(1)) > 0:
                hm = float(m.group(1)) if not np.isfinite(hm) else max(hm, float(m.group(1)))
        table[v] = (ex, lo, hi, hm)
    if not len(values):
        z = np.zeros(0)
        return z, z, z, z
    arr = np.array([table[v] for v in values], dtype=float)
    return arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
