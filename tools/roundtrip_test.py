"""Round-trip check for igzdoc: every IGZ file in the given archives must rebuild byte-identically,
both as-is and with all packed fixup lists and the type tables re-encoded from scratch.

usage: python tools/roundtrip_test.py [archives...]   (default: a sample from both games)
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import paths  # noqa: E402
from igzdoc import IgzDoc, PACKED  # noqa: E402


def check(data):
    doc = IgzDoc(data)
    if doc.to_bytes() != data:
        return "as-is differs"
    doc = IgzDoc(data)
    doc._packed_dirty = set(t for t in PACKED if t in doc.lists)
    doc._types_dirty = True
    out = doc.to_bytes()
    if out != data:
        n = next(i for i in range(min(len(out), len(data))) if out[i] != data[i]) if len(out) == len(data) else -1
        return f"re-encoded differs (len {len(out)} vs {len(data)}, first diff {n:#x})"
    return None


def main():
    archives = sys.argv[1:] or (
        [paths.ssa("permanent", "global.bld")] + sorted(glob.glob(paths.ssa("character", "*.bld")))[:12]
        + [paths.giants("permanent", "global.bld")] + sorted(glob.glob(paths.giants("character", "1*.bld")))[:10]
        + [paths.ssa("character", "016_Spyro.arc"), paths.giants("character", "112_TitanLife.arc")])
    files = ok = 0
    for a in archives:
        for e in iga.read(a).entries:
            if e.data[:4] != b"IGZ\x01":
                continue
            files += 1
            err = check(e.data)
            if err:
                print(f"FAIL {os.path.basename(a)}:{e.name[-50:]}: {err}")
            else:
                ok += 1
    print(f"{ok}/{files} IGZ files round-trip byte-identically")


if __name__ == "__main__":
    main()
