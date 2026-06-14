"""In-memory cache of parsed log files, keyed by (path, mtime).

Reading every file once and keeping the records in RAM makes repeat searches
instant. A file is only re-read when its modification time changes, so a Refresh
re-reads new files and the constantly-changing latest.log while leaving the
archived sessions cached.
"""

from pathlib import Path

from .logs import read_log_file


class LogCache:
    def __init__(self):
        self._cache = {}  # Path -> (mtime, LogFile)

    def get_file(self, path):
        """Return the cached ``LogFile`` for ``path``, loading/refreshing as needed.

        Returns ``None`` if the file is missing or unreadable.
        """
        path = Path(path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None

        entry = self._cache.get(path)
        if entry is not None and entry[0] == mtime:
            return entry[1]

        lf = read_log_file(path)
        if lf is None:
            return None
        self._cache[path] = (mtime, lf)
        return lf

    def get_lines(self, path):
        """Backward-compatible shim returning stripped text lines (or None)."""
        lf = self.get_file(path)
        return None if lf is None else [r.stripped for r in lf.lines]

    def clear(self):
        self._cache.clear()
