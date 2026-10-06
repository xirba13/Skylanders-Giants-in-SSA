"""Resolve a Giants character's imports and look for their counterparts in Spyro's Adventure.

usage: python tools/giant_imports.py [character file stem, default 112_TitanLife] [SSA stem to compare, default 027_Ent]

Imports into global.bld are resolved through each game's root list (import index = position + base; Giants 0x27,
Spyro's Adventure 0x29; below the base they are script classes from record 1). The counterpart in Spyro's
Adventure is the root-list object with the same type and name. Imports into other files are named
(name hash, file hash) pairs; they are compared with the pairs a Spyro's Adventure character imports.
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import giants  # noqa: E402
import iga  # noqa: E402
import langpack  # noqa: E402
import minions  # noqa: E402
import paths  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402

GLOBAL = iga.fnv1a(b"global.bld")


class Global:
    """A game's global.bld: root list, script classes, StringInfo translations."""

    def __init__(self, path, base):
        a = iga.read(path)
        self.doc = d = IgzDoc(max(a.entries, key=lambda e: len(e.data)).data)
        self.base = base
        self.classes = [x.decode("latin1") for x in d.record(1).body.split(b"\0") if x][:d.record(1).count]
        pack = next(e for e in a.entries if e.name.endswith(".pak"))
        self.pack = langpack.strings(IgzDoc(pack.data))
        self.ordinal = {o: k for k, o in enumerate(minions.string_infos(d))}
        n, buf = d.u32(minions.ROOT_LIST + 8), d.u32(minions.ROOT_LIST + 0x14)
        self.root = [d.u32(buf + 4 * k) for k in range(n)]
        self.by_name = {}
        for k, o in enumerate(self.root):
            key = self.key(o)
            if key:
                self.by_name.setdefault(key, k + base)

    def key(self, o):
        d = self.doc
        if o & 0x80000000:
            return None
        t = d.types[d.u32(o)]
        name = None
        for off in range(8, min(d.type_sizes[d.u32(o)], 0x20), 4):
            if (o + off) in set_strings(d):
                name = d.cstr(d.u32(o + off))
                break
        return (t, name) if name else None

    def describe(self, index):
        if index < self.base:
            return ("class", self.classes[index] if index < len(self.classes) else f"<{index:#x}>")
        k = index - self.base
        if k >= len(self.root):
            return ("<out of range>", hex(index))
        o = self.root[k]
        if o & 0x80000000:
            return ("<handle in root>", hex(o))
        key = self.key(o) or (self.doc.types[self.doc.u32(o)], None)
        if key[0] == "StringInfo":
            return key + (self.pack[self.ordinal[o]],)
        return key

    def find(self, desc):
        if desc[0] == "class":
            return self.classes.index(desc[1]) if desc[1] in self.classes else None
        return self.by_name.get(desc[:2])


def set_strings(d):
    """The doc's string-reference fields, cached on the doc itself (an id()-keyed cache can be reused by a new
    doc after the old one is freed)."""
    cached = getattr(d, "_string_fields", None)
    if cached is None:
        cached = d._string_fields = set(d.lists[0x0E])
    return cached


def imports(path):
    a = iga.read(path)
    d = IgzDoc(max(a.entries, key=lambda e: len(e.data)).data)
    rec = d.record(2)
    ents = [struct.unpack_from(">II", rec.body, 8 * k) for k in range(rec.count)]
    uses = collections.Counter()
    for enc in d.lists.get(0x07, ()):
        uses[d.u32(enc) & 0x7FFFFFFF] += 1
    return d, ents, uses


def main():
    stem = sys.argv[1] if len(sys.argv) > 1 else "112_TitanLife"
    ssa_stem = sys.argv[2] if len(sys.argv) > 2 else "027_Ent"
    gg = Global(paths.giants("permanent", "global.bld"), giants.GIANTS_EXPORT_BASE)
    sg = Global(paths.ssa("permanent", "global.bld"), minions.EXPORT_BASE)
    _, ents, uses = imports(paths.giants("character", stem + ".bld"))
    _, ssa_ents, _ = imports(paths.ssa("character", ssa_stem + ".bld"))
    ssa_pairs = set(ssa_ents)
    print(f"{stem}: {len(ents)} imports")
    missing_global, other = [], collections.Counter()
    for n, (idx, fh) in enumerate(ents):
        if fh == GLOBAL:
            desc = gg.describe(idx)
            match = sg.find(desc)
            status = f"SSA {match:#x}" if match is not None else "MISSING in SSA"
            if match is None:
                missing_global.append(desc)
            print(f"  [{n:3}] global {idx:#06x} {desc} -> {status}  ({uses[n]} uses)")
        else:
            other[(fh, (idx, fh) in ssa_pairs)] += 1
    print("other files (file hash, also imported by the SSA character): count")
    for (fh, shared), c in sorted(other.items()):
        print(f"   {fh:#010x} shared={shared}: {c}")
    print(f"global imports missing in Spyro's Adventure: {len(missing_global)}")


if __name__ == "__main__":
    main()
