"""Dump a script's objects in file order with their strings and small values, so the logic can be read.

usage: python tools/script_dump.py ssa|giants Script.ai [filter-regex]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
from script_literal_diff import load, script_objects  # noqa: E402

SKIP = {"RHSReferenceStack", "ReferenceStack", "ValueStack", "ScriptGroupStack"}


def line(doc, enc, strf, ptrs):
    t = doc.u32(enc)
    name, size = doc.types[t], doc.type_sizes[t]
    texts, nums = [], []
    for k in range(1, size // 4):
        f = enc + 4 * k
        v = doc.u32(f)
        if f in strf:
            texts.append(doc.cstr(v))
        elif f not in ptrs and 0 < v < 100000 and k > 1:
            nums.append(v)
    if name == "RHSValueStack":
        return f"    = {doc.u32(enc + 0x20)}" if doc.u32(enc + 0x1c) == 7 else None
    if name in SKIP or (not texts and name.startswith(("Value", "RHS"))):
        return None
    return f"{name}: " + " | ".join(texts) + (f"  {nums[:4]}" if nums and name.startswith("Op") else "")


if __name__ == "__main__":
    game, script = sys.argv[1], sys.argv[2]
    flt = re.compile(sys.argv[3], re.I) if len(sys.argv) > 3 else None
    doc = load(paths.ssa("permanent", "global.bld") if game == "ssa" else paths.giants("permanent", "global.bld"))
    strf, ptrs = set(doc.lists[0x0E]), set(doc.lists[0x06])
    out = []
    for enc in sorted(script_objects(doc)[script]):
        s = line(doc, enc, strf, ptrs)
        if s:
            out.append(f"{enc:#010x} {s}")
    if flt:
        hits = [i for i, s in enumerate(out) if flt.search(s)]
        shown = set()
        for i in hits:
            for j in range(max(0, i - 4), min(len(out), i + 5)):
                if j not in shown:
                    print(out[j])
                    shown.add(j)
            print("   ...")
    else:
        print("\n".join(out))
