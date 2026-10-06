"""Readable dump of the script objects of any level IGZ (largest entry of an archive), optionally from the
OpDefineMacro whose name matches START up to the next macro definition.

usage: python tools/level_dump.py ARCHIVE [macro name] [--count N]
"""
import argparse
import bisect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("archive")
ap.add_argument("macro", nargs="?")
ap.add_argument("--count", type=int, default=400)
a = ap.parse_args()
arch = iga.read(a.archive)
doc = IgzDoc(max(arch.entries, key=lambda e: len(e.data)).data)
strf, ptrs = set(doc.lists[0x0E]), set(doc.lists[0x06])
objs = sorted(doc.lists[0x05])


def obj_at(p):
    i = bisect.bisect_right(objs, p) - 1
    if i >= 0 and objs[i] <= p < objs[i] + doc.type_sizes[doc.u32(objs[i])]:
        return objs[i]
    return None


def ref(v):
    o = obj_at(v)
    if o is None:
        return None
    t = doc.types[doc.u32(o)]
    if t in ("StringInfo", "ValueInfo", "ScriptSet", "OpCreateVariable", "OpDefineMacro", "OpDefineStructure", "OpMacroParameter"):
        for k in range(2, doc.type_sizes[doc.u32(o)] // 4):
            if o + 4 * k in strf:
                s = doc.cstr(doc.u32(o + 4 * k))
                if s not in ("parameter", "create variable||with|members"):
                    return f"{t}('{s}')"
    return t


def describe(o):
    t = doc.types[doc.u32(o)]
    size = doc.type_sizes[doc.u32(o)]
    parts = []
    for k in range(1, size // 4):
        f = o + 4 * k
        v = doc.u32(f)
        if f in strf:
            parts.append(f"'{doc.cstr(v)}'")
        elif f in ptrs:
            r = ref(v)
            if r is None:  # buffer: show the first elements
                els = []
                for j in range(4):
                    if v + 4 * j in ptrs:
                        els.append(ref(doc.u32(v + 4 * j)) or "?")
                parts.append("[" + ", ".join(els) + "]")
            elif not r.startswith(("OpDefineMacroStack", "OpMacroInterface")):
                parts.append(f"->{r}")
        elif t == "RHSValueStack" and k == 8:
            parts.append(f"literal={v}")
    return f"{o:#010x} {t}: " + " ".join(parts)


start = 0
if a.macro:
    t = doc.type_index("OpDefineMacro")
    start = next(i for i, o in enumerate(objs) if doc.u32(o) == t and a.macro in doc.cstr(doc.u32(o + 8)))
for o in objs[start:start + a.count]:
    print(describe(o))
