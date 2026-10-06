"""Exploration helper: try nibble-packed delta decodings of the packed fixup records."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import igz  # noqa: E402
from igz_probe import load  # noqa: E402


def unpack(body, count, high_first, scale):
    """Variable-length nibbles: 3 data bits + continuation bit; values are deltas, scaled."""
    out, pos, prev = [], 0, 0
    for _ in range(count):
        value, shift = 0, 0
        while True:
            b = body[pos >> 1]
            nib = (b >> 4) if ((pos & 1) == 0) == high_first else (b & 0xF)
            pos += 1
            value |= (nib & 7) << shift
            shift += 3
            if not nib & 8:
                break
        prev += value * scale
        out.append(prev)
    return out, (pos + 1) // 2


if __name__ == "__main__":
    data = load(sys.argv[1])
    h = igz.header(data)
    recs = igz.records(data)
    ntypes = len(igz.types(data))
    print("sections:", [(hex(o), hex(s)) for o, s, a, p in h["sections"]])
    for tag in (5, 6, 7, 0xB, 0xE, 0xF, 0x10):
        count, body = recs[tag]
        for high_first in (False, True):
            for scale in (4, 1):
                vals, used = unpack(body, count, high_first, scale)
                print(f"tag {tag:#04x} hi={high_first:d} x{scale}: used {used}/{len(body)} bytes, "
                      f"first {[hex(v) for v in vals[:6]]} last {hex(vals[-1])}")
