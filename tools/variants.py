"""The Giants' variant figures in Spyro's Adventure: Granite Crusher, Scarlet Ninjini, Legendary Bouncer and Gnarly
Tree Rex.

A variant figure carries its base Giant's figure ID; the variant word of its block 1 tells which variant it is.
Giants reads it from the tag header the engine fills for every toy ('save data header': 8 words, the figure's
blocks 0-1 as little-endian words). "Save - Get Tag Subtype Properties" (global.bld) takes word 7 bits 0-11 (the
variant's low 12 bits): bit 10 'is legendary', bits 0-7 the deco id. When bit 10 is set and (base load, deco id) is
in the table character/Init_Setup.bld builds with "Portal - Define Legendary Alt Level Load", "Portal - Load Portal
Object NEW" loads the character file of that table instead of the base one (MinionLoad_112_TitanLifeLegendary,
whose pack text is 112_TitanLife_Alt). Name, element, portrait and collection bit stay the base Giant's.

The variants' character files differ from the base ones in level.bld only (their .arc files are identical, see
verify()), so a variant gets its own converted .bld and the base Giant's converted .arc.

Spyro's Adventure's engine fills the same header for every toy (its "Portal - Load Portal Object NEW" reads the
figure ID that was taken from it), and its global.bld has the same bit-field macro, so the choice is made the same
way in Spyro's Adventure's terms:

  Init_Setup   hidden toy-table entries with item code figure ID + 1000 * (word 7 bits 0-10), the variant's load
               name, no name, and element 99, which no toy has, so the per-element loops of the collection screen
               and of the ownership check never reach them. Bits 8 and 9 do not matter to Giants (bit 9 is set on
               every Giant figure), so each variant gets the four codes they can make.
  global.bld   the variants' load names (StringInfo objects whose text is the file name in all 6 packs, exported),
               and in "Portal - Load Portal Object NEW", right after "Portal - Get Object Level Info" returned the
               toy's entry ('info'):
                   call "Save - Bit Field - Get Bit Field" (values in = loaded data inc . tag data . save data
                        header, set index 7, bit index 0, number of bits 11)
                       value out := value out * 1000
                       value out := value out + loaded data inc . tag . prodid
                       find the portal level loads whose item code == value out
                           info :=& the first of them
               After that the macro reads nothing from 'info' but 'info . level', the stream it loads.

Every op shape used is one the retail scripts use. They never put an operator inside another operator's operand,
never compare a found subset with an expression, and never call a macro inside a call of the same macro (return
parameters are objects shared by all calls), so none of that is done here.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_names  # noqa: E402
import giants  # noqa: E402
import iga  # noqa: E402
import langpack  # noqa: E402
import macro_dump as md  # noqa: E402
import minions  # noqa: E402
import paths  # noqa: E402
import script_edit  # noqa: E402
from igzdoc import IgzDoc, POINTERS  # noqa: E402
from macro_calls import used_macro  # noqa: E402
from toy_table import Level  # noqa: E402

# figure ID, variant, load name, character file name, base character file name, deco id
VARIANTS = [
    (102, "Granite Crusher", "MinionLoad_102_EarthTitanLegendary", "102_Titan_Earth_Alt", "102_Titan_Earth", 2),
    (109, "Scarlet Ninjini", "MinionLoad_109_DjiniLegendary", "109_Djini_Alt", "109_Djini", 2),
    (110, "Legendary Bouncer", "MinionLoad_110_RobotGiantLegendary", "110_RobotGiant_Legendary", "110_RobotGiant", 3),
    (112, "Gnarly Tree Rex", "MinionLoad_112_TitanLifeLegendary", "112_TitanLife_Alt", "112_TitanLife", 2),
]
LEGENDARY = 0x400  # word 7 bit 10
FREE_BITS = (0x000, 0x100, 0x200, 0x300)  # bits 8 and 9
HEADER_WORD, SUBTYPE_BITS, CODE_SCALE = 7, 11, 1000
HIDDEN_ELEMENT = 99
LOADER = "Portal - Load Portal Object NEW"
LOOKUP = "Portal - Get Object Level Info"
BIT_FIELD = "Save - Bit Field - Get Bit Field"
NULL = "null@abstractscriptgroup"


def codes(fid, deco):
    """The hidden toy-table item codes of a variant."""
    return [fid + CODE_SCALE * (LEGENDARY | bits | deco) for bits in FREE_BITS]


def verify(variants=VARIANTS):
    """Re-derive the table from the Giants disc; returns a list of mismatches (empty when it agrees)."""
    lv = Level(paths.giants("character", "Init_Setup.bld"))
    a = iga.read(paths.giants("permanent", "global.bld"))
    gd = IgzDoc(max(a.entries, key=lambda e: len(e.data)).data)
    pack = langpack.strings(IgzDoc(next(e for e in a.entries if e.name.endswith(".pak")).data))
    ordinal = {o: k for k, o in enumerate(minions.string_infos(gd))}
    ghash = iga.fnv1a(b"global.bld")
    table = {}
    for row in lv.calls("Portal - Define Legendary Alt Level Load"):
        handle = row.get("level load", (None, None))[1]
        if not (isinstance(handle, str) and handle.startswith("0x8")):
            continue
        idx, h = script_edit.import_of(lv, int(handle, 16))
        if h != ghash or idx < giants.GIANTS_EXPORT_BASE:
            continue
        o = minions.exported(gd, idx, giants.GIANTS_EXPORT_BASE)
        if o & 0x80000000 or gd.types[gd.u32(o)] != "StringInfo":
            continue
        table[gd.cstr(gd.u32(o + 8))] = (row.get("check against deco id", (None, None))[1], pack[ordinal[o]])
    problems = []
    for fid, name, key, stem, base, deco in variants:
        if table.get(key) != (deco, stem):
            problems.append(f"{name}: Giants' table has {table.get(key)} for {key}, expected {(deco, stem)}")
        if not any(g[0] == fid and g[4] == base for g in giants.GIANTS):
            problems.append(f"{name}: {base} is not Giant {fid}")
        for own, base_arc in zip(paths.giants_discs("character", stem + ".arc"),
                                 paths.giants_discs("character", base + ".arc")):
            if not (os.path.exists(own) and os.path.exists(own[:-4] + ".bld")):
                problems.append(f"{name}: {own[:-4]}.arc/.bld missing")
                continue
            with open(own, "rb") as f1, open(base_arc, "rb") as f2:
                if f1.read() != f2.read():
                    problems.append(f"{name}: {own} differs from {base_arc}")
    return problems


def add_load_names(archive, gdoc, variants=VARIANTS):
    """Add each variant's load name to Spyro's Adventure's global.bld (level doc + packs, in place): a StringInfo
    whose text is the character file name in every pack, exported. Returns {figure ID: import index}."""
    template = gdoc.u32(gdoc.u32(gdoc.u32(minions.find_set(gdoc, "Minion_Loads") + 0x18) + 0x14))
    before = len(minions.string_infos(gdoc))
    objs = [minions.new_string_info(gdoc, v[2], template) for v in variants]
    if minions.string_infos(gdoc)[before:] != objs:
        raise ValueError("new StringInfo objects are not the last ones in address order")

    def append(lang, values):
        if len(values) != before:
            raise ValueError(f"{lang} pack has {len(values)} strings for {before} StringInfo objects")
        return values + [v[3] for v in variants]
    langpack.edit_packs(archive.entries, append)
    return dict(zip((v[0] for v in variants), minions.export(gdoc, objs)))


def null_handle(lv):
    """The import handle of the engine's null object in a level."""
    rec = lv.doc.record(0x02)
    for k in range(rec.count):
        member, namespace = struct.unpack_from(">II", rec.body, 8 * k)
        if engine_names.import_name(member, namespace) == NULL:
            return 0x80000000 | k
    raise ValueError("no null import")


def add_entries(lv, exports, variants=VARIANTS):
    """Add the hidden toy-table entries to Init_Setup (cloned from giants.TEMPLATE like the Giants' own)."""
    null = null_handle(lv)
    specs = []
    for fid, _, _, _, _, deco in variants:
        load = script_edit.add_import(lv, exports[fid], "global.bld")
        specs += [{"code": c, "level_load": load, "name": null, "element": HIDDEN_ELEMENT} for c in codes(fid, deco)]
    lv._index(lv.doc)
    return script_edit.add_toy_entries(lv, giants.TEMPLATE, specs)


class _Builder:
    """New script objects copied from retail ones, with their fixups."""

    def __init__(self, lv):
        self.lv, self.d = lv, lv.doc

    def copy(self, obj):
        """A shallow copy of an object (pointers keep their targets)."""
        d = self.d
        size = d.type_sizes[d.u32(obj)]
        new = d.add_object(script_edit.DEFAULT, d.read(obj, size), align=8)
        d.copy_words(obj, new, size // 4)
        return new

    def elements(self, stack):
        """[(word, fixup tags)] of a value/reference stack's elements."""
        d = self.d
        n, buf = d.u32(stack + 0x08), d.u32(stack + 0x14)
        return [(d.u32(buf + 4 * k), d.tags_at(buf + 4 * k)) for k in range(n)]

    def stack(self, template, elements):
        """A copy of a non-empty stack holding `elements` ([(word, tags)]) in a buffer of its own. As in retail
        files, the buffer has one word more than the elements, and a non-empty stack's size word (+0x10) is not
        in fixup list 0x0F (only empty stacks' are)."""
        d = self.d
        if not d.u32(template + 0x14) or not elements:
            raise ValueError("stack templates and copies must have elements")
        new = self.copy(template)
        buf = d.append(script_edit.DEFAULT, b"".join(struct.pack(">I", w) for w, _ in elements) + bytes(4), align=8)
        for k, (_, tags) in enumerate(elements):
            for tag in tags:
                d.add_fixup(tag, buf + 4 * k)
        n = len(elements)
        d.set_u32(new + 0x08, n)
        d.set_u32(new + 0x0C, n)
        d.set_u32(new + 0x10, 0x80000000 | 4 * n)
        d.set_u32(new + 0x14, buf)
        return new

    def literal(self, template, value):
        """A copy of a literal RHSValueStack (no elements; +0x1C class, +0x20 value) holding value."""
        d = self.d
        if self.lv.type(template) != "RHSValueStack" or d.u32(template + 0x08) or d.u32(template + 0x14):
            raise ValueError("not a literal")
        new = self.copy(template)
        d.set_u32(new + 0x20, value)
        return new

    def literal_param(self, param, value):
        """A copy of a parameter op whose value is a plain literal, passing value. +0x18 bit 31 is set on the
        arguments a retail call leaves at the default (and on a definition's own parameters), clear on those it
        passes."""
        d = self.d
        variant = self.copy(_literal_variant(self.lv, param))
        d.set_u32(variant + 0x08, self.literal(self.lv.obj_at(d.u32(variant + 0x08)), value))
        new = self.copy(param)
        d.set_u32(new + 0x30, variant)
        d.set_u32(new + 0x18, d.u32(new + 0x18) & 0x7FFFFFFF)
        return new


def _literal_variant(lv, param):
    """The ValueRHSVariant of a parameter whose value is a plain literal, else None."""
    d = lv.doc
    v = lv.obj_at(d.u32(param + 0x30)) if param + 0x30 in lv.ptrs else None
    if v is None or lv.type(v) != "ValueRHSVariant" or d.u32(v + 0x0C) != 0xFFFFFFFF:
        return None
    s = lv.obj_at(d.u32(v + 0x08))
    if s is None or lv.type(s) != "RHSValueStack" or d.u32(s + 0x08) or d.u32(s + 0x14):
        return None
    return v


def _members(lv, struct_op):
    """{name: OpCreateVariable} of a structure, from the ops following its definition."""
    d = lv.doc
    for _, ops in md.op_lists(lv):
        if struct_op in ops:
            i = ops.index(struct_op)
            return {d.cstr(d.u32(op + 0x1C)): op for op in ops[i + 1:i + 1 + (d.u32(struct_op + 0x18) & 0xFFFF)]
                    if lv.type(op) == "OpCreateVariable"}
    raise ValueError(f"structure {lv.name_of(struct_op)!r} not in any op list")


def _calls(lv, ops, i):
    """Name of the macro the op at ops[i] calls, or None."""
    if lv.type(ops[i]) != "OpUseMacro":
        return None
    try:
        return used_macro(lv, ops[i])
    except Exception:
        return None


def _params(lv, ops, i):
    """{name: parameter op} of the call at ops[i] (use macro, interface, parameters, flow macro)."""
    d = lv.doc
    n = (d.u32(ops[i + 1] + 0x18) & 0xFFFF) - 1
    return {d.cstr(d.u32(op + 0x1C)): op for op in ops[i + 2:i + 2 + n]}


def patch_loader(lv):
    """Make "Portal - Load Portal Object NEW" load the variant's character file (see the module docstring).
    lv: Level of Spyro's Adventure's global.bld (indexed after the other edits). Returns a description."""
    d = lv.doc
    b = _Builder(lv)
    lists = list(md.op_lists(lv))
    where = [(code_list, ops, i) for code_list, ops in lists for i, op in enumerate(ops)
             if lv.type(op) == "OpDefineMacro" and lv.name_of(op) == LOADER]
    if len(where) != 1:
        raise ValueError(f"{LOADER!r} defined {len(where)} times")
    code_list, ops, i0 = where[0]
    end = i0 + (d.u32(ops[i0] + 0x18) & 0xFFFF)
    call = next(i for i in range(i0, end) if lv.type(ops[i]) == "OpUseMacro")
    if _calls(lv, ops, call) != LOOKUP:
        raise ValueError(f"{LOADER!r} does not start with a call of {LOOKUP!r}")
    args = _params(lv, ops, call)
    if list(args) != ["prodid", "level load", "is item", "is location", "is pet", "info"] \
            or lv.type(ops[call + 8]) != "OpFlowMacro" or lv.type(ops[call + 9]) != "OpCheckMembership" \
            or call + (d.u32(ops[call] + 0x18) & 0xFFFF) != end - 1:  # the call's block runs to the macro's end
        raise ValueError(f"unexpected layout of {LOADER!r}")
    prodid_value = lv.obj_at(d.u32(args["prodid"] + 0x30))
    prodid_path = lv.obj_at(d.u32(prodid_value + 0x08))
    path = [lv.obj_at(w) for w, _ in b.elements(prodid_path)]
    if lv.type(prodid_value) != "ValueRHSVariant" or d.u32(prodid_value + 0x0C) != 0xFFFFFFFF \
            or [lv.type(o) for o in path] != ["OpMacroParameter", "OpCreateVariable", "OpCreateVariable"] \
            or d.cstr(d.u32(path[0] + 0x1C)) != "loaded data inc":
        raise ValueError("prodid is not 'loaded data inc . tag . prodid'")
    loaded_inc, info = path[0], args["info"]
    tag_data = _members(lv, lv.obj_at(d.u32(loaded_inc + 0x24)))["tag data"]
    header = _members(lv, lv.obj_at(d.u32(tag_data + 0x24)))["save data header"]

    # templates, all from retail ops of this file
    bit_calls = [(ops2, i) for _, ops2 in lists for i in range(len(ops2)) if _calls(lv, ops2, i) == BIT_FIELD]
    lit_call = next((o2, i) for o2, i in bit_calls if all(
        _literal_variant(lv, _params(lv, o2, i)[n]) for n in ("set index", "bit index", "number of bits")))

    def set_path(param):
        """Whether a 'values in' argument is a path from a parameter to a set member, like the new one."""
        s = lv.obj_at(d.u32(param + 0x30))
        if lv.type(s) != "RHSReferenceStack" or not d.u32(s + 0x14):
            return False
        objs = [lv.obj_at(w) if POINTERS in tags else None for w, tags in b.elements(s)]
        return None not in objs and lv.type(objs[0]) == "OpMacroParameter" and \
            lv.type(objs[-1]) == "OpCreateVariable" and d.u32(objs[-1] + 0x20) == d.u32(header + 0x20)
    values_in_tpl = next(p for p in (_params(lv, o2, i)["values in"] for o2, i in bit_calls) if set_path(p))
    lops, li = lit_call
    lit = _params(lv, lops, li)
    closing = lops[li + (d.u32(lops[li] + 0x18) & 0xFFFF)]
    set_tpl = next(op for op in ops[i0:end] if lv.type(op) == "OpSetValue" and d.u32(
        lv.obj_at(d.u32(op + 0x20)) + 0x0C) != 0xFFFFFFFF and lv.type(lv.obj_at(d.u32(op + 0x1C))) == "ValueStack")
    expr_tpl = lv.obj_at(d.u32(set_tpl + 0x20))
    sides = [lv.obj_at(d.u32(expr_tpl + off)) for off in (0x08, 0x10)]
    lit_stack = next(s for s in sides if not d.u32(s + 0x08) and not d.u32(s + 0x14))
    find_tpl, take_tpl = None, None
    for o in lv.objs:
        t = lv.type(o)
        if t == "OpFindSubSet" and find_tpl is None and d.u32(o + 0x20) == 1:
            els = b.elements(lv.obj_at(d.u32(o + 0x1C)))
            names = [d.cstr(d.u32(lv.obj_at(w) + 0x1C)) if POINTERS in tags and lv.obj_at(w) is not None
                     and lv.type(lv.obj_at(w)) == "OpCreateVariable" else None for w, tags in els]
            cmp_value = lv.obj_at(d.u32(o + 0x24))
            if names[-1:] == ["item code"] and "portal level loads" in names and lv.type(cmp_value) == \
                    "ValueRHSVariant" and d.u32(cmp_value + 0x0C) == 0xFFFFFFFF:
                find_tpl = o
        elif t == "OpSetReference" and take_tpl is None and not d.u32(o + 0x24):
            target = b.elements(lv.obj_at(d.u32(o + 0x1C)))
            source = lv.obj_at(d.u32(o + 0x20))
            els = b.elements(source) if d.u32(source + 0x14) else []
            if target == [(info, [POINTERS])] and len(els) == 2 and lv.type(lv.obj_at(els[0][0])) == \
                    "OpFindSubSet" and 0x07 in els[1][1]:
                take_tpl = o
    if find_tpl is None or take_tpl is None:
        raise ValueError("no template for the toy-table search")
    take_source = lv.obj_at(d.u32(take_tpl + 0x20))
    first = b.elements(take_source)[1]
    idx, h = script_edit.import_of(lv, first[0])
    if engine_names.import_name(idx, h) != "first@setvariant":
        raise ValueError("the search template does not take the first element")

    # the new objects
    value_out = lit["value out"]
    use = b.copy(lops[li])
    d.set_u32(use + 0x18, 0x10000 | 13)
    values_in = b.copy(values_in_tpl)
    d.set_u32(values_in + 0x18, d.u32(values_in + 0x18) & 0x7FFFFFFF)
    d.set_u32(values_in + 0x30, b.stack(lv.obj_at(d.u32(values_in_tpl + 0x30)),
                                        [(loaded_inc, [POINTERS]), (tag_data, [POINTERS]), (header, [POINTERS])]))
    new_params = [values_in, b.literal_param(lit["set index"], HEADER_WORD), b.literal_param(lit["bit index"], 0),
                  b.literal_param(lit["number of bits"], SUBTYPE_BITS), lit["signed"], value_out]

    def value_out_stack():
        return b.stack(prodid_path, [(value_out, [POINTERS])])

    def assignment(op, right):
        s = b.copy(set_tpl)
        d.set_u32(s + 0x1C, b.stack(lv.obj_at(d.u32(set_tpl + 0x1C)), [(value_out, [POINTERS])]))
        e = b.copy(expr_tpl)
        d.set_u32(e + 0x08, value_out_stack())
        d.set_u32(e + 0x0C, op)
        d.set_u32(e + 0x10, right)
        d.set_u32(s + 0x20, e)
        return s
    scale = assignment(2, b.literal(lit_stack, CODE_SCALE))
    add = assignment(0, b.stack(prodid_path, b.elements(prodid_path)))
    find = b.copy(find_tpl)
    d.set_u32(find + 0x18, 0x10000 | 1)
    compared = b.copy(lv.obj_at(d.u32(find_tpl + 0x24)))
    d.set_u32(compared + 0x08, value_out_stack())
    d.set_u32(find + 0x24, compared)
    take = b.copy(take_tpl)
    d.set_u32(take + 0x20, b.stack(take_source, [(find, [POINTERS]), first]))
    new_ops = [use, lops[li + 1]] + new_params + [lops[li + 8], scale, add, find, take, closing]
    if [lv.type(op) for op in new_ops[1:2] + new_ops[8:9] + new_ops[-1:]] != \
            ["OpMacroInterface", "OpFlowMacro", "OpFlowBuiltInBehavior"]:
        raise ValueError("unexpected call template layout")

    # insert them after the lookup's parameters, as siblings in its block
    others = {op for lst, o2 in lists if lst != code_list for op in o2}
    grown = script_edit.Editor(lv).insert_ops(call + 9, new_ops, sibling_start=call + 1, code_list=code_list)
    shared = [g for g in grown if ops[g[0]] in others]
    if shared:
        raise ValueError(f"grown ops also used by other op lists: {shared}")
    lv._index(d)
    return {"ops": len(new_ops), "at": call + 9, "grown": [f"{t} {a}->{c}" for _, t, a, c in grown]}
