"""Dump every object in an address range of the global script data with all fields resolved.

usage: python tools/range_dump.py ssa|giants START END
"""
import bisect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
from script_literal_diff import load  # noqa: E402

game, start, end = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
doc = load(paths.ssa("permanent", "global.bld") if game == "ssa" else paths.giants("permanent", "global.bld"))
strf, ptrs = set(doc.lists[0x0E]), set(doc.lists[0x06])
objs = sorted(doc.lists[0x05])


def obj_at(p):
    i = bisect.bisect_right(objs, p) - 1
    if i >= 0:
        o = objs[i]
        if o <= p < o + doc.type_sizes[doc.u32(o)]:
            return o
    return None


def short(v):
    o = obj_at(v)
    if o is None:
        return f"buf:{v:#x}"
    t = doc.types[doc.u32(o)]
    if t == "StringInfo":
        return f"StringInfo('{doc.cstr(doc.u32(o + 8))}')"
    if t in ("ValueInfo", "ScriptSet"):
        return f"{t}('{doc.cstr(doc.u32(o + 8))}')"
    return f"{t}@{o:#x}" + (f"+{v - o:#x}" if v != o else "")


for o in objs[bisect.bisect_left(objs, start):bisect.bisect_left(objs, end)]:
    t = doc.u32(o)
    name, size = doc.types[t], doc.type_sizes[t]
    parts = []
    for k in range(1, size // 4):
        f = o + 4 * k
        v = doc.u32(f)
        if f in strf:
            parts.append(f"+{4*k:x}:'{doc.cstr(v)}'")
        elif f in ptrs:
            parts.append(f"+{4*k:x}:{short(v)}")
            if obj_at(v) is None:  # raw buffer: show its first pointer elements
                els = [doc.u32(v + 4 * j) for j in range(4)]
                parts.append("[" + ", ".join(short(e) if (v + 4 * j) in ptrs else f"{e:#x}" for j, e in enumerate(els)) + "]")
        elif v:
            parts.append(f"+{4*k:x}:{v:#x}")
    print(f"{o:#010x} {name}: " + "  ".join(parts))
