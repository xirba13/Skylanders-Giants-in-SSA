"""Exploration helper: which block table (u16 or u8) does each compressed entry use, by size?"""
import glob
import lzma
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import paths  # noqa: E402


def tables(d, ver):
    n = struct.unpack_from("<I", d, 12)[0]
    if ver == 4:
        ents_at = 0x30 + 4 * n
        n16, n8 = struct.unpack_from("<II", d, 0x24)
    else:
        ents_at = 0x34 + 4 * n
        n16, n8 = struct.unpack_from("<II", d, 0x28)  # guess for v8, checked below
    ents = [struct.unpack_from("<III", d, ents_at + 12 * i) for i in range(n)]
    t16_at = ents_at + 12 * n
    t16 = struct.unpack_from(f"<{n16}H", d, t16_at)
    t8 = d[t16_at + 2 * n16:t16_at + 2 * n16 + n8]
    return ents, t16, t8


def decodes(d, ver, off, size, vals, bit, mask):
    try:
        out = 0
        for v in vals[:-1]:
            want = min(0x8000, size - out)
            at = off + (v & mask) * 0x800
            if v & bit:
                iga._lzma_block(d, at, want, ver)
            out += want
        return out == size
    except Exception:
        return False


res = []
for path in sorted(glob.glob(paths.ssa("*", "*.bld"))) + sorted(glob.glob(paths.giants("*", "*.bld"))):
    d = open(path, "rb").read()
    ver = struct.unpack_from("<I", d, 4)[0]
    ents, t16, t8 = tables(d, ver)
    for off, size, flags in ents:
        if flags == iga.RAW or not flags >> 28:
            continue
        nb = (size + 0x7FFF) // 0x8000
        idx = flags & 0xFFFFFF
        u16 = idx + nb < len(t16) + 1 and decodes(d, ver, off, size, t16[idx:idx + nb + 1], 0x8000, 0x7FFF)
        u8 = idx + nb < len(t8) + 1 and decodes(d, ver, off, size, t8[idx:idx + nb + 1], 0x80, 0x7F)
        res.append((ver, size, nb, u16, u8))

for ver in (4, 8):
    r = [x for x in res if x[0] == ver]
    small = [x[1] for x in r if x[4] and not x[3]]
    big = [x[1] for x in r if x[3] and not x[4]]
    both = sum(1 for x in r if x[3] and x[4])
    neither = sum(1 for x in r if not x[3] and not x[4])
    print(f"v{ver}: {len(r)} entries; u8 only {len(small)} (max size {max(small) if small else None:}), "
          f"u16 only {len(big)} (min size {min(big) if big else None}), both {both}, neither {neither}")
