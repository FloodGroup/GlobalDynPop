"""Hourly population fields of a city for validation: computed from the model (parameter
variants) or read from the component GeoTIFFs written by 03_calculate_population_components.py.

    F = Fields(params)                          # compute
    F = Fields(comp_dir="05_outputs/demo/population_components")    # read
    day = F.mean(stem, "workday", [13, 14])     # 100 m array, people per cell
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from stage_2_100m_layers.cities import load_cities
from stage_3_activity_allocation.model import Params, components, hourly, load_layers
from stage_2_100m_layers.time_use import daytype_shares

BANDS = ["N", "C2", "C3", "C4", "C5", "C6", "C7"]


def shares_for(iso3: str, daytype: str, base=None):
    sh, info = daytype_shares(iso3, daytype, base=base)
    if info.get("file") == "V11" and daytype in ("saturday", "sunday"):
        sh, info = daytype_shares(iso3, "restday", base=base)
    return sh, info


class Fields:
    def __init__(self, params: Params | None = None, comp_dir: str | Path | None = None, daytype_dir: str | Path | None = None):
        self.params = params or Params()
        self.comp_dir = Path(comp_dir) if comp_dir else None
        self.daytype_dir = Path(daytype_dir) if daytype_dir else None      # time-use curves (default: the model's)
        self.cities = load_cities().set_index("stem")
        self._stem = None
        self._cache = {}

    def _components(self, stem: str, daytype: str) -> dict:
        kind = "workday" if daytype in ("workday", "alldays") else "restday"
        if self._stem != stem:
            self._cache = {}
            self._stem = stem
        if kind in self._cache:
            return self._cache[kind]
        if self.comp_dir is not None:
            import rasterio
            f = self.comp_dir / f"{stem}.tif"
            with rasterio.open(f) as src:
                arr = src.read().astype(np.float64)
                desc = list(src.descriptions)
            comp = {}
            for i, d in enumerate(desc):
                comp[d] = arr[i]
            out = {"N": comp["C1"]}
            for c in ("C2", "C3", "C4", "C5", "C6", "C7"):
                out[c] = comp.get(f"{c}_rest", comp[c]) if kind == "restday" else comp[c]
            self._cache[kind] = out
        else:
            if "_layers" not in self._cache:
                self._cache["_layers"] = load_layers(stem)
                self._cache["_memo"] = {}
            pc = self.params.for_country(self.cities.loc[stem, "iso3"]).for_daytype(kind)    # country first, then day type
            self._cache[kind] = components(stem, pc, layers=self._cache["_layers"], _memo=self._cache["_memo"], daytype=kind)
        return self._cache[kind]

    def hours(self, stem: str, daytype: str, hours) -> np.ndarray:
        sh, _ = shares_for(self.cities.loc[stem, "iso3"], daytype, base=self.daytype_dir)
        return hourly(self._components(stem, daytype), sh, list(hours))

    def mean(self, stem: str, daytype: str, hours) -> np.ndarray:
        return self.hours(stem, daytype, hours).mean(0)

    def residents(self, stem: str) -> np.ndarray:
        return self._components(stem, "workday")["N"]
