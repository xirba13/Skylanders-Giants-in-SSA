"""Search every archive entry on a disc (decompressed) for byte strings.

usage: python tools/grep_disc.py ssa|giants "text1" ["text2" ...] [--glob "*.bld"]
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import paths  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("game")
ap.add_argument("needles", nargs="+")
ap.add_argument("--glob", default="*.bld")
a = ap.parse_args()
root = paths.ssa() if a.game == "ssa" else paths.giants()
needles = [n.encode() for n in a.needles]
for path in sorted(glob.glob(os.path.join(root, "**", a.glob), recursive=True)):
    try:
        arch = iga.read(path)
    except Exception as e:
        print(f"skip {path}: {e}")
        continue
    for e in arch.entries:
        found = [n.decode() for n in needles if n in e.data]
        if found:
            print(f"{os.path.relpath(path, root)} : {e.name[-60:]} : {found}")
