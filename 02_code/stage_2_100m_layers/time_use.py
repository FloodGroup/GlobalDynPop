"""Read hourly location shares by country and day type.

Each matrix contains 24 local hours and seven location classes, C1-C7. Supplied
matrices and their source index are in
04_intermediate/demo/stage_2/hourly_location_shares/. Their derivation is documented
in 04_intermediate/demo/stage_2/time_use/time_use.pdf.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

import stage_1_data_inputs.configuration as configuration

CLASS_COLS = ["residential", "commercial_industrial", "education", "medical_public", "leisure", "transportation", "other"]
CLASSES = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]


@lru_cache(maxsize=1)
def _v11_index(root: str):
    """Read the V11 master index. Override relative path with DYNAMIC_POPULATION_V11_INDEX_REL
    (default results/model_read_index.csv under DYNAMIC_POPULATION_V11_ROOT / TIMEUSE/V11)."""
    rel = os.environ.get("DYNAMIC_POPULATION_V11_INDEX_REL", "results/model_read_index.csv")
    ix = pd.read_csv(Path(root).joinpath(*Path(rel).parts), encoding="utf-8-sig")
    return ix


def v11_national(iso3: str, root: Path | None = None) -> np.ndarray:
    """(24, 7) shares for the most common V11 matrix of the country."""
    root = Path(root or configuration.TIMEUSE / "V11")
    ix = _v11_index(str(root))
    sub = ix[ix.iso3 == iso3]
    if not len(sub):
        raise KeyError(iso3)
    f = sub.matrix_file.value_counts().index[0]
    m = pd.read_csv(root / f, encoding="utf-8-sig")
    a = m[CLASS_COLS].to_numpy(float)
    a = a / a.sum(axis=1, keepdims=True)
    return a


# The environment variable overrides the configured directory of hourly-share CSVs.
DAYTYPE_DIR = Path(os.environ.get("DYNAMIC_POPULATION_DAYTYPE_DIR") or getattr(configuration, "DAYTYPE_DIR", configuration.TIMEUSE / "daytype"))


def _read_matrix(f: Path) -> np.ndarray:
    m = pd.read_csv(f, encoding="utf-8-sig")
    a = m[CLASS_COLS].to_numpy(float)
    return a / a.sum(axis=1, keepdims=True)


@lru_cache(maxsize=4)
def _daytype_index(base: Path | None = None):
    ix = (base or DAYTYPE_DIR) / "location_share_sources.csv"
    if not ix.exists():
        return None
    t = pd.read_csv(ix, encoding="utf-8-sig", keep_default_na=False)
    return t


def daytype_shares(iso3: str, daytype: str = "workday", base: Path | None = None):
    """Return (24, 7) shares and source metadata for a country and day type.

    Accepted day types are workday, restday, saturday, sunday and alldays. Read
    the source index first, then try the conventional CSV filename. The final
    fallback requires an external V11 national-matrix package.
    base overrides DAYTYPE_DIR, the folder containing the share CSVs.
    """
    base = Path(base) if base else DAYTYPE_DIR
    ix = _daytype_index(base)
    if ix is not None:
        sub = ix[(ix.iso3 == iso3) & (ix.daytype == daytype)]
        if len(sub):
            r = sub.iloc[0]
            return _read_matrix(base / r["file"]), {"file": r["file"], "method": r.get("method", "index"),
                                                   "donors": r.get("donors", "")}
    f = base / f"{iso3}_{dict(alldays='all_days', restday='rest_day').get(daytype, daytype)}_location_shares.csv"
    if f.exists():
        return _read_matrix(f), {"file": f.name, "method": "own"}
    return v11_national(iso3), {"file": "V11", "method": "average day (no day-type curve)"}
