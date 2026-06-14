"""Pure parsing helpers for Lunar Client (Hypixel) log lines.

No tkinter here — everything is testable in isolation. Covers chat detection,
timestamp parsing, session-username detection, the speaker (who-said-it)
heuristic, color segmentation for rendering, and control-char sanitation.

It also defines the in-memory record types ``LineRec`` (one per line) and
``LogFile`` (one per file) used by the cache and search core.
"""

import re
from dataclasses import dataclass

from .colorcodes import strip_color_codes

SECTION = "§"  # § — byte 0xA7 under latin-1

_CHAT_MARKER = "]: [CHAT] "
_CHAT_TAG = "[CHAT] "


# --------------------------------------------------------------------------- #
# Cheap, eager line facts                                                      #
# --------------------------------------------------------------------------- #
def is_chat_line(raw):
    """True if the raw line is an in-game chat line (`[CHAT]` tag present)."""
    return _CHAT_MARKER in raw


def chat_content(line):
    """Return the message text after the first ``[CHAT] `` marker (or '')."""
    i = line.find(_CHAT_TAG)
    return line[i + len(_CHAT_TAG):] if i != -1 else ""


def split_prefix(raw):
    """Split a line into ``(neutral_prefix, payload)`` for rendering.

    For chat lines the prefix runs through ``[CHAT] ``; otherwise through the
    first ``]: `` (the ``[time] [thread/LEVEL]: `` header). Color codes only ever
    appear in the payload, so the prefix can always be drawn in a neutral color.
    """
    i = raw.find(_CHAT_TAG)
    if i != -1:
        cut = i + len(_CHAT_TAG)
        return raw[:cut], raw[cut:]
    j = raw.find("]: ")
    if j != -1:
        cut = j + len("]: ")
        return raw[:cut], raw[cut:]
    return "", raw


def parse_time(raw):
    """Seconds since midnight from a leading ``[HH:MM:SS]``; None if absent/bad."""
    if (len(raw) < 10 or raw[0] != "[" or raw[3] != ":"
            or raw[6] != ":" or raw[9] != "]"):
        return None
    h, m, s = raw[1:3], raw[4:6], raw[7:9]
    if not (h.isdigit() and m.isdigit() and s.isdigit()):
        return None
    return int(h) * 3600 + int(m) * 60 + int(s)


_SETUSER_RE = re.compile(r"Setting user:\s*([A-Za-z0-9_]{1,16})")


def detect_session_user(lines, scan_limit=80):
    """Find the local player's name from the ``Setting user: NAME`` line.

    Only the first ``scan_limit`` lines are scanned (it appears near the top,
    2-3 times). Returns None if not found.
    """
    for line in lines[:scan_limit]:
        m = _SETUSER_RE.search(line)
        if m:
            return m.group(1)
    return None


# Delete all C0 control chars except tab (0x09). Newlines are already split out;
# this also removes the stray mid-line \r (0x0d) Hypixel sometimes emits. Using a
# translate table is far faster than a regex over ~2M lines at load time.
_SANITIZE_TABLE = {c: None for c in list(range(0, 9)) + list(range(10, 32))}


def sanitize(raw):
    """Drop carriage returns and other stray control chars Hypixel sometimes emits."""
    return raw.translate(_SANITIZE_TABLE)


# --------------------------------------------------------------------------- #
# Speaker extraction (Hypixel-tuned heuristic)                                 #
# --------------------------------------------------------------------------- #
# Game chat shows a rank-title word before a player's rank/name (e.g.
# "? Expert [MVP++] YuriTwin: gg"). Only these words (and +*? symbol clusters)
# may sit left of the name; anything else means it's a system/announcement line.
_RANK_TITLES = frozenset({
    "rookie", "untrained", "trained", "amateur", "apprentice", "experienced",
    "seasoned", "skilled", "talented", "professional", "expert", "artisan",
    "master", "legend", "novice", "grandmaster", "prospect",
})
_NAME_RE = re.compile(r"[A-Za-z0-9_]{1,16}")
_BRACKET_RE = re.compile(r"\[[^\]]*\]")


def extract_speaker(stripped_chat_content):
    """Best-effort player username that sent a chat message, or None (system).

    Tuned for Hypixel chat. Returns None for game/system announcements that have
    no ``Name: `` sender (e.g. "Player eliminated: x", JSON blobs, "X got a
    perfect build", "Friend > Name joined.").
    """
    i = stripped_chat_content.find(": ")
    if i == -1:
        return None
    head = stripped_chat_content[:i]
    if ">" in head:  # drop channel prefix: 'Party >', 'Friend >', 'Guild >', ...
        head = head.rsplit(">", 1)[1]
    head = _BRACKET_RE.sub(" ", head)  # remove rank/guild tags: [MVP++], [VIP], [Member]
    toks = head.split()
    if not toks:
        return None
    cand = toks[-1]
    if not _NAME_RE.fullmatch(cand):
        return None
    for w in toks[:-1]:  # everything left of the name must be a rank-title or +*? cluster
        if w.lower() in _RANK_TITLES:
            continue
        if w and all(ch in "+*?" for ch in w):
            continue
        return None  # a stray English word / dashes ⇒ system line
    return cand


# --------------------------------------------------------------------------- #
# Color segmentation for rendering                                             #
# --------------------------------------------------------------------------- #
def segment_colors(raw):
    """Split a raw line into runs of ``(text, color_key)``.

    ``color_key`` is one of '0'-'9'/'a'-'f' or None (default / after §r). Format
    codes (§k/l/m/n/o) are dropped in v1 — they need per-segment fonts that fight
    the Tk color tags.
    """
    out = []
    buf = []
    color = None
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch == SECTION and i + 1 < n:
            code = raw[i + 1].lower()
            if buf:
                out.append(("".join(buf), color))
                buf = []
            if code in "0123456789abcdef":
                color = code
            elif code == "r":
                color = None
            # k/l/m/n/o: ignored (drop the code, keep current color)
            i += 2
            continue
        buf.append(ch)
        i += 1
    if buf:
        out.append(("".join(buf), color))
    return out


# --------------------------------------------------------------------------- #
# Record types                                                                 #
# --------------------------------------------------------------------------- #
_UNSET = object()


class LineRec:
    """One log line. ``speaker`` and ``time_secs`` are computed lazily — they
    only matter for matched lines / active time filters, so paying for them on
    every one of ~2M lines at load would be wasteful."""

    __slots__ = ("raw", "stripped", "lower", "is_chat", "_speaker", "_time")

    def __init__(self, raw, stripped, is_chat):
        self.raw = raw            # KEEPS § codes (for color rendering); sanitized at render
        self.stripped = stripped  # § removed (display fallback + matching + speaker)
        self.lower = stripped.lower()  # precomputed for fast case-insensitive search
        self.is_chat = is_chat
        self._speaker = _UNSET
        self._time = _UNSET

    @property
    def speaker(self):
        if self._speaker is _UNSET:
            self._speaker = (
                extract_speaker(chat_content(self.stripped)) if self.is_chat else None
            )
        return self._speaker

    @property
    def time_secs(self):
        if self._time is _UNSET:
            self._time = parse_time(self.raw)
        return self._time


@dataclass
class LogFile:
    name: str
    lines: list           # list[LineRec]
    session_user: object = None  # str | None
    date: object = None          # datetime.date | None


def build_line(raw):
    """Build a LineRec from one raw (already newline-split) line.

    Hot path (runs ~2M times at load): only the cheap trailing ``\\r`` is removed
    here; the color regex is skipped entirely when the line has no ``§``. Full
    control-char sanitation is deferred to render time (only a capped number of
    lines are ever shown).
    """
    raw = raw.rstrip("\r")
    stripped = strip_color_codes(raw) if SECTION in raw else raw
    return LineRec(raw, stripped, _CHAT_MARKER in raw)
