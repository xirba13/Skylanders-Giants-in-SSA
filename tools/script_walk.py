"""Walk everything reachable from a script set's ScriptStructures; report type counts, int literals
(RHSValueStack +0x20) and which named ScriptSets are referenced."""
import bisect
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import paths  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402
from list_sets import sets  # noqa: E402

a = iga.read(paths.ssa("permanent", "global.bld"))
doc = IgzDoc(max(a.entries, key=lambda e: len(e.data)).data)
objs = sorted((enc, doc.types[doc.u32(enc)], doc.type_sizes[doc.u32(enc)]) for enc in doc.lists[0x05])
starts = [o[0] for o in objs]
ptr_fields = sorted(doc.lists[0x06])
string_fields = set(doc.lists[0x0E])


def owner(p):
    i = bisect.bisect_right(starts, p) - 1
    return objs[i] if i >= 0 and objs[i][0] <= p < objs[i][0] + objs[i][2] else None


def out_refs(start, size):
    """Pointer targets of fields inside [start, start+size), following raw buffers one level."""
    i = bisect.bisect_left(ptr_fields, start)
    while i < len(ptr_fields) and ptr_fields[i] < start + size:
        yield doc.u32(ptr_fields[i])
        i += 1


def reach(roots, limit=200000):
    seen, todo = set(), list(roots)
    while todo and len(seen) < limit:
        t = todo.pop()
        o = owner(t)
        if o is None:  # raw buffer: follow its pointer elements up to the next object or 4 KB
            if ("buf", t) in seen:
                continue
            seen.add(("buf", t))
            nxt = starts[bisect.bisect_right(starts, t)] if bisect.bisect_right(starts, t) < len(starts) else t + 0x1000
            todo.extend(out_refs(t, min(nxt - t, 0x1000)))
            continue
        if o[0] in seen:
            continue
        seen.add(o[0])
        todo.extend(out_refs(o[0], o[2]))
    return {s for s in seen if not isinstance(s, tuple)}


def script_roots(substr):
    """tfbScriptInfo objects whose source path contains substr -> {path: content pointer (+0x14)}."""
    t = doc.type_index("tfbScriptInfo")
    out = {}
    for enc in doc.lists[0x05]:
        if doc.u32(enc) == t:
            path = doc.cstr(doc.u32(enc + 8))
            if substr.lower() in path.lower():
                out[path] = doc.u32(enc + 0x14)
    return out


if __name__ == "__main__":
    set_names = {enc: nm for enc, nm, _, _ in sets(doc)}
    for path, root in script_roots(sys.argv[1]).items():
        got = reach([root])
        types = collections.Counter(doc.types[doc.u32(e)] for e in got)
        lit = collections.Counter(doc.u32(e + 0x20) for e in got if doc.types[doc.u32(e)] == "RHSValueStack")
        strings = sorted({doc.cstr(doc.u32(e + 8)) for e in got if doc.types[doc.u32(e)] == "StringInfo"})
        print(f"== {path.split('/')[-1]}: {len(got)} objects")
        print("   int literals:", sorted(lit)[:60])
        print("   sets:", sorted({set_names[e] for e in got if e in set_names})[:40])
        print("   strings:", strings[:25])
