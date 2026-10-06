"""Fixes to Spyro's Adventure's own level scripts for converted Giants.

Push blocks (the big turtles and the other blocks a character can push): every level that has them carries the same
push-block script (an op list of 1415 ops; 29 levels on the disc). A minion of G:ScriptSet('Minions') close to the
block and facing it gets the push arrows; it pushes when its separation is under 0.8, it faces the block and the way
it would move, and "Minion - Locked State Start/End" locks it. The facing checks are three OpCheckFOV ops that look
only within 14 units of the minion (+0x38); a block is 15 wide and Tree Rex 14 (Spyro 4), so touching a block his
center is about 14.5 from its center and never in reach: the arrows appear but he cannot push (tests 21-29; the
test 29 trace shows the arrows spawned and the locked state never started). Giants' version of the script made that
reach a variable 'FOV check distance' set to 25 (and its separation limit 1); push_block_reach gives the three checks
a reach of 25. Spyro's Adventure's characters still need their separation under 0.8, so they push as before.

usage: python tools/level_fixes.py <level .bld> [...]   (reports what would change)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import script_edit  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402
from toy_table import Level  # noqa: E402

PUSH_REACH = (14, 25)  # Spyro's Adventure's reach, Giants' reach
FOV_VIEW = "FOV check View"  # the variable a push-block facing check takes its view angle from (+0x20)


def _literal_value(lv, field):
    """The value of a literal operand (a ValueRHSVariant or RHSValueStack without a path) at field, else None."""
    d = lv.doc
    if field not in lv.ptrs or not d.u32(field):
        return None
    o = lv.obj_at(d.u32(field))
    if o is None:
        return None
    s = lv.obj_at(d.u32(o + 0x08)) if lv.type(o) == "ValueRHSVariant" else o
    if s is None or lv.type(s) != "RHSValueStack" or d.u32(s + 0x08) or d.u32(s + 0x14):
        return None
    return d.u32(s + 0x20)


def _names_variable(lv, field, name):
    """Whether the operand at field is a one-element path naming the variable `name`."""
    d = lv.doc
    if field not in lv.ptrs or not d.u32(field):
        return False
    o = lv.obj_at(d.u32(field))
    if o is not None and lv.type(o) == "ValueRHSVariant":
        o = lv.obj_at(d.u32(o + 0x08))
    if o is None or lv.type(o) not in ("RHSValueStack", "RHSReferenceStack") or d.u32(o + 0x08) != 1:
        return False
    v = lv.obj_at(d.u32(d.u32(o + 0x14)))
    return v is not None and lv.name_of(v) == name


def push_block_reach(data: bytes):
    """Returns (bytes, what was done)."""
    doc = IgzDoc(data)
    if "OpCheckFOV" not in doc.types:
        return data, "no FOV checks"
    lv = Level.from_doc(doc)
    d = doc
    before = set(d.check())  # retail levels can fail the check already (Level_009_Minefield: 4 handles)
    t = d.type_index("OpCheckFOV")
    old, new = PUSH_REACH
    checks = [o for o in lv.objs if d.u32(o) == t and _literal_value(lv, o + 0x38) == old
              and _names_variable(lv, o + 0x20, FOV_VIEW)]
    if not checks:
        return data, "no push-block reach checks"
    # one private literal for all of them: retail files share identical literals far and wide
    reach = script_edit.Editor(lv).clone(lv.obj_at(d.u32(checks[0] + 0x38)))
    lv._index(d)
    stack = lv.obj_at(d.u32(reach + 0x08)) if lv.type(reach) == "ValueRHSVariant" else reach
    d.set_u32(stack + 0x20, new)
    for o in checks:
        d.set_u32(o + 0x38, reach)
    problems = [p for p in d.check() if p not in before]
    if problems:
        raise ValueError(f"push-block reach: {problems[:3]}")
    return d.to_bytes(), f"{len(checks)} push-block facing checks: reach {old} -> {new}"


def fix_level_archive(src, dst):
    """Apply the level fixes to the level entry of the archive src, written to dst (compressed like retail).
    Returns what was done."""
    a = iga.read(src)
    level = next((e for e in a.entries if e.name == "level.bld"), None) or max(a.entries, key=lambda e: len(e.data))
    level.data, done = push_block_reach(level.data)
    iga.write_v4(a.entries, dst, compress=True)
    return done


if __name__ == "__main__":
    for path in sys.argv[1:]:
        a = iga.read(path)
        level = max(a.entries, key=lambda e: len(e.data))
        _, done = push_block_reach(level.data)
        print(os.path.basename(path), done)
