"""Locate the MinionLoad_* registry objects in a global.bld and show what references their names."""
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
from igzobj import IgzFile  # noqa: E402


def global_igz(path):
    a = iga.read(path)
    return max(a.entries, key=lambda e: len(e.data)).data  # the level data is by far the largest entry


if __name__ == "__main__":
    f = IgzFile(global_igz(sys.argv[1]))
    print(f"{len(f.objects)} objects, {len(f.types)} types, sections {len(f.sections)}")
    # every pointer-like fixup field: (tag, field position, target position)
    refs = []
    for tag, offs in f.fixups.items():
        if tag == 5:
            continue
        for enc in offs:
            p = f.pos(enc)
            if p is not None:
                refs.append((tag, p, f.pos(f.u32(p))))
    by_target = collections.defaultdict(list)
    for tag, p, tgt in refs:
        if tgt is not None:
            by_target[tgt].append((tag, p))
    hits = [(m.start(), m.group().decode()) for m in re.finditer(rb"MinionLoad_[\w]+", f.data)]
    print(f"{len(hits)} MinionLoad strings")
    for spos, name in hits[:3] + hits[-2:]:
        print(f"== {name} at {spos:#x}")
        for tag, p in by_target.get(spos, []):
            o = f.object_at(p)
            print(f"   referenced by fixup {tag:#04x} at {p:#x} in {o[2] if o else '?'} "
                  f"(object {o[0]:#x}, size {o[3]:#x}, field +{p - o[0]:#x})" if o else f"   fixup {tag:#04x} at {p:#x}")
