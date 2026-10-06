"""Offline layout check: do the object types used by Giants files have the same size in Spyro's Adventure?

Reference sizes come from every IGZ file in Spyro's Adventure's character, misc and permanent .bld archives.
A type whose size differs between the games changed layout and needs field-by-field conversion.

usage: python tools/layout_check.py [character base names...]   (default: the 8 Giants and Giants' Spyro)
"""
import collections
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import igz  # noqa: E402
import paths  # noqa: E402

GIANTS = {"101_BugmanGiant": "Swarm", "102_Titan_Earth": "Crusher", "104_OilBlazer": "Hot Head",
          "107_Whale": "Thumpback", "109_Djini": "Ninjini", "110_RobotGiant": "Bouncer",
          "112_TitanLife": "Tree Rex", "114_Mummy": "Eye-Brawl"}


def igz_files(archive_path):
    for e in iga.read(archive_path).entries:
        if e.data[:4] == igz.MAGIC:
            yield e.name, e.data


def collect(paths_list):
    sizes = collections.defaultdict(set)
    for p in paths_list:
        for _, data in igz_files(p):
            for t, s in igz.type_sizes(data).items():
                sizes[t].add(s)
    return sizes


def main():
    targets = sys.argv[1:] or list(GIANTS) + ["016_Spyro"]
    ref_paths = []
    for sub in ("character", "misc", "permanent"):
        ref_paths += sorted(glob.glob(paths.ssa(sub, "*.bld")))
    ref = collect(ref_paths)
    print(f"reference: {len(ref)} types from {len(ref_paths)} Spyro's Adventure archives")
    conflicted = {t for t, s in ref.items() if len(s) > 1}
    if conflicted:
        print(f"  note: {len(conflicted)} types already vary within Spyro's Adventure: {sorted(conflicted)[:8]}")

    total_missing, total_changed = collections.Counter(), {}
    for base in targets:
        label = GIANTS.get(base, base)
        files = [paths.giants("character", base + ext) for ext in (".bld", ".arc")]
        sizes = collect(files)
        missing = sorted(t for t in sizes if t not in ref)
        changed = {t: (sorted(ref[t]), sorted(s)) for t, s in sizes.items() if t in ref and not (s & ref[t])}
        total_missing.update(missing)
        total_changed.update(changed)
        print(f"{label:10} {len(sizes):4} types: {len(missing)} not seen in SSA files, {len(changed)} with a different size")
    print()
    print("types not seen in any Spyro's Adventure file (count = characters using them):")
    for t, n in total_missing.most_common():
        print(f"  {n}  {t}")
    print("types whose size differs (SSA sizes -> Giants sizes):")
    for t, (a, b) in sorted(total_changed.items()):
        print(f"  {t:40} {[hex(x) for x in a]} -> {[hex(x) for x in b]}")


if __name__ == "__main__":
    main()
