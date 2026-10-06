"""Decode and encode Wii (GX) texture data, for looking at and resizing images.

CMPR: 8x8 tiles of four 4x4 DXT1-like blocks (big-endian RGB565 endpoints, 2-bit indices, the first row in the high
bits). I4: 8x8 tiles, 4-bit intensity. Images are lists of rows of (r, g, b, a) tuples.
"""
import struct
import zlib


def _rgb565(c):
    r, g, b = (c >> 11) & 0x1F, (c >> 5) & 0x3F, c & 0x1F
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def _palette(c0, c1):
    a, b = _rgb565(c0), _rgb565(c1)
    if c0 > c1:
        return [a + (255,), b + (255,), tuple((2 * x + y) // 3 for x, y in zip(a, b)) + (255,),
                tuple((x + 2 * y) // 3 for x, y in zip(a, b)) + (255,)]
    return [a + (255,), b + (255,), tuple((x + y) // 2 for x, y in zip(a, b)) + (255,), (0, 0, 0, 0)]


def padded(w, h, tile_w=8, tile_h=8):
    return (w + tile_w - 1) // tile_w * tile_w, (h + tile_h - 1) // tile_h * tile_h


def decode_cmpr(data, w, h):
    pw, ph = padded(w, h)
    img = [[(0, 0, 0, 0)] * pw for _ in range(ph)]
    pos = 0
    for ty in range(0, ph, 8):
        for tx in range(0, pw, 8):
            for sub in range(4):
                c0, c1, bits = struct.unpack_from(">HHI", data, pos)
                pos += 8
                pal = _palette(c0, c1)
                bx, by = tx + (sub & 1) * 4, ty + (sub >> 1) * 4
                for k in range(16):
                    idx = (bits >> (30 - 2 * k)) & 3
                    img[by + k // 4][bx + k % 4] = pal[idx]
    return [row[:w] for row in img[:h]]


def decode_i4(data, w, h):
    pw, ph = padded(w, h, 8, 8)
    img = [[(0, 0, 0, 0)] * pw for _ in range(ph)]
    pos = 0
    for ty in range(0, ph, 8):
        for tx in range(0, pw, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    b = data[pos]
                    pos += 1
                    for k, v in enumerate((b >> 4, b & 0xF)):
                        i = v * 17
                        img[ty + y][tx + x + k] = (i, i, i, 255)
    return [row[:w] for row in img[:h]]


def _to565(c):
    r, g, b = (min(255, max(0, int(round(v)))) for v in c[:3])
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def _encode_block(px):
    """One 4x4 block (16 RGBA tuples, row by row) -> 8 bytes. Pixels with alpha below 128 become transparent
    (3-colour mode); otherwise 4-colour mode. Endpoints: the extremes along the colours' main axis."""
    opaque = [p for p in px if p[3] >= 128]
    has_alpha = len(opaque) < 16
    if not opaque:
        return struct.pack(">HHI", 0, 0, 0xFFFFFFFF)
    n = len(opaque)
    mean = [sum(p[k] for p in opaque) / n for k in range(3)]
    cov = [[sum((p[i] - mean[i]) * (p[j] - mean[j]) for p in opaque) for j in range(3)] for i in range(3)]
    axis = [1.0, 1.0, 1.0]
    for _ in range(6):  # power iteration for the main axis
        v = [sum(cov[i][j] * axis[j] for j in range(3)) for i in range(3)]
        norm = max(abs(x) for x in v)
        if norm < 1e-6:
            break
        axis = [x / norm for x in v]
    proj = [sum((p[k] - mean[k]) * axis[k] for k in range(3)) for p in opaque]
    lo, hi = opaque[proj.index(min(proj))], opaque[proj.index(max(proj))]
    c0, c1 = _to565(hi), _to565(lo)
    if has_alpha:
        if c0 > c1:
            c0, c1 = c1, c0
    else:
        if c0 < c1:
            c0, c1 = c1, c0
        elif c0 == c1:
            # equal endpoints select 3-colour mode; every pixel takes colour 0
            return struct.pack(">HHI", c0, c1, 0)
    pal = _palette(c0, c1)
    usable = 3 if has_alpha else 4
    bits = 0
    for k, p in enumerate(px):
        if p[3] < 128:
            idx = 3
        else:
            idx = min(range(usable), key=lambda i: sum((p[c] - pal[i][c]) ** 2 for c in range(3)))
        bits |= idx << (30 - 2 * k)
    return struct.pack(">HHI", c0, c1, bits)


def encode_cmpr(img):
    h, w = len(img), len(img[0])
    pw, ph = padded(w, h)
    blank = (0, 0, 0, 0)
    out = bytearray()
    for ty in range(0, ph, 8):
        for tx in range(0, pw, 8):
            for sub in range(4):
                bx, by = tx + (sub & 1) * 4, ty + (sub >> 1) * 4
                px = [img[y][x] if y < h and x < w else blank for y in range(by, by + 4) for x in range(bx, bx + 4)]
                out += _encode_block(px)
    return bytes(out)


def resize(img, w, h):
    """Bilinear resize; colours are weighted by alpha so transparent pixels do not darken the edges."""
    sh, sw = len(img), len(img[0])
    out = []
    for y in range(h):
        fy = min(max((y + 0.5) * sh / h - 0.5, 0), sh - 1)
        y0 = int(fy)
        y1, wy = min(y0 + 1, sh - 1), fy - y0
        row = []
        for x in range(w):
            fx = min(max((x + 0.5) * sw / w - 0.5, 0), sw - 1)
            x0 = int(fx)
            x1, wx = min(x0 + 1, sw - 1), fx - x0
            acc, alpha = [0.0, 0.0, 0.0], 0.0
            for px, weight in ((img[y0][x0], (1 - wx) * (1 - wy)), (img[y0][x1], wx * (1 - wy)),
                               (img[y1][x0], (1 - wx) * wy), (img[y1][x1], wx * wy)):
                a = px[3] * weight
                alpha += a
                for c in range(3):
                    acc[c] += px[c] * a
            if alpha > 0:
                row.append(tuple(int(round(v / alpha)) for v in acc) + (int(round(alpha)),))
            else:
                row.append((0, 0, 0, 0))
        out.append(row)
    return out


def write_png(path, img):
    h, w = len(img), len(img[0])
    raw = b"".join(b"\0" + bytes(c for px in row for c in px) for row in img)

    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
