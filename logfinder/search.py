"""Pure search core: scan cached log files and build context blocks.

No tkinter here so this can be unit-tested on its own. The search returns an
accurate total match count, context "blocks" (overlapping context windows around
nearby matches are merged into one block), and a per-speaker breakdown.

Filters: ``scope`` (all / chat / mine), inclusive ``date_from``/``date_to``, and
optional ``time_from``/``time_to`` (seconds since midnight). All count toward the
same filtered match list, so total_count and the breakdown stay consistent.
"""

import re
from collections import Counter
from dataclasses import dataclass, field


class LineView:
    """One rendered line: raw (with §) for color display, plus match/speaker info."""

    __slots__ = ("line_no", "raw", "stripped", "is_match", "speaker")

    def __init__(self, line_no, raw, stripped, is_match, speaker):
        self.line_no = line_no
        self.raw = raw
        self.stripped = stripped
        self.is_match = is_match
        self.speaker = speaker


@dataclass
class Block:
    file: str
    lines: list  # list[LineView]


@dataclass
class SearchResult:
    query: str
    total_count: int
    blocks: list
    files_searched: int
    skipped: list = field(default_factory=list)
    truncated: bool = False
    speakers: Counter = field(default_factory=Counter)  # who-said-it, line-based
    self_names: set = field(default_factory=set)         # your session names (for "(you)")


def _build_matcher(query, regex, ignore_case):
    """Return a predicate over a LineRec. Matches the VISIBLE text, never § noise."""
    if regex:
        flags = re.IGNORECASE if ignore_case else 0
        pattern = re.compile(query, flags)  # may raise re.error -> handled by caller
        return lambda rec: pattern.search(rec.stripped) is not None
    if ignore_case:
        needle = query.lower()
        return lambda rec: needle in rec.lower
    return lambda rec: query in rec.stripped


def _speaker_name(rec):
    return rec.speaker if (rec.is_chat and rec.speaker) else "system"


def search(cache, files, query, *, regex=False, ignore_case=True, context=10,
           max_blocks=2000, scope="all", date_from=None, date_to=None,
           time_from=None, time_to=None):
    """Search ``files`` (Paths) for ``query`` using ``cache`` for file access."""
    if not query:
        return SearchResult(query, 0, [], 0)

    matches = _build_matcher(query, regex, ignore_case)
    has_time = time_from is not None or time_to is not None

    total = 0
    blocks = []
    files_searched = 0
    skipped = []
    truncated = False
    speakers = Counter()
    self_names = set()

    for path in files:
        lf = cache.get_file(path)
        if lf is None:
            skipped.append(path.name)
            continue

        # File-level date prefilter (lf.date is already cached → effectively free).
        if date_from is not None and (lf.date is None or lf.date < date_from):
            continue
        if date_to is not None and (lf.date is None or lf.date > date_to):
            continue

        files_searched += 1
        lines = lf.lines
        session_user = lf.session_user

        def hit(rec):
            if not matches(rec):
                return False
            if scope == "chat" and not rec.is_chat:
                return False
            if scope == "mine":
                if not rec.is_chat or rec.speaker is None or rec.speaker != session_user:
                    return False
            if has_time:
                ts = rec.time_secs
                if ts is None:
                    return False
                if time_from is not None and ts < time_from:
                    return False
                if time_to is not None and ts > time_to:
                    return False
            return True

        match_idx = [i for i, rec in enumerate(lines) if hit(rec)]
        if not match_idx:
            continue
        total += len(match_idx)

        for i in match_idx:
            speakers[_speaker_name(lines[i])] += 1
        if session_user:
            self_names.add(session_user)

        # Once the render cap is hit we keep counting (total + breakdown stay
        # exact) but stop building blocks so the UI stays responsive.
        if truncated:
            continue

        match_set = set(match_idx)
        n = len(lines)

        windows = []
        for i in match_idx:
            start = max(0, i - context)
            end = min(n - 1, i + context)
            if windows and start <= windows[-1][1] + 1:
                if end > windows[-1][1]:
                    windows[-1] = (windows[-1][0], end)
            else:
                windows.append((start, end))

        for start, end in windows:
            if len(blocks) >= max_blocks:
                truncated = True
                break
            views = []
            for idx in range(start, end + 1):
                rec = lines[idx]
                is_m = idx in match_set
                views.append(LineView(
                    idx + 1, rec.raw, rec.stripped, is_m,
                    _speaker_name(rec) if is_m else None,
                ))
            blocks.append(Block(file=lf.name, lines=views))

    return SearchResult(
        query=query, total_count=total, blocks=blocks, files_searched=files_searched,
        skipped=skipped, truncated=truncated, speakers=speakers, self_names=self_names,
    )
