"""stage 1 data inputs implementation."""
from pathlib import Path as _Path
import sys as _sys
_run_directory = str(_Path(__file__).resolve().parents[2] / "03_run" / "runtime")
if _run_directory not in _sys.path:
    _sys.path.insert(0, _run_directory)

# numpy < 2 can read object arrays that numpy >= 2 pickled into .npz files (module path numpy._core)
import sys as _sys

import numpy as _np

if int(_np.__version__.split(".")[0]) < 2 and "numpy._core" not in _sys.modules:
    import importlib as _il
    _sys.modules["numpy._core"] = _il.import_module("numpy.core")
    for _m in ("multiarray", "numeric", "_multiarray_umath", "umath", "fromnumeric", "_dtype_ctypes"):
        try:
            _sys.modules[f"numpy._core.{_m}"] = _il.import_module(f"numpy.core.{_m}")
        except ImportError:
            pass
