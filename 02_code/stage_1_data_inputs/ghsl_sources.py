"""Acquire native GHSL tiles for Stage 1 spatial extraction."""
from pathlib import Path
import time
import urllib.request
import urllib.error
import zipfile
import numpy as np
from stage_1_data_inputs import configuration

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


def fetch_tile(product: str, r: int, c: int, cache: Path, offline=False) -> Path | None:
    """Download and unzip one tile; returns the GeoTIFF path, or None if the tile does not
    exist (ocean tiles are not published)."""
    cache.mkdir(parents=True, exist_ok=True)
    name = configuration.GHSL_PRODUCTS[product][1]
    tif = cache / f"{name}_V1_0_R{r}_C{c}.tif"
    if tif.exists():
        return tif
    if offline:
        raise FileNotFoundError(f"Required source tile is not cached: {tif}")
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
