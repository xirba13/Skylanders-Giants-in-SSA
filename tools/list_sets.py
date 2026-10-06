"""List every ScriptSet in a global/level IGZ: name, element count and element types (optionally filtered)."""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402


def sets(doc):
    t_set = doc.type_index("ScriptSet")
    for enc in doc.lists[0x05]:
        if doc.u32(enc) != t_set:
            continue
        name = doc.cstr(doc.u32(enc + 8))
        lst = doc.u32(enc + 0x18)
        count = doc.u32(lst + 8) if lst else 0
        buf = doc.u32(lst + 0x14) if count else 0
        elems = [doc.u32(buf + 4 * k) for k in range(count)]
        kinds = collections.Counter(doc.types[doc.u32(e)] for e in elems)
        yield enc, name, elems, kinds


if __name__ == "__main__":
    a = iga.read(sys.argv[1])
    doc = IgzDoc(max(a.entries, key=lambda e: len(e.data)).data)
    pat = sys.argv[2].lower() if len(sys.argv) > 2 else ""
    for enc, name, elems, kinds in sets(doc):
        if pat and pat not in name.lower() and not any(pat in k.lower() for k in kinds):
            continue
        print(f"{enc:#010x} {len(elems):4} {name!r:45} {dict(kinds)}")
