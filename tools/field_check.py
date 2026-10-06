"""Find types whose fields moved between the games even though their size did not change.

For every type a Giants character uses, the per-offset fixup profile is compared between Spyro's Adventure
characters and Giants characters: which offsets hold pointers (P, with the types they point to), string
references (S), import handles (H), memory-block indices (B), memory sizes (Z) or class numbers (C). A type that
is not in convert.TYPE_MAPS but shows a different profile has moved fields and needs a mapping. (Found this way:
igBlendMatrixSelect, whose bone index list moved from +0xB0 to +0xB4 in Giants; test 14 crashed on it.)

usage: python tools/field_check.py [Giants character stem ...]
"""
import collections
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert  # noqa: E402
import paths  # noqa: E402
from toy_table import Level  # noqa: E402

KIND = {0x06: "P", 0x0E: "S", 0x07: "H", 0x0B: "B", 0x0F: "Z", 0x10: "C"}
SSA_SAMPLE = ["016_Spyro", "027_Ent", "003_StormGiant", "021_DrillBot", "015_Yeti", "018_Wizard", "007_GemGolem",
              "009_Eruptor", "031_GhostEater", "002_SkyTurtle"]
GIANTS_SAMPLE = ["016_Spyro", "021_DrillBot", "003_StormGiant", "027_Ent", "015_Yeti"]


def profile(paths_list, wanted=None):
    """{type: {offset: Counter(kind)}} and instance counts."""
    prof = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    counts = collections.Counter()
    for p in paths_list:
        lv = Level(p)
        d = lv.doc
        lists = {tag: set(d.lists.get(tag, ())) for tag in KIND}
        for o in lv.objs:
            tidx = d.u32(o)
            t = d.types[tidx]
            if wanted is not None and t not in wanted:
                continue
            counts[t] += 1
            for off in range(4, d.type_sizes[tidx], 4):
                kinds = [KIND[tag] for tag, s in lists.items() if o + off in s]
                if "P" in kinds:
                    tgt = lv.obj_at(d.u32(o + off))
                    kinds = [k if k != "P" else f"P:{lv.type(tgt) if tgt is not None else 'buf'}" for k in kinds]
                prof[t][off][",".join(sorted(kinds)) or "-"] += 1
    return prof, counts


def summarize(c):
    return "/".join(sorted(k for k in c if k != "-")) or "-"


def compare(stems):
    giants_paths = [paths.giants("character", s + ".bld") for s in stems]
    wanted = set()
    for p in giants_paths:
        wanted.update(Level(p).doc.types)
    ssa_paths = [paths.ssa("character", s + ".bld") for s in SSA_SAMPLE]
    gref_paths = [paths.giants("character", s + ".bld") for s in GIANTS_SAMPLE] + giants_paths
    sp, sc = profile(ssa_paths, wanted)
    gp, gc = profile(gref_paths, wanted)
    findings = []
    for t in sorted(wanted):
        if t in convert.TYPE_MAPS or t not in sp or t not in gp:
            continue
        diffs = []
        for off in sorted(set(sp[t]) | set(gp[t])):
            a, b = summarize(sp[t].get(off, {})), summarize(gp[t].get(off, {}))
            # pointer target type names may differ across files only by optional objects; compare fixup kinds
            ka = {k.split(":")[0] for k in a.split("/")}
            kb = {k.split(":")[0] for k in b.split("/")}
            if ka != kb:
                diffs.append(f"+{off:#05x} ssa {a} | giants {b}")
        if diffs:
            findings.append((t, sc[t], gc[t], diffs))
    return findings


if __name__ == "__main__":
    stems = sys.argv[1:] or ["112_TitanLife"]
    for t, ns, ng, diffs in compare(stems):
        print(f"{t} (ssa {ns}, giants {ng} instances)")
        for line in diffs[:12]:
            print("    ", line)
