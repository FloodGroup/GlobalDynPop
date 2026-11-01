"""Write one single-band population GeoTIFF per city, day type and local hour.

Outputs: <out>/<city>/<daytype>/<city>_<daytype>_hour_<HH>.tif.
The index contains one row per hourly file. Values are people per 100 m cell.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as configuration
from stage_2_100m_layers.cities import load_cities
from stage_2_100m_layers.time_use import daytype_shares

CLASSES = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]


def parse_hours(value):
    hours = []
    for part in value.split(","):
        if "-" in part:
            first, last = map(int, part.split("-"))
            if first > last:
                raise ValueError("Hour ranges must be increasing")
            hours.extend(range(first, last + 1))
        else:
            hours.append(int(part))
    if not hours or any(h < 0 or h > 23 for h in hours):
        raise ValueError("Hours must be in the range 0-23")
    return sorted(set(hours))


def hourly_path(out, stem, daytype, hour):
    label = configuration.DAYTYPE_NAMES.get(daytype, daytype)
    return Path(out) / stem / label / f"{stem}_{label}_hour_{hour:02d}.tif"


def render(comp_tif, shares, hours, out, stem, daytype="workday"):
    import rasterio
    rest = daytype in ("restday", "saturday", "sunday")
    with rasterio.open(comp_tif) as src:
        profile = src.profile.copy()
        descriptions = list(src.descriptions)
        indices = [descriptions.index(f"{c}_rest" if rest and f"{c}_rest" in descriptions else c) + 1 for c in CLASSES]
        components = src.read(indices).astype(np.float64)
    profile.update(count=1, dtype="float32")
    for key in ("predictor", "zlevel"):
        profile.pop(key, None)
    sums = {}
    for hour in hours:
        target = hourly_path(out, stem, daytype, hour)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp.tif")
        dst = rasterio.open(temporary, "w", **dict(profile, compress="DEFLATE", predictor=3, zlevel=6))
        values = np.tensordot(shares[hour], components, axes=1).astype(np.float32)
        with dst:
            dst.write(values, 1)
            dst.set_band_description(1, f"hour_{hour:02d}")
            dst.update_tags(daytype=daytype, hour=str(hour), time_basis="local time",
                            time_start=f"{hour:02d}:00", time_end=f"{hour + 1:02d}:00",
                            units="people per 100 m cell", shares=json.dumps(shares[hour].round(6).tolist()),
                            people_total=str(float(values.sum(dtype=np.float64))))
        temporary.replace(target)
        sums[hour] = float(values.sum(dtype=np.float64))
    return sums


def write_index(out, cities, daytypes, hours=None):
    import pandas as pd
    import rasterio
    rows = []
    for stem in cities.index:
        for daytype in daytypes:
            for hour in range(24) if hours is None else hours:
                path = hourly_path(out, stem, daytype, hour)
                if not path.exists():
                    continue
                with rasterio.open(path) as src:
                    if src.count != 1 or src.descriptions != (f"hour_{hour:02d}",):
                        raise ValueError(f"Unexpected hourly raster layout: {path}")
                    total = float(src.read(1).sum(dtype=np.float64))
                    rows.append(dict(stem=stem, name=cities.loc[stem, "name"], country=cities.loc[stem, "country"],
                                     iso3=cities.loc[stem, "iso3"], daytype=daytype, hour=hour,
                                     time_start=f"{hour:02d}:00", time_end=f"{hour + 1:02d}:00", time_basis="local time",
                                     file=path.relative_to(out.parent).as_posix(), band=1,
                                     units="people per 100 m cell", nx=src.width, ny=src.height, people_domain=total))
    index = out.parent / "hourly_population_index.csv" if out.name == "hourly_population" else out / "hourly_population_index.csv"
    if rows:
        pd.DataFrame(rows).sort_values(["stem", "daytype", "hour"]).to_csv(index, index=False, encoding="utf-8-sig")
    print(json.dumps({"index": str(index), "hourly_files": len(rows)}), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stems", nargs="*")
    parser.add_argument("--stems-file")
    parser.add_argument("--daytypes", nargs="+", default=["workday", "restday"])
    parser.add_argument("--hours", default="0-23")
    parser.add_argument("--comp", default=str(configuration.COMPONENTS))
    parser.add_argument("--out", default=str(configuration.HOURLY))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--order", choices=["small", "large", "list"], default="small")
    parser.add_argument("--index-only", action="store_true")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(configuration.ROOT / "03_run/runtime"))
    import work_queue
    hours = parse_hours(args.hours)
    cities = load_cities().set_index("stem")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.index_only:
        write_index(out, cities, args.daytypes, hours)
        return
    stems = list(args.stems or [])
    if args.stems_file:
        stems += Path(args.stems_file).read_text(encoding="utf-8-sig").split()
    component_dir = Path(args.comp)
    if not stems:
        stems = [p.stem for p in sorted(component_dir.glob("*.tif")) if not p.name.endswith(".tmp.tif")]
    if args.order != "list":
        stems = sorted(stems, key=lambda s: int(cities.loc[s, "nx"]) * int(cities.loc[s, "ny"]), reverse=args.order == "large")
    failures = []
    for stem in stems:
        source = component_dir / f"{stem}.tif"
        lock = work_queue.claim(out, stem)
        if lock is None:
            continue
        try:
            for daytype in args.daytypes:
                pending = [hour for hour in hours if not hourly_path(out, stem, daytype, hour).exists()
                           or (args.overwrite and not work_queue.written_in_this_run(hourly_path(out, stem, daytype, hour)))]
                if pending:
                    shares, info = daytype_shares(cities.loc[stem, "iso3"], daytype)
                    sums = render(source, shares, pending, out, stem, daytype)
                    print(json.dumps({"stem": stem, "daytype": daytype, "hours_written": len(sums), "shares": info.get("file")}), flush=True)
        except Exception as error:
            failures.append(stem)
            print(json.dumps({"stem": stem, "error": f"{type(error).__name__}: {error}"}), flush=True)
        finally:
            work_queue.release(lock)
    if not os.environ.get("DYNAMIC_POPULATION_WORKER"):
        write_index(out, cities, args.daytypes)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
