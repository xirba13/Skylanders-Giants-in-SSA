"""Convert the Giants version of a character that is on both discs and compare the result with Spyro's
Adventure's own file, object by object, for every type (converted ones included).

Objects are paired by type and name where the name is unique, then through the pointers of paired objects (same
field, same target type; list buffers element by element). For each type and offset the words of paired objects
are compared: pointers by target type, strings by text, other words by value. Offsets that rarely agree point to
a field the converter gets wrong; data that the Giants version changed (positions, colours, counts) shows up too,
so read the examples.

usage: python tools/converted_diff.py [stem[,stem...], default 016_Spyro] [--all] [--no-scripts]
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert_character  # noqa: E402
import iga  # noqa: E402
import paths  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402
import bisect  # noqa: E402


class View:
    def __init__(self, doc):
        self.doc = d = doc
        self.objs = sorted(d.lists[0x05])
        self.ptrs = set(d.lists.get(0x06, ()))
        self.strf = set(d.lists.get(0x0E, ()))
        self.handles = set(d.lists.get(0x07, ()))
        self.sizes = set(d.lists.get(0x0F, ()))

    def type(self, o):
        return self.doc.types[self.doc.u32(o)]

    def size(self, o):
        return self.doc.type_sizes[self.doc.u32(o)]

    def obj_at(self, p):
        i = bisect.bisect_right(self.objs, p) - 1
        if i >= 0 and self.objs[i] <= p < self.objs[i] + self.size(self.objs[i]):
            return self.objs[i]
        return None

    def name(self, o):
        d = self.doc
        for off in range(8, min(self.size(o), 0x40), 4):
            if o + off in self.strf:
                return d.cstr(d.u32(o + off))
        return None


def level_doc(path):
    a = iga.read(path)
    return IgzDoc(next(e for e in a.entries if e.name == "level.bld").data)


def pair(a: View, b: View):
    names_a, names_b = collections.defaultdict(list), collections.defaultdict(list)
    for v, names in ((a, names_a), (b, names_b)):
        for o in v.objs:
            n = v.name(o)
            if n is not None:
                names[(v.type(o), n)].append(o)
    pairs = {}
    queue = []
    for key, objs in names_a.items():
        if len(objs) == 1 and len(names_b.get(key, ())) == 1:
            pairs[objs[0]] = names_b[key][0]
            queue.append((objs[0], names_b[key][0]))
    # then names that differ only in case or path spelling (Giants re-exported many paths in lower case)
    loose_a, loose_b = collections.defaultdict(list), collections.defaultdict(list)
    for names, loose in ((names_a, loose_a), (names_b, loose_b)):
        for (t, n), objs in names.items():
            loose[(t, n.lower().replace("\\", "/"))] += objs
    done_b = set(pairs.values())
    for key, objs in loose_a.items():
        if len(objs) == 1 and len(loose_b.get(key, ())) == 1 and objs[0] not in pairs \
                and loose_b[key][0] not in done_b:
            pairs[objs[0]] = loose_b[key][0]
            done_b.add(loose_b[key][0])
            queue.append((objs[0], loose_b[key][0]))
    used_b = set(pairs.values())

    def link(ta, tb):
        oa, ob = a.obj_at(ta), b.obj_at(tb)
        if oa is None or ob is None or oa != ta or ob != tb:
            return False
        if a.type(oa) != b.type(ob) or oa in pairs or ob in used_b:
            return True
        pairs[oa] = ob
        used_b.add(ob)
        queue.append((oa, ob))
        return True

    while queue:
        oa, ob = queue.pop()
        for off in range(4, min(a.size(oa), b.size(ob)), 4):
            if oa + off not in a.ptrs or ob + off not in b.ptrs:
                continue
            ta, tb = a.doc.u32(oa + off), b.doc.u32(ob + off)
            if not ta or not tb:
                continue
            if link(ta, tb):
                continue
            # a buffer: pair its pointer elements (size from the memory-size word before the field)
            if a.obj_at(ta) is None and b.obj_at(tb) is None:
                na = a.doc.u32(oa + off - 4) & 0xFFFFFF if a.doc.u32(oa + off - 4) & 0x80000000 else 0
                nb = b.doc.u32(ob + off - 4) & 0xFFFFFF if b.doc.u32(ob + off - 4) & 0x80000000 else 0
                for k in range(0, min(na, nb), 4):
                    if ta + k in a.ptrs and tb + k in b.ptrs:
                        ea, eb = a.doc.u32(ta + k), b.doc.u32(tb + k)
                        if ea and eb:
                            link(ea, eb)
    return pairs


def describe(v: View, o, off):
    enc = o + off
    d = v.doc
    w = d.u32(enc)
    if enc in v.ptrs:
        if not w:
            return "null"
        t = v.obj_at(w)
        return f"->{v.type(t)}" + (f"+{w - t:#x}" if w != t else "") if t is not None else "->buf"
    if enc in v.strf:
        return f"'{d.cstr(w)}'"
    if enc in v.handles:
        return "handle"
    return f"{w:08x}"


def category(desc):
    """Kind of a described word: null, a pointer to some type, a string, a handle or a plain value."""
    if desc.startswith("->"):
        return desc.split("+")[0]
    if desc.startswith("'"):
        return "str"
    if desc in ("null", "handle"):
        return desc
    return "value"


def compare(a: View, b: View, pairs):
    """{type: {offset: [same, total, examples, structural differences {(kind a, kind b): count}]}}"""
    stats = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, [], collections.Counter()]))
    for oa, ob in pairs.items():
        t = a.type(oa)
        for off in range(4, min(a.size(oa), b.size(ob)), 4):
            da, db = describe(a, oa, off), describe(b, ob, off)
            s = stats[t][off]
            s[1] += 1
            if da == db:
                s[0] += 1
                continue
            if len(s[2]) < 4:
                s[2].append((da, db))
            ka, kb = category(da), category(db)
            if ka != kb:
                s[3][(ka, kb)] += 1
    return stats


def block_check(a: View, b: View, pairs):
    """Paired vertex buffers: same block size, and the same pack data at the end of the block."""
    out = collections.Counter()
    ra, rb = a.doc.record(0x0A), b.doc.record(0x0A)
    for oa, ob in pairs.items():
        if a.type(oa) != "igVertexBuffer" or a.doc.u32(oa + 8) != b.doc.u32(ob + 8):
            continue
        sa, ea = struct.unpack_from(">II", ra.body, 8 * a.doc.u32(oa + 0x14))
        sb, eb = struct.unpack_from(">II", rb.body, 8 * b.doc.u32(ob + 0x14))
        same_size = sa == sb
        tail = a.doc.read(ea + (sa & 0xFFFFFF) - 16, 16) == b.doc.read(eb + (sb & 0xFFFFFF) - 16, 16)
        out[("same size" if same_size else f"size {sa & 0xFFFFFF:#x} vs {sb & 0xFFFFFF:#x}",
             "same last 16 bytes" if tail else "different last 16 bytes")] += 1
    return out


SCRIPT_PREFIXES = ("Op", "RHS", "Value", "Reference", "Position", "Script", "LHS", "Lhs", "Rhs")


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    stems = args[0].split(",") if args else ["016_Spyro"]
    show_all = "--all" in sys.argv
    skip_scripts = "--no-scripts" in sys.argv
    total = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, [], collections.Counter()]))
    npairs = collections.Counter()
    for stem in stems:
        need = convert_character.needed_globals(stem)
        extra = {d[:2]: 0 for d in need}  # placeholder indices: the import values are not compared
        data = iga.read(paths.giants("character", stem + ".bld"))
        level = next(e for e in data.entries if e.name == "level.bld")
        out, report = convert_character.convert_igz(level.data, convert_character.havok_templates(), extra,
                                                    strict=False)
        a, b = View(level_doc(paths.ssa("character", stem + ".bld"))), View(IgzDoc(out))
        pairs = pair(a, b)
        print(f"{stem}: {len(pairs)} of {len(a.objs)} Spyro's Adventure objects paired ({len(b.objs)} converted)",
              flush=True)
        sizes_a = {t: s for t, s in zip(a.doc.types, a.doc.type_sizes)}
        sizes_b = {t: s for t, s in zip(b.doc.types, b.doc.type_sizes)}
        for t in sorted(set(sizes_a) & set(sizes_b)):
            if sizes_a[t] != sizes_b[t]:
                print(f"  size differs: {t} {sizes_a[t]:#x} vs {sizes_b[t]:#x}")
        for oa in pairs:
            npairs[a.type(oa)] += 1
        blocks = block_check(a, b, pairs)
        if blocks:
            print("  vertex blocks:", dict(blocks))
        for t, offs in compare(a, b, pairs).items():
            for off, (same, n, ex, kinds) in offs.items():
                s = total[t][off]
                s[0] += same
                s[1] += n
                s[2] += ex[:max(0, 4 - len(s[2]))]
                s[3].update(kinds)
    for t in sorted(total):
        if skip_scripts and t.startswith(SCRIPT_PREFIXES):
            continue
        rows = []
        for off, (same, n, ex, kinds) in sorted(total[t].items()):
            if n and (show_all or (n >= 2 and same / n < 0.6)):
                rows.append(f"    +{off:#04x} {same}/{n} e.g. " + ", ".join(f"{x} vs {y}" for x, y in ex[:3]))
            # rare but structural: a pointer, string or handle on one side only (a list that only some objects
            # carry), which the agreement ratio hides
            structural = {k: c for k, c in kinds.items() if c >= 2}
            if structural:
                rows.append(f"    +{off:#04x} structural ({same}/{n} same): " +
                            ", ".join(f"{ka} vs {kb} x{c}" for (ka, kb), c in structural.items()))
        if rows:
            print(f"  {t} ({npairs[t]} pairs)")
            print("\n".join(rows))


if __name__ == "__main__":
    main()
