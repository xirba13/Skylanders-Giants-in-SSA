"""Exploration helper: for the Minion_Loads set, show every field and which fixup lists cover it."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from find_minions import global_igz  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402
import paths  # noqa: E402

doc = IgzDoc(global_igz(paths.ssa("permanent", "global.bld")))
member = {}
for tag, lst in doc.lists.items():
    for enc in lst:
        member.setdefault(enc, []).append(tag)
strings_sec = doc.section_by_pool("String")


def show(label, enc, nwords):
    print(f"{label} @ {enc:#010x}")
    for k in range(nwords):
        f = enc + 4 * k
        tags = [f"{t:#x}" for t in member.get(f, [])]
        v = doc.u32(f)
        note = ""
        if v >> 24 == strings_sec and "0xe" in tags:
            note = f"  '{doc.cstr(v)}'"
        print(f"   +{4 * k:#04x} {v:08x} {' '.join(tags)}{note}")


def find_set(name):
    t = doc.type_index("ScriptSet")
    for enc in doc.lists[0x05]:
        if doc.u32(enc) == t and doc.cstr(doc.u32(enc + 8)) == name:
            return enc


for name in ("Minion_Loads", "Minion_Loads_Legendary"):
    s = find_set(name)
    show(f"ScriptSet '{name}'", s, 7)
    lst = doc.u32(s + 0x18)
    show("  ScriptSetList", lst, 9)
    buf = doc.u32(lst + 0x14)
    show("  element buffer (first 3)", buf, 3)
    show("  StringInfo [0]", doc.u32(buf), 10)
print("types:", {t: doc.types.index(t) for t in ("ScriptSet", "ScriptSetList", "StringInfo")})
