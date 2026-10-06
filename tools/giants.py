"""The 8 Giants and the Spyro's Adventure edits that make their figures usable.

The table comes from the Giants disc (character/Init_Setup.bld toy table and permanent/global.bld with its
language packs; the names are the same in all six languages of both PAL discs); `verify()` re-derives it from the
discs. Per Giant, Spyro's Adventure gets:

  global.bld    two new StringInfo objects, a load name and a display name, with their strings appended to all
                6 language packs (the load name translates to the character file name), exported through the
                root list
  Init_Setup    a toy-table entry for the figure ID, cloned from Legendary Spyro's (which has its own name
                string), importing both names, with the Giant's element

Element numbers are the same in both games: 0 Magic, 1 Water, 2 Air, 3 Undead, 4 Tech, 5 Fire, 6 Earth, 7 Life.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import langpack  # noqa: E402
import minions  # noqa: E402
import paths  # noqa: E402
import script_edit  # noqa: E402
import script_fixes  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402

# figure ID, display name, element, load name, character file name
GIANTS = [
    (101, "Swarm", 2, "MinionLoad_101_BugmanGiant", "101_BugmanGiant"),
    (102, "Crusher", 6, "MinionLoad_102_EarthTitan", "102_Titan_Earth"),
    (104, "Hot Head", 5, "MinionLoad_104_OilBlazer", "104_OilBlazer"),
    (107, "Thumpback", 1, "MinionLoad_107_Whale", "107_Whale"),
    (109, "Ninjini", 0, "MinionLoad_109_Djini", "109_Djini"),
    (110, "Bouncer", 4, "MinionLoad_110_RobotGiant", "110_RobotGiant"),
    (112, "Tree Rex", 7, "MinionLoad_112_TitanLife", "112_TitanLife"),
    (114, "Eye-Brawl", 3, "MinionLoad_114_Mummy", "114_Mummy"),
]
TEMPLATE = 416  # Legendary Spyro's toy entry: names its own StringInfo instead of indexing Minion_Names by ID
GIANTS_EXPORT_BASE = 0x27  # Giants' global.bld: import index = root position + 0x27 (Spyro's Adventure: 0x29)
# Health categories: in both games every HP_Minion_* ValueInfo stores 1.0. Spyro's Adventure assigns the real
# numbers at start-up ("Minion - Tune Minions" in global.bld: VeryLow 200, Low 240, Medium 270, High 300,
# VeryHigh 340), and "Portal - Define Minion" takes the character's category as its level-1 maximum health. Giants
# has no such assignment for its Titan categories (it computes Titan health differently), so a copied Titan
# category would stay 1.0 (test 17: Tree Rex had 1 HP). The copies get Giants' level-1 health instead.
# Giants sets them in character/Init_Setup.bld (op list 6, its counterpart of "Minion - Tune Minions"), which also
# gives the other categories the same values as Spyro's Adventure.
TITAN_HEALTH = {"HP_Minion_Titan_Low": 400.0, "HP_Minion_Titan_Medium": 430.0, "HP_Minion_Titan_High": 460.0}


def add_names(archive, level, gdoc, giants=GIANTS):
    """Add each Giant's load and display name to Spyro's Adventure global.bld (level doc + packs, in place).
    Returns {figure ID: (load import index, name import index)}."""
    template = gdoc.u32(gdoc.u32(gdoc.u32(minions.find_set(gdoc, "Minion_Loads") + 0x18) + 0x14))
    before = len(minions.string_infos(gdoc))
    objs, strings = [], []
    for fid, name, _, load_name, file_name in giants:
        objs.append(minions.new_string_info(gdoc, load_name, template))
        objs.append(minions.new_string_info(gdoc, f"{fid:03d}_Toy_Name", template))
        strings += [file_name, name]
    if minions.string_infos(gdoc)[before:] != objs:
        raise ValueError("new StringInfo objects are not the last ones in address order")

    def append(lang, values):
        if len(values) != before:
            raise ValueError(f"{lang} pack has {len(values)} strings for {before} StringInfo objects")
        return values + strings
    langpack.edit_packs(archive.entries, append)
    indices = minions.export(gdoc, objs)
    return {g[0]: (indices[2 * k], indices[2 * k + 1]) for k, g in enumerate(giants)}


def add_entries(lv, exports, giants=GIANTS):
    """Add a toy-table entry per Giant to Init_Setup, importing the names added by add_names."""
    specs = []
    for fid, _, element, _, _ in giants:
        load_index, name_index = exports[fid]
        specs.append({"code": fid, "element": element,
                      "level_load": script_edit.add_import(lv, load_index, "global.bld"),
                      "name": script_edit.add_import(lv, name_index, "global.bld")})
    return script_edit.add_toy_entries(lv, TEMPLATE, specs)


def giants_texts(*parts):
    """{language: {StringInfo key: text}} of a .bld from both Giants discs (paths.giants_discs: three languages
    each, all six together)."""
    out = {}
    for path in paths.giants_discs(*parts):
        for lang, texts in langpack.texts(iga.read(path)).items():
            if lang in out:
                raise ValueError(f"{lang} pack found on both Giants discs")
            out[lang] = texts
    return out


def add_imported_globals(archive, gdoc, descs):
    """Copy objects a converted Giants character imports from Giants' global.bld but Spyro's Adventure's lacks.

    descs: [(type, name, ...)] as giant_imports.Global.describe gives them. ValueInfo (a tuning value): name,
    class and value copied; +0x1C holds a class number (script_fixes.script_classes), translated by class name.
    StringInfo: key copied, and each Spyro's Adventure pack gets the Giants string of its own language, looked up
    by key in the packs of the Giants disc that has that language (giants_texts). All are exported. Returns
    {(type, name): import index}."""
    import giant_imports
    from igzdoc import STRINGS_REF
    gg = giant_imports.Global(paths.giants("permanent", "global.bld"), GIANTS_EXPORT_BASE)
    texts = giants_texts("permanent", "global.bld")
    g_classes, s_classes = script_fixes.script_classes(gg.doc), script_fixes.script_classes(gdoc)
    t_value = gdoc.type_index("ValueInfo")
    before = len(minions.string_infos(gdoc))
    template = gdoc.u32(gdoc.u32(gdoc.u32(minions.find_set(gdoc, "Minion_Loads") + 0x18) + 0x14))
    new_objs, new_strings, keys = [], [], []
    for desc in dict.fromkeys(tuple(x[:2]) for x in descs):
        tname, name = desc
        g_index = gg.by_name[desc]
        src = gg.root[g_index - gg.base]
        if tname == "ValueInfo":
            words = [gg.doc.u32(src + k) for k in range(0, gg.doc.type_sizes[gg.doc.u32(src)], 4)]
            words[0] = t_value
            flag, cls = script_fixes.class_name(g_classes, words[7])
            words[7] = script_fixes.class_number(gdoc, s_classes, (flag, cls))
            if name in TITAN_HEALTH:
                if cls != "FloatMeasurement":
                    raise ValueError(f"{name}: expected a FloatMeasurement, found {cls}")
                words[8] = struct.unpack(">I", struct.pack(">f", TITAN_HEALTH[name]))[0]
            elif name.startswith("HP_Minion_Titan"):
                raise ValueError(f"{name}: no level-1 health known (TITAN_HEALTH)")
            obj = b"".join(struct.pack(">I", w) for w in words)
            enc = gdoc.add_object(minions.DEFAULT_SECTION, obj, align=4)
            gdoc.set_u32(enc + 8, gdoc.add_string(name))
            gdoc.add_fixup(STRINGS_REF, enc + 8)
            gdoc.add_fixup(0x10, enc + 0x1C)
        elif tname == "StringInfo":
            enc = minions.new_string_info(gdoc, name, template)
            new_strings.append({lang: by_key[name] for lang, by_key in texts.items()})
        else:
            raise ValueError(f"cannot copy {desc}")
        new_objs.append(enc)
        keys.append(desc)
    added = [o for o in minions.string_infos(gdoc)[before:]]
    if added != [o for o, k in zip(new_objs, keys) if k[0] == "StringInfo"]:
        raise ValueError("new StringInfo objects are not the last ones in address order")

    def append(lang, values):
        if lang not in texts:
            raise ValueError(f"no Giants disc has {lang} text")
        return values + [s[lang] for s in new_strings]
    if new_strings:
        langpack.edit_packs(archive.entries, append)
    indices = minions.export(gdoc, new_objs)
    return dict(zip(keys, indices))


def set_members(doc, name):
    lst = doc.u32(minions.find_set(doc, name) + 0x18)
    return [doc.u32(doc.u32(lst + 0x14) + 4 * k) for k in range(doc.u32(lst + 0x08))]


def add_to_character_list(gdoc, exports, giants=GIANTS):
    """Append each Giant's load name to Minion_Loads. Required: the portal refuses a toy whose load name is in
    neither Minion_Loads nor Item_Loads ("Portal Control - Portal - Logic - 235 - Condition - Toy Can't Be
    Used"), and logics 70/80/90 count Minion_Loads members as characters. Returns the Giants' list positions."""
    lst = gdoc.u32(minions.find_set(gdoc, "Minion_Loads") + 0x18)
    loads = [minions.exported(gdoc, exports[g[0]][0]) for g in giants]
    first = minions.append_to_list(gdoc, lst, loads)
    return {g[0]: first + k for k, g in enumerate(giants)}


def extend_collection_words(gdoc):
    """Point Collection_Minions words 2 and 3 at word 1 (Collection_Minions_2).

    "Save - Check Collection Info" keeps a normal character's owned bit at bit index = figure ID, and the bit
    field macros turn that into word ID / 32, bit ID % 32. Retail has 2 words (IDs 0-31, and the 5 Legendaries
    at bits 0-4 of word 1), so a Giant (IDs 101-114, word 3) would index past the end of the set. With words 2-3
    sharing word 1, the Giants use bits 5, 6, 8, 11, 13, 14, 16 and 18 of word 1: saved already, and unused
    by Spyro's Adventure. The save format does not change."""
    lst = gdoc.u32(minions.find_set(gdoc, "Collection_Minions") + 0x18)
    words = set_members(gdoc, "Collection_Minions")
    if len(words) != 2:
        raise ValueError(f"Collection_Minions has {len(words)} words, expected 2")
    minions.append_to_list(gdoc, lst, [words[1], words[1]])


def extend_parallel_set(doc, name, positions, picks):
    """A set indexed by Minion_Loads position (portraits, videos, sprites): pad it with copies of its first member
    up to the first Giant position, then add picks[k] for the Giant at positions[k]."""
    lst = doc.u32(minions.find_set(doc, name) + 0x18)
    members = set_members(doc, name)
    first = min(positions)
    if sorted(positions) != list(range(first, first + len(positions))) or len(members) > first:
        raise ValueError(f"{name}: {len(members)} members, Giant positions {positions}")
    pad = [members[0]] * (first - len(members))
    minions.append_to_list(doc, lst, pad + [members[p] for p in picks])
    return len(members), len(members) + len(pad) + len(picks)


def verify(giants=GIANTS):
    """Re-derive the table from the Giants disc; returns a list of mismatches (empty when it agrees)."""
    from toy_table import Level
    lv = Level(paths.giants("character", "Init_Setup.bld"))
    a = iga.read(paths.giants("permanent", "global.bld"))
    gd = IgzDoc(max(a.entries, key=lambda e: len(e.data)).data)
    packs = giants_texts("permanent", "global.bld")  # all six languages: add_names gives every pack the same text
    rec = lv.doc.record(2)
    global_hash = iga.fnv1a(b"global.bld")

    def target(handle_text):
        idx, fh = struct.unpack_from(">II", rec.body, 8 * (int(handle_text, 16) & 0x7FFFFFFF))
        if fh != global_hash:
            raise ValueError(f"{handle_text} imports from another file")
        return minions.exported(gd, idx, GIANTS_EXPORT_BASE)

    rows = {r["item code"][1]: r for r in lv.calls("Portal - Define Object Level Load")}
    problems = []
    for fid, name, element, load_name, file_name in giants:
        r = rows.get(fid)
        if r is None:
            problems.append(f"{fid}: not in the Giants toy table")
            continue
        load, nm, el = (target(r[k][1]) for k in ("level load", "name", "element"))
        got = {"load name": gd.cstr(gd.u32(load + 8)), "element": gd.u32(el + 0x20)}
        got.update({f"file ({lang})": v[gd.cstr(gd.u32(load + 8))] for lang, v in packs.items()})
        got.update({f"name ({lang})": v[gd.cstr(gd.u32(nm + 8))] for lang, v in packs.items()})
        want = {"load name": load_name, "element": element}
        want.update({f"file ({lang})": file_name for lang in packs})
        want.update({f"name ({lang})": name for lang in packs})
        problems += [f"{fid}: {k} is {got[k]!r}, table says {want[k]!r}" for k in want if got[k] != want[k]]
    return problems


if __name__ == "__main__":
    problems = verify()
    print("\n".join(problems) or f"table agrees with the Giants disc ({len(GIANTS)} Giants)")
