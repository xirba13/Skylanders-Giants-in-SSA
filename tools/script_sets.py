"""Exploration helper: list the ScriptSets that contain MinionLoad names, with their name and every element."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from find_minions import global_igz  # noqa: E402
from igzobj import IgzFile  # noqa: E402


def string_at(f, enc):
    p = f.pos(enc)
    return f.cstr(p) if p is not None else None


def describe(f, enc):
    """Short description of a script value object (StringInfo, IntMeasurement, ...)."""
    p = f.pos(enc)
    o = f.object_at(p) if p is not None else None
    if not o:
        return f"?{enc:#x}"
    if o[2] == "StringInfo":
        return f"'{string_at(f, f.u32(o[0] + 8))}'"
    vals = [f"{f.u32(o[0] + 4 * k):#x}" for k in range(1, min(6, o[3] // 4))]
    return f"{o[2]}({', '.join(vals)})"


if __name__ == "__main__":
    f = IgzFile(global_igz(sys.argv[1]))
    for o in f.objects:
        if o[2] != "ScriptSet":
            continue
        name = string_at(f, f.u32(o[0] + 8))
        lst = f.pos(f.u32(o[0] + 0x18))
        lo = f.object_at(lst) if lst is not None else None
        if not lo or lo[2] != "ScriptSetList":
            continue
        count, data = f.u32(lo[0] + 8), f.pos(f.u32(lo[0] + 0x14))
        elems = [describe(f, f.u32(data + 4 * k)) for k in range(count)] if data is not None else []
        if any("MinionLoad" in e for e in elems) or (name and "inion" in name):
            print(f"ScriptSet '{name}' @ {o[0]:#x}: {count} elements")
            for k, e in enumerate(elems[:100]):
                print(f"   [{k:2}] {e}")
