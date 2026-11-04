# -*- coding: utf-8 -*-
"""Stage 2, step 10 (no internet): floor area by use from GlobalBuildingAtlas and the open space of every cell.

    python 02_code/stage_2_100m_layers/10_prepare_buildings_open_space.py [--stems ...] [--stems-file f] [--shard k/n] [--overwrite]

Inputs (100 m grid of the city): GlobalBuildingAtlas sums (01_inputs/buildings/gba, s14_gba.py), the GHSL 2018 net
building height (ghs_building_height), the floor area by use of the Overture / OpenBuildingMap buildings
(01_inputs/buildings/floor_area, s04_buildings.py), the land-use groups of Overture Maps (01_inputs/basemap/land_use,
s13) and, in China, of the Amap AOIs (01_inputs/basemap/land_use_aoi, s13b), permanent water (01_inputs/basemap/
landcover) and the road network (01_inputs/road_network).

Floor area (-> 01_inputs/buildings/floor_area_by_use/<stem>.npz, fa [9, ny, nx]: C1..C7, use unknown, industrial part of
C2, m2; the layout of floor_area):
  total      GlobalBuildingAtlas: footprint x storeys, storeys = max(1, round(height / 3 m)); buildings without a
             height estimate take the mean storeys of the buildings with one in the same cell, else the GHSL net
             height of the cell / 3 m (if >= 2 m), else the city mean; buildings in cells of >= 95 % permanent water
             (ships, barges, false detections) are dropped
  use        the part of the total that the Overture / OpenBuildingMap floor area of the cell covers keeps the use
             composition of that floor area; the rest (buildings that only GlobalBuildingAtlas maps) takes the
             composition of the land use of the cell (Amap AOIs first in China, then Overture land use: residential ->
             C1, commercial / industrial -> C2, education -> C3, hospitals, institutional, religious -> C4, sports and
             parks -> C5, transport land -> C6, cemeteries -> C7); the cell share without land-use polygons stays of
             unknown use (split by the model with the GHSL non-residential share of the built volume)
  -> also 01_inputs/buildings/gba_cells/<stem>.npz: footprint (m2), volume (m3), floor area (m2), mean height (m),
     share of the footprint with an imputed height
Cities without a GlobalBuildingAtlas layer (failed download) keep the floor area of floor_area (copied to floor_area_by_use,
column fallback of the log) and get no gba_cells / open_space file: the model then uses the GHSL footprint and the untyped open-space fallback for them.
Open space (-> 01_inputs/basemap/open_space/<stem>.npz, share of the cell area, float32), on the land part of the cell
outside the building footprints:
  street   road surface of the streets people walk along: length x width, primary / secondary 20 m, tertiary /
           unclassified 12 m, local streets 8 m (motorways and trunk roads excluded)
  parking  parking lots; plaza  pedestrian areas and squares; park  parks and gardens; grass  managed grass;
  rec      sports and recreation grounds; campus  open land of school, university and hospital grounds;
  cons     construction sites; open  the rest of the land outside buildings, roads and the above, except farmland and
           protected natural areas
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as config  # noqa: E402
from stage_2_100m_layers.cities import grid_of, load_cities  # noqa: E402

STOREY_M = 3.0
WATER_DROP = 0.95             # permanent-water share of a cell above which GlobalBuildingAtlas buildings are dropped
WIDTH_M = {"prim_sec": 20.0, "tert": 12.0, "local": 8.0}     # walkable street surface per metre of road
ROAD_GROUP = {45.0: 0, 35.0: 0, 28.0: 1, 24.0: 1, 20.0: 2, 18.0: 2}    # km/h of the routing graph (gdp.network)
# land-use groups -> building use (index into C1..C7; 7 = unknown); IND marks the industrial part of C2
LU_USE = {"RES": 0, "COM": 1, "IND": 1, "EDU": 2, "MED": 3, "PUB": 3, "REC": 4, "PARK": 4, "TRN": 5, "CEM": 6}
AOI_USE = {"AOI_C1": 0, "AOI_C2": 1, "AOI_IND": 1, "AOI_C3": 2, "AOI_C4": 3, "AOI_C5": 4, "AOI_C6": 5}
OUT_FA = config.FLOOR_AREA
OUT_GBA = config.INPUTS / "buildings" / "gba_cells"
OUT_OS = config.BASEMAP / "open_space"


def save_npz(f: Path, **arrays):
    """np.savez_compressed through a temporary file (no half-written file after an interruption)"""
    tmp = f.with_name(f.stem + ".tmp.npz")
    np.savez_compressed(tmp, **arrays)
    tmp.replace(f)


def read_groups(f: Path, shape) -> dict:
    out = {}
    if f.exists():
        with np.load(f) as z:
            for k in z.files:
                if k != "meta":
                    a = z[k]
                    if a.shape == shape:
                        out[k] = a.astype(np.float64) / 16.0
    return out


def road_lengths(stem: str, g):
    """Metres per cell of primary / secondary, tertiary / unclassified and local streets (motorway / trunk apart)."""
    rf = config.ROAD_GRAPHS / f"{stem}.npz"
    ny, nx = g.shape
    L = {k: np.zeros((ny, nx)) for k in ("mot", "prim_sec", "tert", "local")}
    if not rf.exists():
        return L, False
    with np.load(rf, allow_pickle=False) as z:
        p_len, p_time, p_rail = z["p_len"], z["p_time"], z["p_rail"].astype(bool)
        s_n, s_cell, street = z["s_n"].astype(np.int64), z["s_cell"].astype(np.int64), z["street"].astype(np.float64)
    if street.shape != (ny, nx):
        return L, False
    if len(p_len):
        piece = np.repeat(np.arange(len(s_n)), s_n)
        step = np.where(s_n > 0, p_len / np.maximum(s_n, 1), 0.0)[piece]
        speed = np.round(p_len / np.maximum(p_time, 1e-12) / 1000.0, 1)
        grp = np.array([3 if rl else ROAD_GROUP.get(float(s), 2) for s, rl in zip(speed, p_rail)], np.int64)[piece]
        ok = (s_cell >= 0) & (s_cell < ny * nx)
        for j, k in ((0, "mot"), (1, "prim_sec"), (2, "tert")):
            m = ok & (grp == j)
            L[k] = np.bincount(s_cell[m], weights=step[m], minlength=ny * nx).reshape(ny, nx)
    L["local"] = np.maximum(street - L["mot"] - L["prim_sec"] - L["tert"], 0.0)
    return L, True


def city(row: dict) -> dict:
    stem = row["stem"]
    g = grid_of(row)
    ny, nx = g.shape
    shape = (ny, nx)
    info = {"stem": stem}
    lf = config.BASEMAP / "landcover" / f"{stem}.npz"
    water = np.zeros(shape)
    if lf.exists():
        with np.load(lf) as z:
            w = z["pw"].astype(np.float64) / 100.0
        if w.shape == shape:
            water = w
    # ---- GlobalBuildingAtlas: footprint, volume, floor area with imputed heights; cells that are (almost) entirely
    # permanent water (>= WATER_DROP) lose their buildings: ships, barges and other false detections on rivers and
    # harbours (the model places nobody on water in any case)
    gf = config.INPUTS / "buildings" / "gba" / f"{stem}.npz"
    with np.load(gf) as z:
        foot, noh = z["foot_m2"].astype(np.float64), z["foot_noh_m2"].astype(np.float64)
        volh, floorh = z["vol_h_m3"].astype(np.float64), z["floor_h_m2"].astype(np.float64)
    wet = water >= WATER_DROP
    info["gba_dropped_on_water_km2"] = round(float(foot[wet].sum()) / 1e6, 4)
    for a in (foot, noh, volh, floorh):
        a[wet] = 0.0
    fh = np.clip(foot - noh, 0.0, None)
    Hc = float(volh.sum() / fh.sum()) if fh.sum() > 0 else 6.0
    Sc = float(floorh.sum() / fh.sum()) if fh.sum() > 0 else 2.0
    hgf = config.ghsl_file("height", stem)
    Hg = np.load(hgf).astype(np.float64) if hgf.exists() else np.zeros(shape)
    if Hg.shape != shape:
        Hg = np.zeros(shape)
    with np.errstate(invalid="ignore", divide="ignore"):
        h_cell = np.where(fh > 0, volh / fh, np.nan)
        s_cell = np.where(fh > 0, floorh / fh, np.nan)
    h_imp = np.where(np.isfinite(h_cell), h_cell, np.where(Hg >= 2.0, Hg, Hc))
    s_imp = np.where(np.isfinite(s_cell), s_cell, np.where(Hg >= 2.0, np.maximum(1.0, np.round(Hg / STOREY_M)), Sc))
    vol = volh + noh * h_imp
    floor = floorh + noh * s_imp
    info.update(gba_floor_km2=round(float(floor.sum()) / 1e6, 3), gba_foot_km2=round(float(foot.sum()) / 1e6, 3),
                share_foot_imputed=round(float(noh.sum() / max(foot.sum(), 1e-9)), 4), H_city=round(Hc, 2),
                storeys_city=round(Sc, 2))
    # ---- use composition
    ff = config.INPUTS / "buildings" / "floor_area_legacy" / f"{stem}.npz"
    if ff.exists():
        with np.load(ff) as z:
            fa = z["fa"].astype(np.float64)
    else:
        fa = np.zeros((9, ny, nx))
    F_ex = fa[:8].sum(0)
    matched = np.minimum(floor, F_ex)
    excess = floor - matched
    with np.errstate(invalid="ignore", divide="ignore"):
        sh_ex = np.where(F_ex > 0, fa[:8] / np.where(F_ex > 0, F_ex, 1.0), 0.0)
        ind_ex = np.where(F_ex > 0, fa[8] / np.where(F_ex > 0, F_ex, 1.0), 0.0)
    ov = read_groups(config.BASEMAP / "land_use" / f"{stem}.npz", shape)
    aoi = read_groups(config.BASEMAP / "land_use_aoi" / f"{stem}.npz", shape)
    aoi_tot = np.clip(sum(aoi.values()) if aoi else np.zeros(shape), 0.0, 1.0)
    comp = np.zeros((8, ny, nx))
    comp_ind = np.zeros(shape)
    for k, a in aoi.items():
        if k in AOI_USE:
            comp[AOI_USE[k]] += a
            if k == "AOI_IND":
                comp_ind += a
    rest = 1.0 - aoi_tot
    for k, a in ov.items():
        if k in LU_USE:
            comp[LU_USE[k]] += rest * a
            if k == "IND":
                comp_ind += rest * a
    known = comp.sum(0)
    comp[7] = np.clip(1.0 - known, 0.0, 1.0)              # cell share without land-use evidence: use unknown
    s = comp.sum(0)
    comp /= np.where(s > 0, s, 1.0)
    comp_ind /= np.where(s > 0, s, 1.0)
    fa6 = np.zeros((9, ny, nx), np.float32)
    fa6[:8] = (matched[None] * sh_ex + excess[None] * comp).astype(np.float32)
    fa6[8] = (matched * ind_ex + excess * comp_ind).astype(np.float32)
    info.update(classified_floor_area_km2=round(float(F_ex.sum()) / 1e6, 3), excess_km2=round(float(excess.sum()) / 1e6, 3),
                excess_unknown_km2=round(float((excess * comp[7]).sum()) / 1e6, 3),
                by_class_km2=[round(float(x) / 1e6, 3) for x in fa6.reshape(9, -1).sum(1)])
    # ---- open space
    land = np.clip(1.0 - water, 0.0, 1.0)
    foot_sh = np.minimum(foot / g.cell ** 2, land)
    free = np.clip(land - foot_sh, 0.0, 1.0)                 # land outside the footprints
    L, has_roads = road_lengths(stem, g)
    street = sum(L[k] * WIDTH_M[k] for k in WIDTH_M) / g.cell ** 2
    street = np.minimum(street, free)
    G = lambda k: ov.get(k, np.zeros(shape))                 # noqa: E731
    with np.errstate(invalid="ignore", divide="ignore"):
        open_frac = np.where(land > 0, free / land, 0.0)       # open part of a polygon, buildings spread evenly
    typed = {"parking": G("PRK"), "plaza": G("PED"), "park": G("PARK"), "grass": G("GRS"), "rec": G("REC"),
             "campus": np.maximum(G("EDU") + G("MED"), aoi.get("AOI_C3", np.zeros(shape))), "cons": G("CON")}
    typed = {k: v * open_frac for k, v in typed.items()}
    room = np.clip(free - street, 0.0, 1.0)
    tsum = sum(typed.values())
    scale = np.where(tsum > room, room / np.where(tsum > 0, tsum, 1.0), 1.0)
    typed = {k: v * scale for k, v in typed.items()}
    natural = np.clip((G("AGR") + G("NAT")) * open_frac, 0.0, 1.0)
    other = np.clip(room - sum(typed.values()) - natural, 0.0, 1.0)
    os_ = {"street": street, **typed, "open": other}
    info.update(roads=has_roads, open_space_km2={k: round(float(v.sum()) * g.cell ** 2 / 1e6, 3) for k, v in os_.items()})
    # ---- write
    for d in (OUT_FA, OUT_GBA, OUT_OS):
        d.mkdir(parents=True, exist_ok=True)
    save_npz(OUT_FA / f"{stem}.npz", fa=fa6)
    with np.errstate(invalid="ignore", divide="ignore"):
        hmean = np.where(foot > 0, vol / np.where(foot > 0, foot, 1.0), 0.0)
        shimp = np.where(foot > 0, noh / np.where(foot > 0, foot, 1.0), 0.0)
    save_npz(OUT_GBA / f"{stem}.npz", foot_m2=foot.astype(np.float32), vol_m3=vol.astype(np.float32),
             floor_m2=floor.astype(np.float32), h_mean=hmean.astype(np.float32), share_imputed=shimp.astype(np.float32))
    save_npz(OUT_OS / f"{stem}.npz", meta=np.array(json.dumps({"widths_m": WIDTH_M, "storey_m": STOREY_M})),
             **{k: v.astype(np.float32) for k, v in os_.items()})
    return info


def fallback(row: dict) -> dict:
    """no GlobalBuildingAtlas layer: the floor area of floor_area is kept (classified building-use inputs for this city)"""
    stem = row["stem"]
    OUT_FA.mkdir(parents=True, exist_ok=True)
    ff = config.INPUTS / "buildings" / "floor_area_legacy" / f"{stem}.npz"
    if ff.exists():
        with np.load(ff) as z:
            save_npz(OUT_FA / f"{stem}.npz", fa=z["fa"].astype(np.float32))
    for d in (OUT_GBA, OUT_OS):
        (d / f"{stem}.npz").unlink(missing_ok=True)
    return {"stem": stem, "fallback": "no GlobalBuildingAtlas layer: floor_area kept, no open space by type",
            "floor_area": ff.exists()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--stems-file")
    ap.add_argument("--shard")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--fallback", action="store_true",
                    help="cities without a GlobalBuildingAtlas layer: keep the floor area of floor_area (else skipped)")
    a = ap.parse_args(argv)
    c = load_cities()
    stems = list(a.stems or [])
    if a.stems_file:
        stems += [l.strip() for l in open(a.stems_file, encoding="utf-8") if l.strip()]
    if stems:
        c = c[c.stem.isin(stems)]
    c = c.assign(_cells=c.nx * c.ny).sort_values("_cells", ascending=False)
    if a.shard:
        k, n = map(int, a.shard.split("/"))
        c = c.iloc[k::n]
    log = OUT_FA / f"_stats_{(a.shard or '0/1').replace('/', 'of')}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    errors = 0
    for row in c.to_dict("records"):
        stem = row["stem"]
        has_gba = (config.INPUTS / "buildings" / "gba" / f"{stem}.npz").exists()
        if (OUT_FA / f"{stem}.npz").exists() and (OUT_OS / f"{stem}.npz").exists() and not a.overwrite:
            continue
        t0 = time.time()
        if not has_gba:
            if not a.fallback:
                print(json.dumps({"stem": stem, "skipped": "no GlobalBuildingAtlas layer"}), flush=True)
                continue
            if (OUT_FA / f"{stem}.npz").exists() and not a.overwrite:
                continue
            info = fallback(row)
        else:
            try:
                info = city(row)
            except Exception as e:  # noqa: BLE001
                errors += 1
                print(json.dumps({"stem": stem, "error": repr(e)}), flush=True)
                continue
        info["s"] = round(time.time() - t0, 1)
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(info) + "\n")
        print(json.dumps(info), flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
