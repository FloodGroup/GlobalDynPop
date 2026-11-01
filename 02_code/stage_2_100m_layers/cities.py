"""City list and model domains.

Cities are the urban centres of the GHSL Urban Centre Database R2024A (GHS-UCDB 2025, V1.2)
with a 2025 population of at least 300,000, the size threshold the UN World Urbanization
Prospects uses for urban agglomerations. An urban centre is a contiguous set of 1 km cells
with >= 1,500 inhabitants/km2 and >= 50,000 inhabitants in total (Degree of Urbanisation),
so the list is defined in the same way everywhere and is independent of national city
definitions and of WorldMove.

Model domain of a city: the bounding box of the urban-centre polygon in a local Lambert
azimuthal equal-area projection (centred on the polygon centroid), enlarged by BUFFER_M on
every side and snapped to the 100 m cell size. The margin brings the suburban commuting
belt into the domain; results are reported for the urban-centre polygon.
"""
from __future__ import annotations

import os

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import pyogrio
import shapely
from pyproj import Transformer

import stage_1_data_inputs.configuration as configuration
from stage_2_100m_layers.grid import Grid, laea_crs

TAIWAN = "China, Taiwan Province of China"


def fix_text(s):
    """UCDB strings are UTF-8 read as Latin-1 (e.g. 'MÃ©xico'); repair when possible."""
    if not isinstance(s, str):
        return ""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def slug(s: str) -> str:
    from unidecode import unidecode
    s = unidecode(unicodedata.normalize("NFKC", s))
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s[:40] or "UC"


def country_names_zh(v11_root: Path | None) -> dict:
    """ISO3 -> Chinese country name, from external V11 time-use folder names (NNN_ISO_English_ChineseName).

    Layout under DYNAMIC_POPULATION_V11_ROOT (override with DYNAMIC_POPULATION_V11_TIMEUSE_REL, default results/time_use):
      <V11>/<DYNAMIC_POPULATION_V11_TIMEUSE_REL>/<NNN_ISO_English_ChineseName>/
    """
    out = {}
    if v11_root and Path(v11_root).is_dir():
        rel = os.environ.get("DYNAMIC_POPULATION_V11_TIMEUSE_REL", "results/time_use")
        folder = Path(v11_root).joinpath(*Path(rel).parts)
        if not folder.is_dir():
            return out
        for p in folder.iterdir():
            parts = p.name.split("_")
            if len(parts) >= 4 and len(parts[1]) == 3:
                out[parts[1]] = parts[-1]
    out.update({"TWN": "台湾（中国）", "HKG": "中国香港", "MAC": "中国澳门", "CHN": "中国", "TGO": "多哥", "SLE": "塞拉利昂",
                "SRB": "塞尔维亚", "PSE": "巴勒斯坦", "DJI": "吉布提", "GNB": "几内亚比绍", "LVA": "拉脱维亚",
                "TTO": "特立尼达和多巴哥", "PNG": "巴布亚新几内亚"})
    return out


def read_ucdb(path=configuration.UCDB) -> "pd.DataFrame":
    import country_converter as coco
    import logging
    logging.getLogger("country_converter").setLevel(logging.ERROR)
    uc = pyogrio.read_dataframe(path, layer=configuration.UCDB_LAYER)
    uc["name"] = uc["GC_UCN_MAI_2025"].map(fix_text)
    uc["names_all"] = uc["GC_UCN_LIS_2025"].map(fix_text)
    uc["country"] = uc["GC_CNT_UNN_2025"].map(fix_text)
    cn = sorted(set(uc.country))
    iso = dict(zip(cn, coco.CountryConverter().convert(cn, to="ISO3", not_found=None)))
    iso[TAIWAN] = "TWN"
    uc["iso3"] = uc.country.map(iso)
    uc.loc[uc.country == TAIWAN, "country"] = "Taiwan (China)"
    return uc


def make_city_table(pop_min=configuration.POP_MIN, buffer_m=configuration.BUFFER_M, cell=configuration.CELL, v11_root=None) -> pd.DataFrame:
    uc = read_ucdb()
    uc = uc[uc["GC_POP_TOT_2025"].astype(float) >= pop_min].copy()
    zh = country_names_zh(v11_root)
    to_ll = Transformer.from_crs(uc.crs, 4326, always_xy=True)
    rows = []
    for r in uc.itertuples():
        g = r.geometry
        c = shapely.centroid(g)
        lon0, lat0 = to_ll.transform(c.x, c.y)
        crs = laea_crs(lon0, lat0)
        tr = Transformer.from_crs(uc.crs, crs, always_xy=True)
        poly = shapely.transform(shapely.segmentize(g, 200.0), lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
        x0, y0, x1, y1 = poly.bounds
        x0 = np.floor((x0 - buffer_m) / cell) * cell
        y0 = np.floor((y0 - buffer_m) / cell) * cell
        x1 = np.ceil((x1 + buffer_m) / cell) * cell
        y1 = np.ceil((y1 + buffer_m) / cell) * cell
        nx, ny = int(round((x1 - x0) / cell)), int(round((y1 - y0) / cell))
        uid = int(r.ID_UC_G0)
        rows.append(dict(
            uc_id=uid, stem=f"{uid:05d}_{r.iso3 or 'XXX'}_{slug(r.name)}", name=r.name, names_all=r.names_all,
            country=r.country, iso3=r.iso3, country_zh=zh.get(r.iso3, ""), pop2025=float(r.GC_POP_TOT_2025),
            uc_area_km2=float(r.GC_UCA_KM2_2025), lon0=round(lon0, 6), lat0=round(lat0, 6), x0=x0, y1=y1, nx=nx, ny=ny,
            cell=cell, domain_km2=nx * ny * cell * cell / 1e6, uc_wkt_laea=shapely.to_wkt(poly, rounding_precision=1)))
    df = pd.DataFrame(rows).sort_values("pop2025", ascending=False).reset_index(drop=True)
    return df


def grid_of(row) -> Grid:
    return Grid(float(row["lon0"]), float(row["lat0"]), float(row["x0"]), float(row["y1"]), int(row["nx"]), int(row["ny"]),
                float(row.get("cell", 100.0)))


def uc_mask(row) -> np.ndarray:
    """Boolean mask of the 100 m cells whose centre lies inside the urban-centre polygon."""
    g = grid_of(row)
    poly = shapely.from_wkt(row["uc_wkt_laea"])
    xs, ys = g.centres()
    X, Y = np.meshgrid(xs, ys)
    m = shapely.contains_xy(poly, X.ravel(), Y.ravel())
    return m.reshape(g.shape)


def load_cities(path=None) -> pd.DataFrame:
    path = Path(path or configuration.CITY_TABLE)
    return pd.read_csv(path, encoding="utf-8-sig")
