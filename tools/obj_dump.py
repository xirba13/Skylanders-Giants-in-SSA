"""Dump every object in an address range of any level archive, with all fields and which fixup list covers them.

usage: python tools/obj_dump.py ARCHIVE START END
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from toy_table import Level  # noqa: E402

lv = Level(sys.argv[1])
d = lv.doc
start, end = int(sys.argv[2], 16), int(sys.argv[3], 16)
member = {}
for tag, lst in d.lists.items():
    for enc in lst:
        member.setdefault(enc, []).append(tag)


def label(v):
    o = lv.obj_at(v)
    if o is None:
        return f"buf@{v:#x}"
    n = lv.name_of(o)
    return f"{lv.type(o)}@{o:#x}" + (f"('{n}')" if n else "") + (f"+{v - o:#x}" if v != o else "")


p = start
while p < end:
    o = lv.obj_at(p)
    if o is None:  # raw memory between objects (buffers)
        nxt = next((x for x in lv.objs if x > p), end)
        words = []
        for q in range(p, min(nxt, end, p + 0x40), 4):
            v = d.u32(q)
            tags = member.get(q, [])
            words.append(f"{v:08x}{'*' if 6 in tags else ''}{'h' if 7 in tags else ''}" + (f"->{label(v)}" if 6 in tags else ""))
        print(f"{p:#08x} [raw {nxt - p:#x} bytes] " + " ".join(words))
        p = nxt
        continue
    size = d.type_sizes[d.u32(o)]
    fields = []
    for k in range(1, size // 4):
        f = o + 4 * k
        v = d.u32(f)
        tags = member.get(f, [])
        if 0x0E in tags:
            fields.append(f"+{4*k:x}='{d.cstr(v)}'")
        elif 6 in tags:
            fields.append(f"+{4*k:x}->{label(v)}")
        elif 7 in tags:
            fields.append(f"+{4*k:x}=handle({v:#x})")
        elif v:
            fields.append(f"+{4*k:x}={v:#x}" + (f"[{','.join(hex(t) for t in tags)}]" if tags else ""))
    print(f"{o:#08x} {lv.type(o)} size {size:#x}: " + " ".join(fields))
    p = o + size
