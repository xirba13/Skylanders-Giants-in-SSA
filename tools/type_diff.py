"""Compare one object type's layout between Giants and Spyro's Adventure, word by word.

usage: python tools/type_diff.py TYPE [samples]

For each 4-byte field it prints, per game: the fixup kind (P pointer, S string, H handle, - none), how many
distinct values the instances have, the most common values and, for pointers, the types they point to. Fields with
matching patterns line up between the versions; the offsets that do not are where the layout changed.
"""
import collections
import glob
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import paths  # noqa: E402
from toy_table import Level  # noqa: E402


def levels(game):
    if game == "giants":
        files = [paths.giants("character", f + ".bld") for f in
                 ("112_TitanLife", "110_RobotGiant", "102_Titan_Earth", "107_Whale", "016_Spyro")]
    else:
        files = [paths.ssa("character", f) for f in ("027_Ent.bld", "016_Spyro.bld", "003_StormGiant.bld",
                                                     "021_DrillBot.bld", "015_Yeti.bld")]
    for p in files:
        yield Level(p)


def fmt(v):
    f = struct.unpack(">f", struct.pack(">I", v))[0]
    if v and 1e-4 < abs(f) < 1e6 and (v >> 23) & 0xFF not in (0, 0xFF):
        return f"{v:08x}({f:.4g})"
    return f"{v:08x}"


def profile(game, tname, samples):
    fields = collections.defaultdict(list)  # offset -> [(kind, value, target type)]
    size, count = None, 0
    for lv in levels(game):
        d = lv.doc
        if tname not in d.types:
            continue
        t = d.type_index(tname)
        size = d.type_sizes[t]
        handles = set(d.lists.get(0x07, ()))
        objs = [o for o in lv.objs if d.u32(o) == t]
        for o in objs[:samples]:
            count += 1
            for off in range(0, size, 4):
                f = o + off
                v = d.u32(f)
                if f in lv.ptrs:
                    tgt = lv.obj_at(v)
                    fields[off].append(("P", v, lv.type(tgt) if tgt is not None else "buf"))
                elif f in lv.strf:
                    fields[off].append(("S", v, d.cstr(v)[:24]))
                elif f in handles:
                    fields[off].append(("H", v, None))
                else:
                    fields[off].append(("-", v, None))
    return size, count, fields


def show(game, size, count, fields):
    print(f"--- {game}: size {size:#x}, {count} instances")
    for off in sorted(fields):
        entries = fields[off]
        kinds = collections.Counter(k for k, _, _ in entries)
        kind = "/".join(kinds)
        if "P" in kinds or "S" in kinds:
            tg = collections.Counter(t for k, _, t in entries if t is not None)
            desc = ", ".join(f"{t}x{c}" for t, c in tg.most_common(3))
        else:
            vals = collections.Counter(v for _, v, _ in entries)
            desc = f"{len(vals)} distinct: " + ", ".join(f"{fmt(v)}x{c}" for v, c in vals.most_common(4))
        print(f"  +{off:#04x} {kind:5} {desc}")


def main():
    tname = sys.argv[1]
    samples = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    for game in ("ssa", "giants"):
        size, count, fields = profile(game, tname, samples)
        if size is None:
            print(f"--- {game}: no {tname}")
            continue
        show(game, size, count, fields)


if __name__ == "__main__":
    main()
