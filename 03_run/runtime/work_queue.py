"""Lock files with which several processes share the cities of one step (run_parallel.py).

A process takes a city by creating <folder>/.<stem>.lock (an atomic create on Linux and Windows); the other
processes skip the city while the file exists, and the file is removed when the city is done or has failed. With
--overwrite, a city whose output was written after the start of the run (DYNAMIC_POPULATION_RUN_START, set by run_parallel.py) is
not computed again.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

RUN_START = float(os.environ.get("DYNAMIC_POPULATION_RUN_START") or time.time())


def claim(folder, stem: str):
    """The lock file of the city, or None when another process has it."""
    lock = Path(folder) / f".{stem}.lock"
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return None
    return lock


def release(lock) -> None:
    if lock is None:
        return
    try:
        Path(lock).unlink()
    except FileNotFoundError:
        pass


def written_in_this_run(f: Path) -> bool:
    try:
        return Path(f).stat().st_mtime >= RUN_START - 1.0
    except FileNotFoundError:
        return False


def clear(folder) -> int:
    """Remove the lock files left by interrupted processes (only when no process of the step is running)."""
    n = 0
    for f in list(Path(folder).glob(".*.lock")) + list(Path(folder).glob("*.lock")):
        try:
            f.unlink()
            n += 1
        except FileNotFoundError:
            pass
    return n
