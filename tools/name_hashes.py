"""Build a dictionary FNV-1a hash -> name from everything nameable in both games, to identify import targets.

Sources: disc file names, archive entry names (and their path pieces), and every string in the String pool of the
global.bld levels and of the given character archives. Several spellings of each are hashed (as is, lower case,
without extension, basename).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import paths  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402


def spellings(name):
    out = {name}
    base = re.split(r"[\\/]", name)[-1]
    for n in (name, base):
        stem = n.rsplit(".", 1)[0]
        out.update({n, n.lower(), stem, stem.lower()})
    return {s for s in out if s}


def strings_of(data):
    try:
        d = IgzDoc(data)
        blob = bytes(d.blobs[d.section_by_pool("String")])
    except Exception:
        return []
    return [s.decode("latin1") for s in blob.split(b"\0") if s]


def build(archives):
    table = {}
    names = set()
    for root in (paths.ssa(), paths.giants()):
        for dp, dn, fn in os.walk(root):
            names.update(fn)
    for p in archives:
        a = iga.read(p)
        for e in a.entries:
            names.add(e.name)
            if e.data[:4] == b"IGZ\x01":
                names.update(strings_of(e.data))
    for n in names:
        for s in spellings(n):
            table.setdefault(iga.fnv1a(s.encode("latin1", "replace")), s)
    return table


if __name__ == "__main__":
    import pickle
    archives = [paths.ssa("permanent", "global.bld"), paths.giants("permanent", "global.bld"),
                paths.giants("character", "112_TitanLife.bld"), paths.ssa("character", "027_Ent.bld"),
                paths.ssa("misc", "Init_Setup.bld"), paths.giants("character", "Init_Setup.bld")]
    table = build(archives)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "name_hashes.pickle")
    with open(out, "wb") as f:
        pickle.dump(table, f)
    print(len(table), "hashes ->", out)
