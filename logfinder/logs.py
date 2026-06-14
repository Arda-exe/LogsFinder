"""Find Lunar Client log files and read them into structured records.

Files are named ``YYYY-MM-DD-N.log.gz`` (gzip) plus one uncompressed
``latest.log`` for the current session. They are decoded as cp1252
(Windows-1252) — old Minecraft on Windows wrote them in the system codepage,
so cp1252 recovers punctuation (• – — “”) that latin-1 turns into invisible
control characters, while keeping 0xA7 -> ``§`` identical. ``errors='replace'``
makes it never raise on the few cp1252-undefined bytes.

``read_log_file`` returns a ``LogFile`` carrying ``LineRec``s (raw + stripped),
the session username, and the file's date.
"""

import datetime
import gzip
import re
import zlib
from pathlib import Path

from .parse import LogFile, build_line, detect_session_user

_NAME_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d+)\.log\.gz$")


def _sort_key(path):
    """Chronological sort key: dated archives oldest-first, latest.log last."""
    m = _NAME_RE.match(path.name)
    if m:
        year, month, day, seq = (int(g) for g in m.groups())
        return (0, year, month, day, seq)
    if path.name == "latest.log":
        return (2, 0, 0, 0, 0)  # current session sorts after everything dated
    return (1, 0, 0, 0, 0)


def _file_date(path):
    """Date from the filename, or (for latest.log) the file's mtime date."""
    m = _NAME_RE.match(path.name)
    if m:
        year, month, day, _seq = (int(g) for g in m.groups())
        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None
    try:
        return datetime.date.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def find_log_files(folder):
    """Return all log files in ``folder`` in chronological order.

    Tolerates a missing folder (returns an empty list).
    """
    folder = Path(folder)
    if not folder.is_dir():
        return []
    files = list(folder.glob("*.log.gz"))
    latest = folder / "latest.log"
    if latest.is_file():
        files.append(latest)
    files.sort(key=_sort_key)
    return files


def read_log_file(path):
    """Read one log file into a ``LogFile``.

    ``.gz`` files are gunzipped; everything else (latest.log) is read with a
    shared read so it works even while Lunar holds it open for writing. Returns
    ``None`` if the file can't be read (busy / corrupt) so the caller can skip it.
    """
    path = Path(path)
    try:
        if path.suffix.lower() == ".gz":
            with gzip.open(path, "rb") as f:
                data = f.read()
        else:
            with open(path, "rb") as f:
                data = f.read()
    except (OSError, EOFError, gzip.BadGzipFile, zlib.error):
        return None

    raw_lines = data.decode("cp1252", errors="replace").split("\n")
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()  # drop the empty element after a trailing newline

    recs = [build_line(line) for line in raw_lines]
    session_user = detect_session_user([r.stripped for r in recs])
    return LogFile(name=path.name, lines=recs, session_user=session_user,
                   date=_file_date(path))


def read_log_lines(path):
    """Backward-compatible shim: list of cleaned (stripped) text lines, or None."""
    lf = read_log_file(path)
    return None if lf is None else [r.stripped for r in lf.lines]
