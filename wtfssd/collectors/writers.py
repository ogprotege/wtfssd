from __future__ import annotations

from typing import Callable, Optional

from ..models import WriterProc, WritersReport
from ._run import run_cmd
from .processes import etime_to_seconds

# proc_pid_rusage(RUSAGE_INFO_V2) — the same libproc source Activity
# Monitor's "Bytes Written" column reads. Needs no root: other users' and
# most system processes simply return an error and are skipped.
_RUSAGE_INFO_V2 = 2
_BUF_LEN = 16 + 18 * 8            # ri_uuid[16] + 18 x uint64 fields
_OFF_BYTES_WRITTEN = 16 + 17 * 8  # ri_diskio_byteswritten (last V2 field)


def _libproc_reader() -> Optional[Callable[[int], Optional[int]]]:
    """Build a per-pid bytes-written reader, or None if libproc is unusable
    (non-macOS, hardened runtime, missing dylib)."""
    try:
        import ctypes
        lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        lib.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int,
                                        ctypes.c_void_p]
        lib.proc_pid_rusage.restype = ctypes.c_int
    except Exception:
        return None

    def read(pid: int) -> Optional[int]:
        buf = ctypes.create_string_buffer(_BUF_LEN)
        if lib.proc_pid_rusage(pid, _RUSAGE_INFO_V2, buf) != 0:
            return None  # permission denied / process gone
        return int.from_bytes(
            buf.raw[_OFF_BYTES_WRITTEN:_OFF_BYTES_WRITTEN + 8], "little")

    return read


def collect_writers(
    top_n: int = 8,
    runner: Callable = run_cmd,
    rusage_fn: Optional[Callable[[int], Optional[int]]] = None,
) -> WritersReport:
    """Rank live processes by cumulative disk bytes written.

    Attribution is a floor, not a total: exited processes took their
    counters with them, and root-only daemons are invisible without sudo
    (which this product never uses)."""
    if rusage_fn is None:
        rusage_fn = _libproc_reader()
        if rusage_fn is None:
            return WritersReport(available=False, error="libproc unavailable")
    text = runner(["ps", "-axo", "pid=,etime=,comm="])
    if text is None:
        return WritersReport(available=False, error="ps failed")
    rows: list[WriterProc] = []
    for line in text.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        try:
            written = rusage_fn(int(parts[0]))
        except Exception:
            written = None  # a denied pid must never sink the collector
        if not written:
            continue
        try:
            elapsed = etime_to_seconds(parts[1])
        except ValueError:
            elapsed = 0
        rows.append(WriterProc(pid=int(parts[0]), name=parts[2].strip(),
                               written_bytes=int(written),
                               elapsed_seconds=elapsed))
    rows.sort(key=lambda w: w.written_bytes, reverse=True)
    return WritersReport(
        available=True,
        top=rows[:top_n],
        visible_total_bytes=sum(w.written_bytes for w in rows),
        process_count=len(rows),
    )
