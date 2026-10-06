"""Dump a Havok packfile's __data__ section word by word with its fixups, for comparing class layouts.

usage: python tools/hk_dump.py ssa|giants CHARACTER_STEM ANIMATION_NAME_SUBSTRING
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hkpack  # noqa: E402
import paths  # noqa: E402
from toy_table import Level  # noqa: E402


def animation_packfiles(game, stem):
    """{animation name: packfile bytes} from a character's tfbPhysicsAnimation objects (+0x08 name, +0x14 size,
    +0x18 data)."""
    p = paths.ssa("character", stem + ".bld") if game == "ssa" else paths.giants("character", stem + ".bld")
    lv = Level(p)
    d = lv.doc
    out = {}
    t = d.type_index("tfbPhysicsAnimation")
    for o in lv.objs:
        if d.u32(o) == t:
            out[d.cstr(d.u32(o + 8))] = d.read(d.u32(o + 0x18), d.u32(o + 0x14) & 0xFFFFFF)
    return out


def dump(pf):
    s = pf.section("__data__")
    local = {src: dst for src, dst in s.local_fixups}
    glob = {src: (ds, dst) for src, ds, dst in s.global_fixups}
    objs = {off: cls for off, cls in pf.objects()}
    for off in range(0, len(s.data), 4):
        if off in objs:
            print(f"  ---- {objs[off]} @{off:#06x}")
        v = struct.unpack_from(">I", s.data, off)[0]
        note = ""
        if off in local:
            note = f"-> local {local[off]:#06x}"
        elif off in glob:
            note = f"-> global sec {glob[off][0]} {glob[off][1]:#06x}"
        f = struct.unpack(">f", struct.pack(">I", v))[0]
        fl = f" ({f:.5g})" if v and 1e-5 < abs(f) < 1e7 else ""
        print(f"  {off:#06x}: {v:08x}{fl} {note}")


if __name__ == "__main__":
    game, stem, sub = sys.argv[1:4]
    limit = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x140
    anims = animation_packfiles(game, stem)
    name = next(n for n in anims if sub in n)
    pf = hkpack.parse(anims[name])
    print(f"{game} {name}: packfile v{pf.version} {pf.contents_version}, data {len(pf.section('__data__').data):#x}")
    s = pf.section("__data__")
    keep = s.data
    s.data = keep[:limit] + b"".join([]) if limit else keep
    dump(pf)
