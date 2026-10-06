"""Show the script objects around RHSValueStack literals with a given value in one script."""
import bisect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
from script_literal_diff import load, script_objects  # noqa: E402


def describe(doc, enc, strf, ptrs):
    t = doc.u32(enc)
    name, size = doc.types[t], doc.type_sizes[t]
    parts = []
    for k in range(1, size // 4):
        f = enc + 4 * k
        v = doc.u32(f)
        if f in strf:
            parts.append(f"+{4*k:#x}='{doc.cstr(v)}'")
        elif f in ptrs:
            parts.append(f"+{4*k:#x}->{v:#x}")
        elif v:
            parts.append(f"+{4*k:#x}={v:#x}")
    return f"{enc:#010x} {name:22} " + " ".join(parts[:10])


if __name__ == "__main__":
    game, script, value = sys.argv[1], sys.argv[2], int(sys.argv[3], 0)
    doc = load(paths.ssa("permanent", "global.bld") if game == "ssa" else paths.giants("permanent", "global.bld"))
    objs = sorted(script_objects(doc)[script])
    strf, ptrs = set(doc.lists[0x0E]), set(doc.lists[0x06])
    t = doc.type_index("RHSValueStack")
    for i, enc in enumerate(objs):
        if doc.u32(enc) == t and doc.u32(enc + 0x20) == value:
            print(f"--- literal {value} at {enc:#x}")
            for j in range(max(0, i - 6), min(len(objs), i + 4)):
                print("   " + describe(doc, objs[j], strf, ptrs))
