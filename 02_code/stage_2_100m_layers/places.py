"""Classify local POI records and aggregate counts to the model grid."""
from __future__ import annotations

import numpy as np

import pandas as pd

from stage_2_100m_layers.cities import grid_of

MIN_CONFIDENCE = 0.5

CLASSES = ["C2", "C3", "C4", "C5", "C6"]

TOP_TO_CLASS = {
    "services_and_business": "C2", "shopping": "C2", "lifestyle_services": "C2",
    "education": "C3",
    "health_care": "C4", "community_and_government": "C4",
    "food_and_drink": "C5", "arts_and_entertainment": "C5", "sports_and_recreation": "C5",
    "cultural_and_historic": "C5", "lodging": "C5",
    "travel_and_transportation": "C6",
}

PARK_BASIC = {"park", "playground", "garden", "nature_reserve", "beach", "plaza"}

CLOSED = {"permanently_closed", "temporarily_closed"}

def classify(d: pd.DataFrame) -> pd.Series:
    cls = d.top.map(TOP_TO_CLASS)
    park = d.basic.isin(PARK_BASIC)
    cls = cls.where(~park, "C5")
    keep = (~d.status.isin(CLOSED)) & (d.confidence.fillna(0) >= MIN_CONFIDENCE)
    return cls.where(keep)

def city_places(reader, row: dict) -> dict:
    """Counts of places per 100 m cell and class for one city (dict of float32 arrays)."""
    from pyproj import Transformer
    g = grid_of(row)
    lon0, lat0, lon1, lat1 = g.lonlat_bounds(0.01)
    d = reader.read_bbox(lon0, lat0, lon1, lat1)
    d["cls"] = classify(d)
    out = {c: np.zeros(g.shape, np.float32) for c in CLASSES}
    stats = {"read": int(len(d))}
    if len(d):
        x, y = Transformer.from_crs(4326, g.crs, always_xy=True).transform(d.lon.to_numpy(), d.lat.to_numpy())
        r, c = g.index(x, y)
        ok = r >= 0
        for k in CLASSES:
            m = ok & (d.cls.to_numpy() == k)
            if m.any():
                out[k] = np.bincount(r[m] * g.nx + c[m], minlength=g.nx * g.ny).reshape(g.shape).astype(np.float32)
            stats[k] = int(m.sum())
        stats["in_domain"] = int(ok.sum())
        stats["unclassified"] = int((ok & d.cls.isna().to_numpy()).sum())
    return out, stats
