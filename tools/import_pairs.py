"""Collect every (name hash, namespace hash) import pair used by any IGZ file of a game, plus every type name and
size, and cache them (build/<game>_imports.pickle). An engine member or class that some Spyro's Adventure file
imports exists in its engine.

usage: python tools/import_pairs.py ssa|giants
"""
import collections
import os
import pickle
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import paths  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    game = sys.argv[1]
    root = paths.ssa() if game == "ssa" else paths.giants()
    pairs = collections.Counter()
    types = collections.defaultdict(set)
    files = 0
    archives = []
    for dp, dn, fn in os.walk(root):
        archives += [os.path.join(dp, f) for f in fn if f.endswith((".bld", ".arc"))]
    archives.sort(key=os.path.getsize)
    for n, p in enumerate(archives):
        try:
            a = iga.read(p)
        except Exception as e:
            print("skip", p, e, flush=True)
            continue
        for e in a.entries:
            if e.data[:4] != b"IGZ\x01":
                continue
            try:
                d = IgzDoc(e.data)
            except Exception:
                continue
            files += 1
            for t, s in zip(d.types, d.type_sizes):
                types[t].add(s)
            for r in d.records:
                if r.tag == 0x02:
                    for k in range(r.count):
                        pairs[struct.unpack_from(">II", r.body, 8 * k)] += 1
        if n % 50 == 0:
            print(f"{n}/{len(archives)} archives, {files} igz files", flush=True)
    out = os.path.join(ROOT, "build", f"{game}_imports.pickle")
    with open(out, "wb") as f:
        pickle.dump({"pairs": pairs, "types": dict(types), "files": files}, f)
    print("done:", files, "igz files,", len(pairs), "pairs,", len(types), "types ->", out, flush=True)


if __name__ == "__main__":
    main()
