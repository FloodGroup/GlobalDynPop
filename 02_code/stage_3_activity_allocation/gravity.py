"""Production-constrained gravity allocation on the 100 m grid.

For one activity c, the residents N(y) of every origin cell y are distributed over the
destination cells x in proportion to attractiveness x distance decay:

    D_c(x) = A_c(x) * sum_y N(y) f_c(|x - y|) / Z_c(y),     Z_c(y) = sum_x A_c(x) f_c(|x - y|)

so that sum_x D_c(x) = sum_y N(y) (every resident is placed somewhere). Both sums are
convolutions with the isotropic kernel f_c, computed with FFTs on the full 100 m grid:
Z = A * f and D = A . ((N / Z) * f). Residents whose accessibility Z is zero (no destination
within the kernel radius) stay at home (returned separately).

Kernels: exponential f(d) = exp(-d / d0) (default) or power law with exponential cut-off.
The kernel is truncated at `radius` (default 6 d0, capped by the domain size).
"""
from __future__ import annotations

import numpy as np
from scipy.signal import fftconvolve


def kernel_values(d, d0_m: float, kind: str = "exp", beta: float = 1.0, dmin_m: float = 250.0):
    """Distance-decay function f(d) (d in metres)."""
    if kind == "exp":
        return np.exp(-d / d0_m)
    if kind == "pow":        # power law (d + dmin)^-beta with an exponential cut-off at d0
        return (d + dmin_m) ** (-beta) * np.exp(-d / d0_m)
    raise ValueError(kind)


def kernel(d0_m: float, cell: float = 100.0, radius_m: float | None = None, kind: str = "exp", beta: float = 1.0,
           max_cells: int | None = None, dmin_m: float = 250.0, coarse: int = 1) -> np.ndarray:
    """Kernel on a grid of `cell` (m). With coarse > 1 the kernel of a grid coarsened by that
    factor is returned: the mean of the fine kernel (cell / coarse) over each coarse cell,
    seen from the centre of the central cell, so that a calibration on the coarse grid is
    consistent with the fine model."""
    radius_m = radius_m or 6.0 * d0_m
    n = int(np.ceil(radius_m / cell))
    if max_cells is not None:
        n = min(n, max_cells)
    if coarse == 1:
        ax = np.arange(-n, n + 1) * cell
        X, Y = np.meshgrid(ax, ax)
        d = np.hypot(X, Y)
        k = kernel_values(d, d0_m, kind, beta, dmin_m)
        k[d > n * cell] = 0.0
        return k.astype(np.float64)
    fc = cell / coarse
    sub = (np.arange(coarse) - (coarse - 1) / 2.0) * fc
    ax = np.arange(-n, n + 1) * cell
    X, Y = np.meshgrid(ax, ax)
    k = np.zeros_like(X, dtype=np.float64)
    for su in sub:
        for sv in sub:
            d = np.hypot(X + su, Y + sv)
            k += kernel_values(d, d0_m, kind, beta, dmin_m)
    k /= coarse * coarse
    k[np.hypot(X, Y) > n * cell] = 0.0
    return k


def conv(a: np.ndarray, k: np.ndarray) -> np.ndarray:
    out = fftconvolve(a, k, mode="same")
    out[out < 0] = 0.0          # FFT round-off
    return out


def allocate(N: np.ndarray, A: np.ndarray, k: np.ndarray, eps_rel: float = 1e-9):
    """Returns (D, stay): D = destinations of all residents with Z > 0, stay = residents that
    cannot reach any destination (Z == 0)."""
    N = N.astype(np.float64); A = A.astype(np.float64)
    if A.sum() <= 0:
        return np.zeros_like(N), N.copy()
    Z = conv(A, k)
    zmin = eps_rel * Z.max()
    ok = Z > zmin
    q = np.where(ok, N / np.where(ok, Z, 1.0), 0.0)
    D = A * conv(q, k)
    stay = np.where(ok, 0.0, N)
    # renormalise round-off so that mass is conserved exactly
    tot = N[ok].sum()
    s = D.sum()
    if s > 0:
        D *= tot / s
    return D, stay


def mean_distance(N: np.ndarray, A: np.ndarray, k: np.ndarray, cell: float = 100.0):
    """Mean origin-destination distance of the allocation (m): sum_y N(y) E[d | y]."""
    n = (k.shape[0] - 1) // 2
    ax = np.arange(-n, n + 1) * cell
    X, Y = np.meshgrid(ax, ax)
    d = np.hypot(X, Y)
    Z = conv(A, k)
    ZD = conv(A, k * d)
    ok = Z > 1e-12 * Z.max()
    ed = np.where(ok, ZD / np.where(ok, Z, 1.0), 0.0)
    w = N * ok
    return float((w * ed).sum() / max(w.sum(), 1e-12))
