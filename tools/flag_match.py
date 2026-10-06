"""Derive Giants bitfield <-> Spyro's Adventure flag-field mappings from objects present in both games.

Spyro (016_Spyro) exists on both discs. Objects of a changed type are paired across the games by a key that both
versions share (their name, or their float fields), then each Spyro's Adventure flag field is compared with each
bit of the Giants bitfield over all pairs. A bit that agrees on every pair (and varies) is the field's new home.

usage: python tools/flag_match.py TYPE
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
from toy_table import Level  # noqa: E402

# per type: how to pair instances, which Spyro's Adventure words are flag fields, and the Giants bitfield word
SPECS = {
    "tfbPhysicsAnimation": {"key": ("name", 0x08, 0x08), "ssa_flags": [0x28], "giants_bits": 0x20},
    "AnimationInfo": {"key": ("target_name", 0x40, 0x3c), "ssa_flags": [0x18, 0x34, 0x38], "giants_bits": 0x30},
    "GeneratorMovementFields": {"key": ("words", [0x20, 0x24, 0x28, 0x2c, 0x30, 0x38, 0x3c, 0x40, 0x44, 0x48, 0x4c, 0x50],
                                        [0x1c, 0x20, 0x24, 0x28, 0x2c, 0x30, 0x34, 0x38, 0x3c, 0x40, 0x44, 0x48]),
                                "ssa_flags": [0x18, 0x1c, 0x34, 0x54], "giants_bits": 0x18},
}
FILES = ["016_Spyro", "021_DrillBot", "004_Rock_Dragon", "008_FireDragon", "014_GillGrunt", "032_Cynder"]
GIANTS_FILES = ["016_Spyro", "021_DrillBot", "004_Rock_Dragon", "008_FireDragon", "014_GillGrunt", "032_Cynder"]


def key_of(lv, o, spec, game):
    d = lv.doc
    kind = spec["key"][0]
    if kind == "name":
        f = o + spec["key"][1 if game == "ssa" else 2]
        return d.cstr(d.u32(f)) if f in lv.strf else None
    if kind == "target_name":
        f = o + spec["key"][1 if game == "ssa" else 2]
        t = lv.obj_at(d.u32(f)) if f in lv.ptrs else None
        return d.cstr(d.u32(t + 8)) if t is not None and (t + 8) in lv.strf else None
    offs = spec["key"][1 if game == "ssa" else 2]
    return tuple(d.u32(o + k) for k in offs)


def instances(game, tname, spec):
    out = collections.defaultdict(list)
    for stem in (FILES if game == "ssa" else GIANTS_FILES):
        p = paths.ssa("character", stem + ".bld") if game == "ssa" else paths.giants("character", stem + ".bld")
        if not os.path.exists(p):
            continue
        lv = Level(p)
        d = lv.doc
        if tname not in d.types:
            continue
        t = d.type_index(tname)
        for o in lv.objs:
            if d.u32(o) == t:
                k = key_of(lv, o, spec, game)
                if k is not None:
                    out[(stem, k)].append((lv, o))
    return out


def main():
    tname = sys.argv[1]
    spec = SPECS[tname]
    ssa = instances("ssa", tname, spec)
    gia = instances("giants", tname, spec)
    pairs = [(ssa[k][0], gia[k][0]) for k in ssa if k in gia and len(ssa[k]) == 1 and len(gia[k]) == 1]
    print(f"{tname}: {len(pairs)} unambiguous pairs")
    for sf in spec["ssa_flags"]:
        for byte in range(4):
            shift = 24 - 8 * byte
            sv = [(lv.doc.u32(o + sf) >> shift) & 0xFF for (lv, o), _ in pairs]
            if len(set(sv)) < 2:
                continue
            gw = [glv.doc.u32(go + spec["giants_bits"]) for _, (glv, go) in pairs]
            # a bitfield value v stored at bit b with width w: try widths 1-3
            hits = []
            for w in (1, 2, 3):
                for b in range(0, 32 - w + 1):
                    gv = [(x >> b) & ((1 << w) - 1) for x in gw]
                    if gv == sv:
                        hits.append((b, w))
            print(f"  SSA +{sf:#04x} byte {byte} (values {sorted(set(sv))}): Giants bits {hits or 'no exact match'}")
    gw = [glv.doc.u32(go + spec["giants_bits"]) for _, (glv, go) in pairs]
    print("  Giants bitfield values:", collections.Counter(hex(x) for x in gw).most_common(8))


if __name__ == "__main__":
    main()
