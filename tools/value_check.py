"""Find moved scalar fields: pair same-named objects of each type in Spyro's two versions (Spyro is on both
discs) and compare them word by word. An offset whose values rarely agree while the same values sit at another
offset in the Giants object points to a moved field.

usage: python tools/value_check.py [stem, default 016_Spyro]
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert  # noqa: E402
import paths  # noqa: E402
from toy_table import Level  # noqa: E402


def named(lv):
    """{(type, name): [object]} using the first string field of each object."""
    d = lv.doc
    out = collections.defaultdict(list)
    for o in lv.objs:
        t = d.types[d.u32(o)]
        for off in range(8, min(d.type_sizes[d.u32(o)], 0x40), 4):
            if o + off in lv.strf:
                out[(t, d.cstr(d.u32(o + off)))].append(o)
                break
    return out


def words(lv, o, skip):
    d = lv.doc
    size = d.type_sizes[d.u32(o)]
    return {off: (None if (o + off) in skip else d.u32(o + off)) for off in range(4, size, 4)}


def main():
    stem = sys.argv[1] if len(sys.argv) > 1 else "016_Spyro"
    s = Level(paths.ssa("character", stem + ".bld"))
    g = Level(paths.giants("character", stem + ".bld"))
    skip_s = set(s.ptrs) | s.strf | set(s.doc.lists.get(0x07, ()))
    skip_g = set(g.ptrs) | g.strf | set(g.doc.lists.get(0x07, ()))
    sn, gn = named(s), named(g)
    by_type = collections.defaultdict(list)
    for key, objs in sn.items():
        if key in gn and len(objs) == 1 and len(gn[key]) == 1:
            by_type[key[0]].append((objs[0], gn[key][0]))
    for t, pairs in sorted(by_type.items()):
        if t in convert.TYPE_MAPS:
            continue
        if s.doc.type_sizes[s.doc.type_index(t)] != g.doc.type_sizes[g.doc.type_index(t)]:
            continue
        same, moved = collections.Counter(), collections.Counter()
        total = collections.Counter()
        for so, go in pairs:
            ws, wg = words(s, so, skip_s), words(g, go, skip_g)
            for off, v in ws.items():
                if v is None or wg.get(off) is None:
                    continue
                total[off] += 1
                if wg[off] == v:
                    same[off] += 1
                elif v not in (0, 0xFFFFFFFF, 1):
                    for off2, v2 in wg.items():
                        if off2 != off and v2 == v:
                            moved[(off, off2)] += 1
        bad = [off for off in total if total[off] >= 3 and same[off] / total[off] < 0.5]
        if bad:
            hints = {off: [f"{o2:#x}x{c}" for (o1, o2), c in moved.most_common() if o1 == off][:2] for off in bad}
            print(f"{t} ({len(pairs)} pairs): offsets rarely equal: " +
                  ", ".join(f"+{off:#x} ({same[off]}/{total[off]}, found at {hints[off]})" for off in sorted(bad)))


if __name__ == "__main__":
    main()
