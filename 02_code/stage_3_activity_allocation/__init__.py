"""stage 3 activity allocation implementation."""
from pathlib import Path as _Path
import sys as _sys
_run_directory = str(_Path(__file__).resolve().parents[2] / "03_run" / "runtime")
if _run_directory not in _sys.path:
    _sys.path.insert(0, _run_directory)
