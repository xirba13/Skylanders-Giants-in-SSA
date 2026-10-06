"""Compare the int literals (RHSValueStack +0x20) of same-named scripts in Spyro's Adventure and Giants global.bld.
Counts each literal per script so changed constants (e.g. 32 -> 115, 38 -> 68) stand out."""
import bisect
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import paths  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402


def load(path):
    a = iga.read(path)
    return IgzDoc(max(a.entries, key=lambda e: len(e.data)).data)


def script_objects(doc):
    """{script file name: [objects of that script]}, assigning each object to the script whose tfbScriptInfo
    content pointer is the closest one at or below it (scripts are laid out contiguously)."""
    t = doc.type_index("tfbScriptInfo")
    starts = []
    for enc in doc.lists[0x05]:
        if doc.u32(enc) == t:
            starts.append((doc.u32(enc + 0x14), doc.cstr(doc.u32(enc + 8)).split("/")[-1]))
    starts.sort()
    keys = [s for s, _ in starts]
    out = collections.defaultdict(list)
    for enc in doc.lists[0x05]:
        i = bisect.bisect_right(keys, enc) - 1
        if i >= 0 and enc >> 24 == keys[i] >> 24:
            out[starts[i][1]].append(enc)
    return out


def literals(doc, objs):
    t = doc.type_index("RHSValueStack")
    return collections.Counter(doc.u32(e + 0x20) for e in objs if doc.u32(e) == t)


if __name__ == "__main__":
    names = sys.argv[1:] or ["PortalManager.ai", "Spyro_PortalManager.ai", "PortalControl.ai", "SaveGame_Init.ai",
                             "Portal_ObjectLevelLoads.ai", "SaveGame_Portal.ai", "PortalControl_Items.ai"]
    ssa, gi = load(paths.ssa("permanent", "global.bld")), load(paths.giants("permanent", "global.bld"))
    so, go = script_objects(ssa), script_objects(gi)
    for n in names:
        a, b = literals(ssa, so.get(n, [])), literals(gi, go.get(n, []))
        small = lambda c: {k: v for k, v in c.items() if k < 5000}
        only_a = {k: v for k, v in small(a).items() if k not in b}
        only_b = {k: v for k, v in small(b).items() if k not in a}
        print(f"== {n}: SSA {len(so.get(n, []))} objects, Giants {len(go.get(n, []))}")
        print(f"   only in SSA: {dict(sorted(only_a.items()))}")
        print(f"   only in Giants: {dict(sorted(only_b.items()))}")
