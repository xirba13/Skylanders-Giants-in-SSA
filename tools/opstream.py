"""Print a script's op stream (the OpCodeList array) with each op's +0x18 control word.

usage: python tools/opstream.py ARCHIVE [FIRST] [COUNT]  (FIRST may be an op index or 'find:<text>')
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from toy_table import Level  # noqa: E402


def op_list(lv):
    d = lv.doc
    t = d.type_index("OpCodeList")
    lists = [o for o in lv.objs if d.u32(o) == t]
    o = max(lists, key=lambda x: d.u32(x + 8))
    n, buf = d.u32(o + 8), d.u32(o + 0x14)
    return o, buf, [d.u32(buf + 4 * i) for i in range(n)]


def describe(lv, op):
    d = lv.doc
    t = lv.type(op)
    ctl = d.u32(op + 0x18) if d.type_sizes[d.u32(op)] > 0x18 else 0
    name = lv.name_of(op) or ""
    if t == "OpMacroParameter":
        name = d.cstr(d.u32(op + 0x1c))
    return f"{t:28} ctl={ctl >> 16:#x}:{ctl & 0xFFFF:<5} {name}"


if __name__ == "__main__":
    lv = Level(sys.argv[1])
    o, buf, ops = op_list(lv)
    first = sys.argv[2] if len(sys.argv) > 2 else "0"
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    if first.startswith("find:"):
        text = first[5:]
        first = next(i for i, op in enumerate(ops) if text in describe(lv, op))
    else:
        first = int(first, 0)
    print(f"OpCodeList@{o:#x}: {len(ops)} ops, buffer {buf:#x}")
    for i in range(max(0, first), min(len(ops), first + count)):
        print(f"  [{i:5}] {ops[i]:#08x} {describe(lv, ops[i])}")
