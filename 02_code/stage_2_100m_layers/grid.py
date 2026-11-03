"""Local 100 m model grids and mass-conserving resampling.

Each city uses a Lambert azimuthal equal-area projection centred on its urban
centre. Model cells are 100 m squares in projected coordinates. The projection
preserves area; projected Euclidean distances approximate ground distances within
the local domain.

Resampling of count rasters (people, m3 of building volume) from the GHSL Mollweide grid is
mass-conserving: every non-zero source pixel is split into s x s sub-pixels that carry
value / s^2 each, the sub-pixel centres are projected to the local grid and summed into the
cell they fall in.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyproj import CRS, Transformer


def laea_crs(lon0: float, lat0: float) -> CRS:
    return CRS.from_proj4(f"+proj=laea +lat_0={lat0:.6f} +lon_0={lon0:.6f} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs")


@dataclass(frozen=True)
class Grid:
    lon0: float
    lat0: float
    x0: float          # west edge (m, local projection)
    y1: float          # north edge
    nx: int
    ny: int
    cell: float = 100.0

    @property
    def crs(self) -> CRS:
        return laea_crs(self.lon0, self.lat0)

    @property
    def shape(self):
        return (self.ny, self.nx)

    def bounds(self):
        return self.x0, self.y1 - self.ny * self.cell, self.x0 + self.nx * self.cell, self.y1

    def transform(self):
        from rasterio.transform import from_origin
        return from_origin(self.x0, self.y1, self.cell, self.cell)

    def centres(self, every: int = 1):
        xs = self.x0 + (np.arange(0, self.nx, every) + 0.5) * self.cell
        ys = self.y1 - (np.arange(0, self.ny, every) + 0.5) * self.cell
        return xs, ys

    def boundary(self, k: int = 200):
        """Densified boundary (x, y) of the grid in its own projection."""
        x0, y0, x1, y1 = self.bounds()
        t = np.linspace(0, 1, k)
        xs = np.r_[x0 + (x1 - x0) * t, np.full(k, x1), x1 - (x1 - x0) * t, np.full(k, x0)]
        ys = np.r_[np.full(k, y1), y1 - (y1 - y0) * t, np.full(k, y0), y0 + (y1 - y0) * t]
        return xs, ys

    def bounds_in(self, crs, margin: float = 0.0):
        """Bounding box of the grid in another CRS (densified boundary)."""
        xs, ys = self.boundary()
        X, Y = Transformer.from_crs(self.crs, crs, always_xy=True).transform(xs, ys)
        return X.min() - margin, Y.min() - margin, X.max() + margin, Y.max() + margin

    def lonlat_bounds(self, margin_deg: float = 0.0):
        return self.bounds_in(4326, margin_deg)

    def index(self, x, y):
        """Row/col of points (local projection); -1 outside."""
        c = np.floor((x - self.x0) / self.cell).astype(np.int64)
        r = np.floor((self.y1 - y) / self.cell).astype(np.int64)
        ok = (c >= 0) & (c < self.nx) & (r >= 0) & (r < self.ny)
        return np.where(ok, r, -1), np.where(ok, c, -1)

    def to_dict(self):
        return dict(lon0=self.lon0, lat0=self.lat0, x0=self.x0, y1=self.y1, nx=self.nx, ny=self.ny, cell=self.cell)


def grid_from_row(r) -> Grid:
    return Grid(float(r["lon0"]), float(r["lat0"]), float(r["x0"]), float(r["y1"]), int(r["nx"]), int(r["ny"]),
                float(r.get("cell", 100.0)))


def resample_counts(src: np.ndarray, src_x0: float, src_y1: float, src_res: float, src_crs, grid: Grid,
                    out: np.ndarray | None = None, sub: int = 4, nodata=None, chunk: int = 2_000_000) -> np.ndarray:
    """Add the counts of a north-up source raster window to `out` (grid.shape), conserving mass.

    src_x0/src_y1: west and north edge of the window in src_crs. Pixels <= 0, NaN or equal to
    nodata are skipped. Returns `out` (float64)."""
    if out is None:
        out = np.zeros(grid.shape, np.float64)
    v = src.astype(np.float64, copy=False)
    m = np.isfinite(v) & (v > 0)
    if nodata is not None:
        m &= v != nodata
    rr, cc = np.nonzero(m)
    if not len(rr):
        return out
    vals = v[rr, cc] / (sub * sub)
    off = (np.arange(sub) + 0.5) / sub
    ox, oy = np.meshgrid(off, off)
    ox, oy = ox.ravel(), oy.ravel()
    tr = Transformer.from_crs(src_crs, grid.crs, always_xy=True)
    flat = out.ravel()
    step = max(1, chunk // (sub * sub))
    for s in range(0, len(rr), step):
        r_, c_, w_ = rr[s:s + step], cc[s:s + step], vals[s:s + step]
        X = (src_x0 + (c_[:, None] + ox[None, :]) * src_res).ravel()
        Y = (src_y1 - (r_[:, None] + oy[None, :]) * src_res).ravel()
        x, y = tr.transform(X, Y)
        ri, ci = grid.index(x, y)
        ok = ri >= 0
        idx = ri[ok] * grid.nx + ci[ok]
        flat += np.bincount(idx, weights=np.repeat(w_, sub * sub)[ok], minlength=flat.size)
    return out
