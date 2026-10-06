"""Names of the engine members and classes scripts import by hash.

An import (record 2 entry) names its target by two FNV-1a hashes, member and namespace. The names are strings in
the executables: hashing every printable string of both games' main.dol, as is and in lower case, resolves the
common ones (for example 0xeacdfcfd in 0x266aa87a is 'parent' in 'abstractplacement', 0x4c2dfe93 in 0x8865fc57
'my' in 'optoplevelbehavior', 0x77074ba4 'null'). NUL-delimited strings are preferred over substrings when two
spellings collide.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import paths  # noqa: E402

_NAMES = None


def names():
    """{hash: name} from both games' main.dol."""
    global _NAMES
    if _NAMES is None:
        found = {}
        for root in (paths.SSA_ROOT, paths.GIANTS_ROOT):
            if not root:
                continue
            path = os.path.join(root, "sys", "main.dol")
            if not os.path.exists(path):
                continue
            data = open(path, "rb").read()
            for pattern, rank in ((rb"(?<=\x00)[\x20-\x7e]{2,80}(?=\x00)", 0), (rb"[\x20-\x7e]{2,80}", 1)):
                for m in re.finditer(pattern, data):
                    s = m.group().decode()
                    for v in (s, s.lower()):
                        h = iga.fnv1a(v.encode())
                        if h not in found or found[h][0] > rank:
                            found[h] = (rank, v)
        _NAMES = {h: v for h, (_, v) in found.items()}
    return _NAMES


def name(h):
    return names().get(h)


def import_name(member, namespace):
    """'member@namespace' when both hashes are known, else None."""
    a, b = name(member), name(namespace)
    return f"{a}@{b}" if a and b else None
