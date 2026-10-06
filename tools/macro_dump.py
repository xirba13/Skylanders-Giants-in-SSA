"""Print a script macro in op-stream order, indented by block nesting, with references resolved.

usage: python tools/macro_dump.py <archive .bld> "<macro name>" [--global <global.bld>] [--base 0x29]

References into global.bld (import handles) are resolved through its root list (import index = position + base)
and shown with their language-pack text when they are StringInfo objects.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_names  # noqa: E402
import iga  # noqa: E402
import langpack  # noqa: E402
import minions  # noqa: E402
import paths  # noqa: E402
import script_edit  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402
from opstream import op_list  # noqa: E402
from toy_table import Level  # noqa: E402

STACKS = ("RHSReferenceStack", "ReferenceStack", "RHSValueStack", "ValueStack", "SetStack")


class Resolver:
    def __init__(self, lv, global_path, base):
        self.lv, self.base = lv, base
        a = iga.read(global_path)
        self.g = IgzDoc(max(a.entries, key=lambda e: len(e.data)).data)
        self.sis = {o: k for k, o in enumerate(minions.string_infos(self.g))}
        eng = next((e for e in a.entries if e.name == "ENGLISH.pak"), None) or \
            next(e for e in a.entries if e.name.endswith(".pak"))
        self.pack = langpack.strings(IgzDoc(eng.data))
        self.ghash = iga.fnv1a(b"global.bld")
        self.handles = set(lv.doc.lists.get(0x07, ()))

    def global_obj(self, index):
        g = self.g
        if index < self.base:  # below the root list: script classes (record 1) and a few others
            names = [x.decode() for x in g.record(1).body.split(b"\0") if x]
            return f"class '{names[index]}'" if index < len(names) else f"<index {index:#x}>"
        o = minions.exported(g, index, self.base)
        if o & 0x80000000:
            return f"<global handle {o:#x}>"
        t = g.types[g.u32(o)]
        if t == "StringInfo":
            k = self.sis[o]
            return f"'{g.cstr(g.u32(o + 8))}'='{self.pack[k]}'"
        if t in ("ScriptSet", "ValueInfo", "ScriptStructure", "ScriptReference"):
            try:
                return f"{t}('{g.cstr(g.u32(o + 8))}')"
            except Exception:
                return t
        return t

    def element(self, field):
        lv, d = self.lv, self.lv.doc
        v = d.u32(field)
        if field in self.handles:
            idx, h = script_edit.import_of(lv, v)
            if h == self.ghash:
                return "G:" + self.global_obj(idx)
            return engine_names.import_name(idx, h) or f"import({idx:#x} in {h:#010x})"
        o = lv.obj_at(v)
        if o is None:
            return hex(v)
        t = lv.type(o)
        if t == "StringInfo":
            return f"local '{d.cstr(d.u32(o + 8))}'"
        return f"{t}('{lv.name_of(o)}')" if lv.name_of(o) else t

    def stack(self, o):
        lv, d = self.lv, self.lv.doc
        t = lv.type(o)
        if t in ("RHSValueStack", "ValueStack") and d.u32(o + 8) == 0 and d.u32(o + 0x1c) == 7:
            return f"={d.u32(o + 0x20)}"
        n, buf = d.u32(o + 8), d.u32(o + 0x14)
        if not buf or n > 16:
            return t
        return " . ".join(self.element(buf + 4 * k) for k in range(n))

    def value(self, v):
        lv, d = self.lv, self.lv.doc
        o = lv.obj_at(v)
        if o is None:
            return None
        t = lv.type(o)
        if t == "ValueRHSVariant":
            inner = lv.obj_at(d.u32(o + 8))
            return self.stack(inner) if inner is not None else t
        if t in STACKS:
            return self.stack(o)
        return None


def describe(lv, res, op):
    d = lv.doc
    t = lv.type(op)
    label = lv.name_of(op) or ""
    parts = []
    for k in range(2, d.type_sizes[d.u32(op)] // 4):
        f = op + 4 * k
        if f in lv.ptrs:
            v = res.value(d.u32(f))
            if v:
                parts.append(v)
    return f"{t} '{label}' " + " | ".join(parts)


def op_lists(lv):
    """Every OpCodeList's ops (a level with several scripts has one list per script)."""
    d = lv.doc
    t = d.type_index("OpCodeList")
    for o in lv.objs:
        if d.u32(o) == t:
            n, buf = d.u32(o + 8), d.u32(o + 0x14)
            yield o, [d.u32(buf + 4 * i) for i in range(n)]


def dump(path, macro, global_path, base, after=0):
    """Dump the block of the first op labelled `macro` (exact macro name, or 'find:<text>' for any op whose label
    contains text). Non-block ops get `after` following ops instead."""
    lv = Level(path)
    d = lv.doc
    res = Resolver(lv, global_path, base)
    found = None
    for lst, ops in op_lists(lv):
        for i, op in enumerate(ops):
            label = lv.name_of(op) or ""
            if (macro.startswith("find:") and macro[5:] in label) or                     (lv.type(op) == "OpDefineMacro" and label == macro):
                found = (lst, ops, i)
                break
        if found:
            break
    if not found:
        raise SystemExit(f"{macro!r} not found in any op stream")
    lst, ops, i0 = found
    print(f"OpCodeList {lst:#x}, {len(ops)} ops")
    span = d.u32(ops[i0] + 0x18) & 0xFFFF if lv.type(ops[i0]) in script_edit.COUNTING else after
    end = min(len(ops) - 1, i0 + span)
    closes = []
    for i in range(i0, end + 1):
        while closes and i > closes[-1]:
            closes.pop()
        op = ops[i]
        print(f"{i:5d} " + "  " * len(closes) + describe(lv, res, op))
        if lv.type(op) in script_edit.COUNTING and i != i0:
            closes.append(i + (d.u32(op + 0x18) & 0xFFFF))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("archive")
    ap.add_argument("macro")
    ap.add_argument("--global", dest="global_path", default=paths.ssa("permanent", "global.bld"))
    ap.add_argument("--base", type=lambda s: int(s, 0), default=minions.EXPORT_BASE)
    ap.add_argument("--after", type=int, default=40, help="ops to show after a non-block op")
    a = ap.parse_args()
    dump(a.archive, a.macro, a.global_path, a.base, a.after)
