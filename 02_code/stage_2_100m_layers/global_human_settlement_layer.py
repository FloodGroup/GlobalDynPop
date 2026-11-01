"""GHSL R2023A 100 m tiles (Mollweide, ESRI:54009) -> city grids.

Tile scheme of the R2023A 100 m products: 1,000 km x 1,000 km tiles (10,000 x 10,000
pixels before edge clipping), named R<row>_C<col>; column c covers x in [-18,041,000 + (c-1) * 1e6, +1e6),
row r covers y in (9,000,000 - r * 1e6, 9,000,000 - (r-1) * 1e6].

The tile scheme selects candidate files. Actual GeoTIFF bounds and transforms
control reading and resampling because edge tiles can be cropped.

`accumulate(product, cities)` downloads every tile the city domains need (one at a time),
adds each tile's contribution to the city arrays with the mass-conserving resampling of
grid.resample_counts and deletes the tile again, so that disk use stays at one tile.
"""
from __future__ import annotations

import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

import stage_1_data_inputs.configuration as configuration
from stage_2_100m_layers.cities import grid_of

TILE = 1_000_000.0
X_ORIGIN = -18_041_000.0
Y_ORIGIN = 9_000_000.0
RES = 100.0


def tile_bounds(r: int, c: int):
    x0 = X_ORIGIN + (c - 1) * TILE
    y1 = Y_ORIGIN - (r - 1) * TILE
    return x0, y1 - TILE, x0 + TILE, y1


def tiles_for_bounds(x0, y0, x1, y1):
    c0 = int(np.floor((x0 - X_ORIGIN) / TILE)) + 1
    c1 = int(np.floor((x1 - X_ORIGIN) / TILE)) + 1
    r0 = int(np.floor((Y_ORIGIN - y1) / TILE)) + 1
    r1 = int(np.floor((Y_ORIGIN - y0) / TILE)) + 1
    return [(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]


def tile_url(product: str, r: int, c: int) -> str:
    folder, name = configuration.GHSL_PRODUCTS[product]
    return f"{configuration.GHSL_FTP}/{folder}/{name}/V1-0/tiles/{name}_V1_0_R{r}_C{c}.zip"


def fetch_tile(product: str, r: int, c: int, cache: Path) -> Path | None:
    """Download and unzip one tile; returns the GeoTIFF path, or None if the tile does not
    exist (ocean tiles are not published)."""
    cache.mkdir(parents=True, exist_ok=True)
    name = configuration.GHSL_PRODUCTS[product][1]
    tif = cache / f"{name}_V1_0_R{r}_C{c}.tif"
    if tif.exists():
        return tif
    zp = cache / f"{product}_R{r}_C{c}.zip"
    url = tile_url(product, r, c)
    for k in range(5):
        try:
            with urllib.request.urlopen(url, timeout=300) as resp, open(zp, "wb") as f:
                while True:
                    b = resp.read(1 << 22)
                    if not b:
                        break
                    f.write(b)
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if k == 4:
                raise
            time.sleep(5 * (k + 1))
        except Exception:
            if k == 4:
                raise
            time.sleep(5 * (k + 1))
    with zipfile.ZipFile(zp) as z:
        member = [n for n in z.namelist() if n.endswith(".tif")][0]
        with z.open(member) as src, open(tif, "wb") as dst:
            while True:
                b = src.read(1 << 22)
                if not b:
                    break
                dst.write(b)
    zp.unlink()
    return tif


def city_tiles(cities):
    """{stem: [(r, c), ...]} of the tiles each city domain touches."""
    out = {}
    for row in cities.to_dict("records"):
        g = grid_of(row)
        out[row["stem"]] = tiles_for_bounds(*g.bounds_in(configuration.MOLLWEIDE, margin=2 * RES))
    return out


def add_tile_to_city(tif: Path, r: int, c: int, row: dict, acc: np.ndarray, sub: int = 4):
    """Resample counts using the GeoTIFF georeference, including clipped edge tiles."""
    import rasterio
    from rasterio.windows import Window
    from stage_2_100m_layers.grid import resample_counts
    g = grid_of(row)
    with rasterio.open(tif) as ds:
        bx0, by0, bx1, by1 = g.bounds_in(ds.crs, margin=2 * RES)
        tx0, ty0, tx1, ty1 = ds.bounds
        x0, y0, x1, y1 = max(bx0, tx0), max(by0, ty0), min(bx1, tx1), min(by1, ty1)
        if x0 >= x1 or y0 >= y1:
            return acc
        res = ds.res[0]
        col0 = max(0, int(np.floor((x0 - tx0) / res)))
        col1 = min(ds.width, int(np.ceil((x1 - tx0) / res)))
        row0 = max(0, int(np.floor((ty1 - y1) / res)))
        row1 = min(ds.height, int(np.ceil((ty1 - y0) / res)))
        a = ds.read(1, window=Window(col0, row0, col1 - col0, row1 - row0))
        return resample_counts(a, tx0 + col0 * res, ty1 - row0 * res, res, ds.crs,
                               g, out=acc, sub=sub, nodata=ds.nodata)


def accumulate(product: str, cities, out_dir: Path, cache: Path | None = None, sub: int = 4, keep_tiles=False, log=print):
    """Resample `product` to every city grid; writes out_dir/<stem>.npy (float32, persons or m3
    per 100 m cell). Cities already written are skipped."""
    import pandas as pd
    cache = Path(cache or configuration.CACHE / "global_human_settlement_layer")
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    todo = cities[[not (out_dir / f"{s}.npy").exists() for s in cities.stem]]
    if not len(todo):
        return
    ct = city_tiles(todo)
    by_tile = {}
    for s, ts in ct.items():
        for t in ts:
            by_tile.setdefault(t, []).append(s)
    remaining = {s: len(ts) for s, ts in ct.items()}
    rows = {r["stem"]: r for r in todo.to_dict("records")}
    part = out_dir / "_partial"; part.mkdir(exist_ok=True)
    t0 = time.time()
    for k, (t, stems) in enumerate(sorted(by_tile.items())):
        tif = fetch_tile(product, *t, cache)
        for s in stems:
            pp = part / f"{s}.npy"
            row = rows[s]
            acc = np.load(pp) if pp.exists() else np.zeros((int(row["ny"]), int(row["nx"])), np.float64)
            if tif is not None:
                acc = add_tile_to_city(tif, *t, row, acc, sub=sub)
            remaining[s] -= 1
            if remaining[s] == 0:
                np.save(out_dir / f"{s}.npy", acc.astype(np.float32))
                pp.unlink(missing_ok=True)
            else:
                np.save(pp, acc)
        if tif is not None and not keep_tiles:
            tif.unlink(missing_ok=True)
        log(f"[{product}] tile R{t[0]}_C{t[1]} ({k + 1}/{len(by_tile)}): {len(stems)} cities, {time.time() - t0:.0f} s")


def sample_tile_to_city(tif: Path, r: int, c: int, row: dict, acc: np.ndarray, hit: np.ndarray):
    """Sample height at city-cell centres using the GeoTIFF's own extent and transform."""
    import rasterio
    from rasterio.windows import Window
    from pyproj import Transformer
    g = grid_of(row)
    xs, ys = g.centres()
    X, Y = np.meshgrid(xs, ys)
    with rasterio.open(tif) as ds:
        mx, my = Transformer.from_crs(g.crs, ds.crs, always_xy=True).transform(X.ravel(), Y.ravel())
        cc, rr = ~ds.transform * (mx, my)
        cc, rr = np.floor(cc).astype(int), np.floor(rr).astype(int)
        inside = (cc >= 0) & (cc < ds.width) & (rr >= 0) & (rr < ds.height)
        if not inside.any():
            return acc, hit
        cc, rr = cc[inside], rr[inside]
        c0, c1, r0, r1 = cc.min(), cc.max() + 1, rr.min(), rr.max() + 1
        a = ds.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype(np.float64)
        values = a[rr - r0, cc - c0]
        if ds.nodata is not None:
            values = np.where(values == ds.nodata, 0., values)
    index = np.flatnonzero(inside)
    acc.ravel()[index] = np.maximum(values, 0.)
    hit.ravel()[index] = True
    return acc, hit


def sample(product: str, cities, out_dir: Path, cache: Path | None = None, log=print):
    cache = Path(cache or configuration.CACHE / "global_human_settlement_layer")
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    todo = cities[[not (out_dir / f"{s}.npy").exists() for s in cities.stem]]
    if not len(todo):
        return
    ct = city_tiles(todo)
    by_tile = {}
    for s, ts in ct.items():
        for t in ts:
            by_tile.setdefault(t, []).append(s)
    remaining = {s: len(ts) for s, ts in ct.items()}
    rows = {r["stem"]: r for r in todo.to_dict("records")}
    part = out_dir / "_partial"; part.mkdir(exist_ok=True)
    for k, (t, stems) in enumerate(sorted(by_tile.items())):
        tif = fetch_tile(product, *t, cache)
        for s in stems:
            row = rows[s]
            pp = part / f"{s}.npz"
            if pp.exists():
                with np.load(pp) as z:
                    acc, hit = z["acc"], z["hit"]
            else:
                acc = np.zeros((int(row["ny"]), int(row["nx"])), np.float32); hit = np.zeros_like(acc, bool)
            if tif is not None:
                acc, hit = sample_tile_to_city(tif, *t, row, acc, hit)
            remaining[s] -= 1
            if remaining[s] == 0:
                np.save(out_dir / f"{s}.npy", acc.astype(np.float32)); pp.unlink(missing_ok=True)
            else:
                np.savez(pp, acc=acc, hit=hit)
        if tif is not None:
            tif.unlink(missing_ok=True)
        log(f"[{product}] tile R{t[0]}_C{t[1]} ({k + 1}/{len(by_tile)}): {len(stems)} cities")
