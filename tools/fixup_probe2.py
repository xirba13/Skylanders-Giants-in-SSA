"""Test: record 5 = object list. Decode with delta*4+4, offsets = (object section << 24) | offset."""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import igz  # noqa: E402
from igz_probe import load  # noqa: E402


def unpack_offsets(body, count):
    out, pos, prev = [], 0, 0
    for _ in range(count):
        value, shift = 0, 0
        while True:
            b = body[pos >> 1]
            nib = (b & 0xF) if (pos & 1) == 0 else (b >> 4)
            pos += 1
            value |= (nib & 7) << shift
            shift += 3
            if not nib & 8:
                break
        prev += value * 4 + 4
        out.append(prev)
    return out


def file_pos(h, enc):
    sec = enc >> 24
    off = enc & 0xFFFFFF
    s = h["sections"][sec + 1]  # encoded section 0 = first object section (file section 1)
    if off >= s[1]:
        return None
    return s[0] + off


if __name__ == "__main__":
    data = load(sys.argv[1])
    h = igz.header(data)
    recs = igz.records(data)
    names = igz.types(data)
    sizes = igz.type_sizes(data)
    for tag in sorted(t for t in recs if t in (5, 6, 7, 0xB, 0xE, 0xF, 0x10)):
        count, body = recs[tag]
        offs = unpack_offsets(body, count)
        pos = [file_pos(h, o) for o in offs]
        inside = sum(p is not None for p in pos)
        secs = collections.Counter(o >> 24 for o in offs)
        msg = f"tag {tag:#04x}: {count} offsets, {inside} inside their section, sections {dict(secs)}"
        if tag == 5:
            words = [struct.unpack_from(">I", data, p)[0] for p in pos if p is not None]
            valid = sum(w < len(names) for w in words)
            msg += f"; first word is a valid type index for {valid}/{len(words)}"
            kinds = collections.Counter(names[w] for w in words if w < len(names))
            msg += f"; most common: {kinds.most_common(4)}"
        print(msg)
