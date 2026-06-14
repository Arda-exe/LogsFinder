"""Generate app.ico for LogsFinder — a magnifying glass on the app's dark theme.

Pure standard library (struct + math), no third-party deps, so it doesn't touch
the runtime or the single-file build. Run once at build time:

    C:\\Python314\\python.exe tools\\make_icon.py

It writes ../app.ico containing 16/32/48/64/128/256 px entries in the classic
32-bit BGRA DIB format (the kind PyInstaller and Windows handle most reliably).
Each size is rendered at 4x and box-averaged down so the edges are smooth.
"""

import math
import os
import struct

# Palette (matches the app): dark background + Minecraft green for the glass.
BG = (30, 30, 30)          # #1e1e1e — app background
GREEN = (85, 255, 85)      # #55ff55 — Minecraft §a
GLASS = (34, 46, 40)       # faint tint inside the lens
HILITE = (200, 232, 212)   # small specular highlight on the lens

SIZES = [16, 32, 48, 64, 128, 256]
SS = 4  # supersample factor (each pixel averaged from SS*SS samples)


def _dist_to_segment(px, py, ax, ay, bx, by):
    """Shortest distance from point P to segment AB (normalized coords)."""
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 <= 0:
        t = 0.0
    else:
        t = ((px - ax) * dx + (py - ay) * dy) / seg2
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _sample(u, v):
    """Colour (r, g, b, a) for normalized coords u, v in [0, 1]."""
    # Rounded-square icon mask: soft corners via transparency (SDF of a box).
    rr = 0.16
    qx = max(abs(u - 0.5) - (0.5 - rr), 0.0)
    qy = max(abs(v - 0.5) - (0.5 - rr), 0.0)
    if math.hypot(qx, qy) > rr:
        return (0, 0, 0, 0)  # outside the icon -> transparent

    # Magnifying glass: a green ring + a handle to the lower-right.
    cx, cy = 0.42, 0.40
    outer, inner = 0.27, 0.20
    d = math.hypot(u - cx, v - cy)

    diag = 0.70710678
    p1x, p1y = cx + outer * diag, cy + outer * diag
    p2x, p2y = cx + (outer + 0.24) * diag, cy + (outer + 0.24) * diag
    on_handle = _dist_to_segment(u, v, p1x, p1y, p2x, p2y) <= 0.052

    if inner < d <= outer or on_handle:
        return GREEN + (255,)
    if d <= inner:
        # lens interior + a soft highlight near the upper-left
        hd = math.hypot(u - (cx - 0.085), v - (cy - 0.085))
        if hd <= 0.06:
            f = (1.0 - hd / 0.06) * 0.7
            return (
                int(GLASS[0] + (HILITE[0] - GLASS[0]) * f),
                int(GLASS[1] + (HILITE[1] - GLASS[1]) * f),
                int(GLASS[2] + (HILITE[2] - GLASS[2]) * f),
                255,
            )
        return GLASS + (255,)
    return BG + (255,)


def _render(size):
    """Render one size to a flat list of (r,g,b,a), top-to-bottom rows."""
    r = size * SS
    inv = 1.0 / r
    master = [_sample((x + 0.5) * inv, (y + 0.5) * inv)
              for y in range(r) for x in range(r)]

    # Box-average SSxSS blocks, premultiplying alpha so the transparent border
    # doesn't bleed dark fringes into the edges.
    out = [None] * (size * size)
    n = SS * SS
    for ty in range(size):
        for tx in range(size):
            sa = sr = sg = sb = 0
            by, bx = ty * SS, tx * SS
            for yy in range(SS):
                base = (by + yy) * r + bx
                for xx in range(SS):
                    pr, pg, pb, pa = master[base + xx]
                    sa += pa
                    sr += pr * pa
                    sg += pg * pa
                    sb += pb * pa
            if sa == 0:
                out[ty * size + tx] = (0, 0, 0, 0)
            else:
                out[ty * size + tx] = (sr // sa, sg // sa, sb // sa, sa // n)
    return out


def _dib(size, pixels):
    """A 32-bit BGRA DIB: BITMAPINFOHEADER + bottom-up colour rows + AND mask."""
    header = struct.pack("<IiiHHIIiiII",
                         40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    body = bytearray()
    for y in range(size - 1, -1, -1):       # bottom-up
        base = y * size
        for x in range(size):
            r, g, b, a = pixels[base + x]
            body += bytes((b, g, r, a))      # BGRA
    body += bytes((((size + 31) // 32) * 4) * size)  # AND mask, all zero
    return header + bytes(body)


def build_ico(path):
    entries = [(s, _dib(s, _render(s))) for s in SIZES]
    out = bytearray(struct.pack("<HHH", 0, 1, len(entries)))  # ICONDIR
    offset = 6 + 16 * len(entries)
    for size, data in entries:
        wh = size if size < 256 else 0       # 256 is stored as 0
        out += struct.pack("<BBBBHHII", wh, wh, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _size, data in entries:
        out += data
    with open(path, "wb") as f:
        f.write(out)
    return len(out)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(os.path.dirname(here), "app.ico")
    total = build_ico(out_path)
    print(f"Wrote {out_path} ({total} bytes; sizes {SIZES})")
