"""Strip Minecraft color codes from a line of text.

Lunar Client chat lines contain color codes written as the section sign
``§`` (byte 0xA7, which decodes to U+00A7 under latin-1) followed by one
character, e.g. ``§9Party §8> §6Name§f: hi``.

We strip the ``§`` together with the single character after it. The
``|§$`` alternative also removes a dangling ``§`` at the very end of a line
that has no following character.
"""

import re

_COLOR_CODE_RE = re.compile(r"§.|§$")


def strip_color_codes(s):
    """Return ``s`` with all ``§x`` color codes removed."""
    return _COLOR_CODE_RE.sub("", s)
