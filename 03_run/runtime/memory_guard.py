"""Optional memory gate for batch runs (only active when DYNAMIC_POPULATION_MEMWAIT_GB is set): before a city is started, wait
until the computer has room for DYNAMIC_POPULATION_MEMWAIT_GB more GB, keeping DYNAMIC_POPULATION_MEMWAIT_MARGIN_GB (default 0.5) free.

The free memory is read from the memory cgroup of the process (Linux containers, cgroup v1 or v2) or, elsewhere
(Windows, macOS, Linux without a memory limit), from the available physical memory (psutil). Without either it
does nothing. While the file DYNAMIC_POPULATION_PAUSE_FILE exists, no new city is started."""
from __future__ import annotations

import os
import time
from pathlib import Path


def _cgroup():
    try:
        for line in Path("/proc/self/cgroup").read_text().splitlines():
            parts = line.split(":", 2)
            if len(parts) == 3 and ("memory" in parts[1].split(",") or parts[1] == ""):
                base = Path("/sys/fs/cgroup/memory") if parts[1] else Path("/sys/fs/cgroup")
                p = base / parts[2].lstrip("/")
                if (p / "memory.limit_in_bytes").exists():
                    return p, "v1"
                if (p / "memory.max").exists():
                    return p, "v2"
    except OSError:
        pass
    return None, None


def used_and_limit():
    """(used, limit) in bytes of the memory cgroup, or (None, None) without a limited cgroup."""
    p, v = _cgroup()
    if p is None:
        return None, None
    try:
        st = dict(l.split() for l in (p / "memory.stat").read_text().splitlines() if " " in l)
        if v == "v1":
            lim = int((p / "memory.limit_in_bytes").read_text())
            used = int(st.get("total_rss", st.get("rss", 0))) + int(st.get("total_mapped_file", st.get("mapped_file", 0)))
        else:
            m = (p / "memory.max").read_text().strip()
            if m == "max":
                return None, None
            lim = int(m)
            used = int(st.get("anon", 0)) + int(st.get("file_mapped", 0))
    except (OSError, ValueError):
        return None, None
    if lim >= 1 << 60:                                   # no real limit
        return None, None
    return used, lim


def own_rss() -> int:
    """Resident memory of this process (bytes); a waiting worker reuses it for the next city."""
    try:
        return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError, AttributeError):
        pass
    try:
        import psutil
        return int(psutil.Process().memory_info().rss)
    except Exception:  # noqa: BLE001
        return 0


def headroom():
    """Bytes the next city of this process can use, or None when the memory cannot be read."""
    used, lim = used_and_limit()
    if used is not None:
        return lim - max(used - own_rss(), 0)
    try:
        import psutil
        return int(psutil.virtual_memory().available) + own_rss()
    except Exception:  # noqa: BLE001
        return None


def wait(need_gb: float | None = None, log=None, poll_s: float = 15.0):
    need = need_gb if need_gb is not None else float(os.environ.get("DYNAMIC_POPULATION_MEMWAIT_GB", "0") or 0)
    if need <= 0:
        return
    margin = float(os.environ.get("DYNAMIC_POPULATION_MEMWAIT_MARGIN_GB", "0.5"))
    pause = os.environ.get("DYNAMIC_POPULATION_PAUSE_FILE")                 # while this file exists, no new city is started
    t0, said = time.time(), False
    while True:
        if pause and Path(pause).exists():
            if not said and log:
                log("paused (" + pause + ")")
                said = True
            time.sleep(poll_s)
            continue
        room = headroom()
        if room is None or room >= (need + margin) * 1e9:
            if said and log:
                log(f"memory free again after {time.time() - t0:.0f} s")
            return
        if not said and log:
            log(f"waiting for memory: {room / 1e9:.1f} GB free, need {need:.1f} GB")
            said = True
        time.sleep(poll_s)
