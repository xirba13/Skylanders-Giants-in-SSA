"""Build the Riivolution test patches for Dolphin and verify them offline.

  test1   Spyro's own files, repacked by our IGA writer (passed 2026-10-02)
  test7   misc/Init_Setup.bld with Spyro's entry in the supported-toy table changed from figure ID 16 to 112
          (passed: Tree Rex loads Spyro, Spyro is refused)
  test8   misc/Init_Setup.bld with a NEW entry for ID 112, cloned from Legendary Spyro's (416); Spyro's entry kept
          (passed: Tree Rex loads Legendary Spyro with a proper name and 0 coins; Spyro still works)
  test9   the debug toy's load name translated to "112_TitanLife" in global.bld's language packs, a new ID 112
          entry using it, and character/112_TitanLife.* (copies of Spyro's): does the translation pick the file?
  test12  all 8 Giants (tools/giants.py: IDs, names, elements, file names from the Giants disc): names and toy
          entries, Minion_Loads membership, save collection bits, portrait/video/sprite sets; each Giant played
          by a Spyro's Adventure character of the same element copied under the Giant's file name
          (tests 10 and 11, without the Minion_Loads membership, were refused by the portal)
  test13  test 12, but Tree Rex uses his own data converted from the Giants disc (tools/convert_character.py)
          (result: stuck on the loading screen; converted Tree Rex exceeds the character memory budget)
  test14a test 13 files + character memory pool B raised 0x100000 -> 0x180000 (Riivolution memory patch)
  test14b test 13 files + pools A 0xC0000 -> 0x140000 and B 0x100000 -> 0x180000
          (14a and 14b: Tree Rex loads, then the game stops as he appears)
  test15  diagnosis: test 13 with every Tree Rex sound replaced by one known-good Spyro's Adventure sound, pool B
          patch as 14a (result: same stop; the debugger showed a null read in skinning code, igBlendMatrixSelect)
  test16  test 13 with the igBlendMatrixSelect and material-flag fixes, pool B patch; 16s: with substituted sounds
          (result: Tree Rex plays and talks, but is drawn huge and torn; B attack freezes the game for a while)
  test17  Tree Rex with the fixes found by comparing converted shared characters with Spyro's Adventure's own
          files (tools/converted_diff.py): vertex pack data, particle generators, material flags, ability
          pictures and the life-bar head; pool B patch
          (result: right size and animations in menus, no freeze; in game only the arm spikes show, 1 HP)
  test18  test 17 with the lip-sync mouth poses (tfbPhysicsBody _visemeSet) left out, Titan health 430 at
          level 1, the life-bar head at 64x64; pool B patch
          (result: still invisible in game, life-bar picture unchanged, 430 HP in game at any level)
  test19  test 18 with 'Starting Scale XYZ' set in Tree Rex's start-up script (tools/script_fixes.py: Giants sets
          it in a global macro Spyro's Adventure's version lacks, so he was spawned at scale 0) and the life-bar
          head texture scaled to 80x80; pool B patch
          (result: crash as Tree Rex appears in game; Dolphin's log, with OSReport mapped through a symbol map,
          showed the script interpreter reading the name of a destroyed script object)
  test20  test 19 with the start-up script op inserted in place (the op array keeps its position, directly followed
          by its first op as in every retail file; four identical ops keep the 16-byte alignment); pool B patch
          (result: the same crash. Cause: object reference counts (tools/refcounts.py). The new op shares the path
          objects of Tree Rex's 'scale' reference without counting itself; resolving the path released the shared
          'Starting Scale XYZ' stub to 0, destroying it under the other path)
  test21  test 20 with every written file's reference counts recomputed from its pointers (IgzDoc.to_bytes); this
          also fixes the toy-table ops shared by the new Init_Setup entries and the shared UI and global.bld list
          entries, which had the same kind of deficit; pool B patch
          (result: Tree Rex plays, whole body, right size; moves during dialogues, cannot push turtles, the B charge
          neither speeds up nor hurts, Z fires nothing, 430 HP at level 6)
  test22  test 21 with the stubs of the five macros Giants renamed given Spyro's Adventure's names (projectiles:
          "Projectile - Fire Projectile" is "Combat - Fire Projectile", same IDs) and his controller-off calls
          redirected to "Minion - Set Controller to Inactive" (tools/script_fixes.py); pool B patch
          (result: held still in dialogues and cutscenes; Z still fires nothing)
  test23  test 22 with the two renamed structures' stubs renamed too: his projectile description's type
          "Projectile - Projectile Description" is Spyro's Adventure's "Combat - Projectile Description"; pool B patch
          (result: Z fires, but the lasers stay where they are fired from; no sound)
  test24  test 23 with Giants-style projectiles for callers that do not pick a style (a global.bld change, since
          removed: logic sets, and Fire's registering path); pool B patch
          (result: Tree Rex's lasers still stay where they are fired; and every Spyro's Adventure projectile now stays
          too, in test 12 as well: the change wrote comparison code 5, which is <=, for >=)
  test25  test 23 again with today's tools (no global.bld projectile change); pool B patch
  test26  test 25 with Giants-style projectiles for callers that do not pick a style (a global.bld change, since
          removed: logic sets, Fire's registering path, no removal right after firing)
          (result: Spyro's and Tree Rex's projectiles stay where they are fired: the ">=" was code 3, not 2)
  test27  test 25 with Tree Rex's Fire call passing his laser description's speed instead of -1
          (a script fix since removed: -1 was not the problem); no global.bld projectile change; pool B patch
          (result: Spyro's fireballs fly; Tree Rex's lasers still stay where they are fired, no sound)
  test27t test 27's files with the script trace patches (tools/script_trace.py)
          (result: only spawn ops reach the hooked call sites; "Combat - Fire Projectile" spawns from its style-1
          branch for Spyro's fireballs and from its style-0 branch for Tree Rex's lasers)
  test28  test 25 with every Spyro's Adventure parameter a converted call leaves out and whose default is not 0
          passed with its default (script_fixes.fill_omitted_parameters): Tree Rex's "Combat - Define Projectile"
          call gets 'is new-style projectile' = 1; pool B patch
          (result: the Z lasers fly and hit; a big sphere shows with them; no laser sound; B charge and turtles
          unchanged)
  test29  test 28 with Giants' "Movement - Displace Velocity" and an empty "Minion - Combat - Query to Add Enemy
          to Already Hurt Handler" as local macros of Tree Rex's script (tools/macro_port.py), and his "Sound -
          Ultra Sound" / "Sound - VO Request" calls redirected to "Sound - Play From Set" / "Sound - Play Sound"
          (script_fixes.redirect_calls); pool B patch
          (result: sounds work; the charge hurts but runs away, faster and faster; still no turtle pushing)
  test29t test 29's files with the script trace (tools/script_trace.py): spawns land in Dolphin's log, which shows
          how far the turtle push blocks get with Tree Rex (push arrow, locked state, slide)
          (result: the push arrows spawn, the locked state never starts)
  test30  test 29 with the charge's displacement setting his horizontal velocity instead of adding to it
          (macro_port.PORTS), his laser's launch particle left out (script_fixes.drop_post_processed_launch_particles,
          an experiment: is it the yellow sphere?) and Level_021_Sheep's push blocks given Giants' reach of 25
          (tools/level_fixes.py); pool B patch
          (result: the charge runs at Giants' speed and steers, no sphere on the lasers, turtles push in Sheep)
  test30t test 30's files with the script trace (not run)
  test31  test 30 with Giants' "Sound - Stop Loop" as a local macro (tools/macro_port.py; the loops of his wing beats
          and charge stop), his laser's muzzle flash back and attached to him after each shot
          (script_fixes.attach_launch_particles), and the push-block reach in all 29 levels that have push blocks
          (shared folder levels/, cached in build/level_cache); pool B patch
          (result: loops stop, turtles push in other levels; the muzzle flash shows as the yellow sphere over his
          hand)
  test32  test 31 with the muzzle flash left out again (script_fixes.drop_post_processed_launch_particles)
          (result: everything works)
  test33  all 8 Giants converted from their own data with the same tools: Titan health for every category
          (giants.TITAN_HEALTH from Giants' Init_Setup), controller calls that turn the controller back on
          (Eye-Brawl, Crusher, Thumpback), arguments rebound by name (homing logic of Ninjini and Bouncer); pool B
          patch
  test34  test 33 plus the 4 variant figures (tools/variants.py): Granite Crusher, Scarlet Ninjini, Legendary
          Bouncer and Gnarly Tree Rex load their own converted .bld (with the base Giant's .arc), chosen like
          Giants does from the figure's variant word, through hidden toy-table entries; pool B patch
          (result: the variants appear; their life-bar portraits are too big)
  test35  test 34 with the variants' life-bar portraits shrunk like the Giants' (their head sprites are named
          "112_MinionHead_Alt", "110_MinionHead_Legendary": convert_character.HEAD_SPRITE)
          (result: the variants show up correctly; Bouncer's B attack crashes the game)
  test36  test 35 with Bouncer's write to the rumble's 'attenuates', a member Spyro's Adventure's engine lacks,
          replaced by an empty jump (script_fixes.drop_missing_member_writes)
          (result: no crash; Swarm's charged A crashes, some upgrade pictures missing, steering problems)
  test37  test 36 with: Giants' transform UV animations converted (Swarm's charged A crashed on an unknown class)
          and scroll wobbles kept (convert.py); ability pictures as Spyro's Adventure's colour image and alpha mask
          (convert_character.widen_picture); Giants' "Movement - Get Controller Reference", "Simple Safe
          Movement", "Turn To" and "Set Velocity" as local macros (macro_port.py: Bouncer's rocket target,
          Crusher's turns)
          (result: Crusher crashes the game as he loads: the "Turn To" copy wrote class numbers past the end of
          his named references, as the tools read class numbers off record 1 instead of record 3; still missing
          pictures and Swarm's portal voice)
  test38  test 37 with class numbers translated through each file's named references (record 3,
          script_fixes.script_classes) in the macro ports, the parameters filled in and the copied tuning values
          (Crusher, Thumpback and Eye-Brawl had numbers out of range, Bouncer one wrong class), and archives
          written with the hash-search window retail uses (iga.search_window: six Giants' .arc had 3 to 83
          entries the engine could not find, among them the missing pictures and voice lines); "Movement - Get
          Velocity" defined empty, its returned members read from the actor's velocity directly
          (script_fixes.read_velocity_directly: the Giants-only call skipped its block, Hot Head's A fire)
          (result: Crusher loads, his Z works; all pictures and voices; Hot Head's fire leaves his hand; left:
          Crusher's B gaze cannot be steered, Bouncer's B lands far off, Hot Head's flame looks dim and brownish)
  test39  test 38 with Bouncer's rocket aim given its rocket's gravity (script_fixes.literal_definition_physics: the
          ballistics read it off the actor definition, which Spyro's Adventure's engine does not answer) and
          Giants' self-illuminated materials (basic flags bit 18) made unlit (convert.py: Hot Head's flame)
          (result: the effects look good enough; Bouncer's rockets fall even farther and take long to come down)
  test39t test 39's files with the script trace (tools/script_trace.py, every spawn in Dolphin's log): which of
          Crusher's B gaze steering branches run when the stick moves
          (result, tools/trace_map.py: the steering runs, but both stick directions take the same branch, as if the
          gaze sequence's position read back as NaN)
  test40  test 39 with Bouncer's rockets launched straight down from their launch point 75 ft above the target
          (script_fixes.drop_rockets_from_above) and Crusher's gaze sequence started at rate 1 instead of 0.001
          (script_fixes.whole_playback_rates: Spyro's Adventure's rates are whole numbers)
          (result: everything works)
  test40t test 40's files with the script trace, to see the gaze steering branches again
  test41  test 40 in all six languages: each Spyro's Adventure language pack of the Giants' character files and
          of their global.bld strings is the Giants pack of the same language (Spanish, German and Italian from the
          DE/ES/IT disc, English, French and Dutch from the EN/FR/NL disc; until test 40 every pack was the Spanish
          one), and each Giant's .arc holds both discs' voice lines

Tests 13-40 are no longer built: the converter has changed since, so rebuilding them would not reproduce what
was tested. Their results are in docs/TESTS.md.

Tests 4a-6 (global.bld rebuilds and the Minion_Loads experiment) are recorded in docs/TESTS.md.

usage: python tools/build_tests.py [--install] [--install-tests] [--sd ROOT] [--no-build]

  --install and --sd install the patch for playing: RELEASE_TEST, shown in Riivolution as "Skylanders Giants port"
  > "Giants" (riivolution/GiantsPort.xml, files in giants-port/ laid out like the disc). --install-tests installs
  every test above into Dolphin instead (riivolution/GiantsPortTests.xml, files in giants-port-tests/).
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert_character  # noqa: E402
import giants  # noqa: E402
import iga  # noqa: E402
import langpack  # noqa: E402
import level_fixes  # noqa: E402
import minions  # noqa: E402
import paths  # noqa: E402
import refcounts  # noqa: E402
import script_edit  # noqa: E402
import toys  # noqa: E402
import variants  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402
from toy_table import Level  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "build", "riivolution")
PATCH = "giants-port-tests"  # the test patches' folder under a Riivolution root (Dolphin's Load/Riivolution)
XML = "GiantsPortTests.xml"
# The patch for playing (--install into Dolphin, --sd onto a Wii's SD card): the newest Giants test under a proper
# name, its files in a folder laid out like the disc (giants-port/character/, level/, misc/, permanent/).
RELEASE_TEST = "test41"
RELEASE_XML = "GiantsPort.xml"
RELEASE_FOLDER = "giants-port"
RELEASE_MENU = ("Skylanders Giants port", "Giants", "Enabled")  # Riivolution section, option and choice
NEW_ENTRY = "MinionLoad_112_TitanLife"
NEW_FILE = "112_TitanLife"  # its pack string: the character/ file name
DEBUG_INDEX = 0x776  # global.bld import index of MinionLoad_099_DebugMinion, used only by toy entry 999
# test 11 stand-ins: a Spyro's Adventure character of the same element plays each Giant until the converter exists
PARALLEL_SETS = {  # misc/ sets indexed by Minion_Loads position (found by tracing the scripts, see FORMATS.md)
    "UI_Collection_Champions.bld": ["Collection_MinionIcons"],
    "UI_HeroicChallengeSelect.bld": ["Collection_MinionIcons"],
    "UpgradeUI.bld": ["Collection_MinionIcons"],
    "PvP_MainControl.bld": ["RightFacing_MinionSprites"],
}
STAND_INS = {2: "003_StormGiant", 6: "007_GemGolem", 5: "009_Eruptor", 1: "015_Yeti", 0: "018_Wizard",
             4: "021_DrillBot", 7: "027_Ent", 3: "031_GhostEater"}

TESTS = {
    "test1": "Test 1: Spyro repacked by our writer",
    "test7": "Test 7: toy table - Spyro's entry answers to ID 112",
    "test8": "Test 8: toy table - new ID 112 entry (copy of Legendary Spyro)",
    "test9": "Test 9: ID 112 entry, debug load name translated to 112_TitanLife",
    "test12": "Test 12: all 8 Giants, stand-in characters",
    "test41": "Test 41: all 8 Giants and the 4 variants, all languages",
}
# per-category memory budgets in main.dol (table at 0x8054208C, rows of 0x3C: name, four pool sizes, counts,
# slots). The character row: pool A at 0x80542108 (0xC0000), pool B at 0x8054210C (0x100000). The engine puts an
# IGZ section of pool "Default" into budget pool A and every other pool (String, Image, Vertex, VertexObject,
# AnimationData, Audio, ...) into pool B (table 0x804229C0 of pool names and budget pool index, read by
# fn_804D0D08). Every converted Giant fits A unchanged and B raised to 0x180000 (Hot Head is the largest, 1,485,390
# bytes; see docs/FORMATS.md).
CHARACTER_POOL_A, CHARACTER_POOL_B = 0x80542108, 0x8054210C


def same_entries(a_path, b_path):
    a = {(e.name, e.hash): e.data for e in iga.read(a_path).entries}
    b = {(e.name, e.hash): e.data for e in iga.read(b_path).entries}
    return a.keys() == b.keys() and all(a[k] == b[k] for k in a)


def rebuild_global(dst, compress, add=()):
    """global.bld with its level data passed through the IGZ editor (optionally adding list entries)."""
    a = iga.read(paths.ssa("permanent", "global.bld"))
    level = max(a.entries, key=lambda e: len(e.data))
    doc = IgzDoc(level.data)
    if add:
        minions.add_entries(doc, "Minion_Loads", add)
    data = doc.to_bytes()
    if not add and data != level.data:
        raise SystemExit("global level data did not round-trip")
    level.data = data
    iga.write_v4(a.entries, dst, compress=compress)
    back = iga.read(dst)
    got = max(back.entries, key=lambda e: len(e.data)).data
    if got != data:
        raise SystemExit(f"{dst}: level data does not read back")
    return {"size": os.path.getsize(dst), "retail_size": os.path.getsize(paths.ssa("permanent", "global.bld")),
            "minion_loads": len(minions.entries(IgzDoc(got), "Minion_Loads"))}


def build(report):
    # test 1: Spyro's archives through the writer
    out = os.path.join(OUT, PATCH, "test1")
    os.makedirs(out)
    for ext in (".arc", ".bld"):
        src = paths.ssa("character", "016_Spyro" + ext)
        dst = os.path.join(out, "016_Spyro" + ext)
        iga.write_v4(iga.read(src).entries, dst)
        if not same_entries(src, dst):
            raise SystemExit(f"test1: {dst} does not read back identical")
    report["test1"] = "built"

    # test 7: the supported-toy table in Init_Setup.bld, Spyro's entry moved from figure ID 16 to 112
    report["test7"] = write_init_setup("test7", lambda lv: toys.set_item_code(lv, 16, 112), want={112}, absent={16})

    # test 8: a new ID 112 entry cloned from Legendary Spyro's (416), Spyro's own entry untouched
    report["test8"] = write_init_setup("test8", lambda lv: script_edit.add_toy_entry(lv, 416, 112),
                                       want={112, 16, 416}, absent=set())

    # test 9: the debug toy's load name (MinionLoad_099_DebugMinion, used only by toy entry 999) translated to
    # "112_TitanLife" in every language pack, and a new ID 112 entry that uses that load name. Nothing is added to
    # global.bld's objects. Shows whether the translated load name is the file the game opens.
    # (The first test 9 added a StringInfo without pack strings and exported it; the game hung after global.bld.)
    a, level, gdoc = global_archive()
    debug = minions.string_infos(gdoc).index(minions.exported(gdoc, DEBUG_INDEX))

    def repoint(lang, values):
        if values[debug] != "099_Debug_Minion":
            raise SystemExit(f"test9: {lang} pack string {debug} is {values[debug]!r}")
        values[debug] = NEW_FILE
        return values
    langpack.edit_packs(a.entries, repoint)
    report["test9"] = write_global("test9", a, level, gdoc, {debug: NEW_FILE})

    def edit9(lv):
        handle = script_edit.entry_handles(lv, 999)["level load"]
        if script_edit.import_of(lv, handle) != (DEBUG_INDEX, iga.fnv1a(b"global.bld")):
            raise SystemExit("test9: entry 999 does not use the debug load name")
        script_edit.add_toy_entry(lv, 416, 112, level_load=handle)
    report["test9"]["init_setup"] = write_init_setup("test9", edit9, want={112, 16, 416}, absent=set())
    copy_spyro_as("test9", NEW_FILE)

    # test 12: all 8 Giants (tools/giants.py), with what the scripts need besides the toy-table entry:
    #   global.bld   the load and display names (with pack strings), exported; the load names added to
    #                Minion_Loads (the portal refuses toys whose load name is not in it); Collection_Minions words
    #                2-3 pointed at word 1 so the Giants' owned bits stay inside the saved data; ChampionIntroVideos
    #                extended to the Giants' Minion_Loads positions
    #   misc/        portrait and sprite sets indexed by Minion_Loads position extended the same way
    # Each Giant is played by a Spyro's Adventure character of the same element (STAND_INS), copied under the
    # Giant's file name; the extended portrait/video/sprite entries reuse that character's.
    # (Tests 10 and 11 had the names and entries but not the Minion_Loads membership: the portal refused them.)
    giants_patch("test12", report)

    # test 36 (as built up by tests 33-35): every Giant's own data (tools/convert_character.py) with everything
    # found so far (tests 13-35 are in docs/TESTS.md). His start-up script sets 'Starting Scale XYZ' (Giants' global macro does it from a 'default
    # scale' parameter Spyro's Adventure's version lacks, so he was spawned at scale 0), with the ops inserted in
    # place; every written file has its reference counts recomputed (tests 19 and 20 crashed on a shared object
    # whose count did not include the new op); stubs of renamed macros and structures carry Spyro's Adventure's
    # names, his controller-off calls use its macro, parameters his calls leave out are passed with Spyro's
    # Adventure's defaults where those are not 0, and his sound calls use Spyro's Adventure's sound macros
    # (tools/script_fixes.py); two Giants-only macros of his B charge are local macros of his script
    # (tools/macro_port.py). The life-bar head texture is 80x80. Pool B patch. Levels with push blocks get Giants'
    # reach (tools/level_fixes.py, LEVEL_FIXES).
    # Then the variant figures (tools/variants.py; tests 34 and 35), and writes to engine members Spyro's
    # Adventure's engine lacks dropped (script_fixes.drop_missing_member_writes; Bouncer's B attack crashed in 35).
    giants_patch("test41", report, converted={g[4] for g in giants.GIANTS}, variant_figures=True)
    report["levels"] = write_levels()


# Converted characters by (file stem, global imports, sound mode, with .arc): tests built from the same global
# imports share them instead of converting again.
_CONVERTED = {}


def converted_character(stem, extra, sound_mode, with_arc=True):
    key = (stem, tuple(sorted(extra.items())), sound_mode, with_arc)
    if key not in _CONVERTED:
        _CONVERTED[key] = convert_character.build(stem, extra, sound_mode, with_arc)
    return _CONVERTED[key]


def giants_patch(test, report, converted=(), sound_mode="convert", variant_figures=False):
    """The 8 Giants with names, toy entries, character-list membership, collection bits and portrait sets
    (test 12). Giants whose file stem is in `converted` get their own converted character files; the others are
    played by STAND_INS. variant_figures: also the variants of the converted Giants (tools/variants.py)."""
    problems = giants.verify()
    if variant_figures:
        problems += variants.verify()
    if problems:
        raise SystemExit(f"{test}: Giants table disagrees with the Giants disc: " + "; ".join(problems))
    alts = [v for v in variants.VARIANTS if variant_figures and v[4] in converted]
    a, level, gdoc = global_archive()
    stand_in = stand_in_positions(gdoc)
    before = len(minions.string_infos(gdoc))
    exports = giants.add_names(a, level, gdoc)
    positions = giants.add_to_character_list(gdoc, exports)
    giants.extend_collection_words(gdoc)
    order = [positions[g[0]] for g in giants.GIANTS]
    picks = [stand_in[g[2]] for g in giants.GIANTS]
    extended = {"ChampionIntroVideos": giants.extend_parallel_set(gdoc, "ChampionIntroVideos", order, picks)}
    expect = {}
    for k, (_, name, _, _, file_name) in enumerate(giants.GIANTS):
        expect[before + 2 * k], expect[before + 2 * k + 1] = file_name, name
    extra = {}
    for stem in sorted(converted) + [v[3] for v in alts]:
        need = [x for x in convert_character.needed_globals(stem) if tuple(x[:2]) not in extra]
        if need:
            extra.update(giants.add_imported_globals(a, gdoc, need))
    alt_exports, loader = {}, None
    if alts:
        first = len(minions.string_infos(gdoc))
        alt_exports = variants.add_load_names(a, gdoc, alts)
        expect.update({first + k: v[3] for k, v in enumerate(alts)})
        loader = variants.patch_loader(Level.from_doc(gdoc))
    report[test] = write_global(test, a, level, gdoc, expect)
    if loader:
        report[test]["loader"] = loader
    report[test]["globals_added"] = {f"{t}:{n}": hex(i) for (t, n), i in extra.items()}
    ids = {g[0] for g in giants.GIANTS} | {c for v in alts for c in variants.codes(v[0], v[5])}

    def edit_init_setup(lv):
        giants.add_entries(lv, exports)
        if alts:
            lv._index(lv.doc)
            variants.add_entries(lv, alt_exports, alts)
    report[test]["init_setup"] = write_init_setup(test, edit_init_setup, want=ids | {16, 416}, absent=set())
    for f, sets in PARALLEL_SETS.items():
        def edit(doc, sets=sets):
            for name in sets:
                extended[f"{f}:{name}"] = giants.extend_parallel_set(doc, name, order, picks)
        report[test].setdefault("misc_references_recounted", {})[f] = write_misc(test, f, edit)
    report[test]["minion_loads_positions"] = order
    report[test]["sets_extended"] = extended
    out = os.path.join(OUT, PATCH, test)
    report[test]["characters"] = {}
    for fid, name, element, _, file_name in giants.GIANTS:
        if file_name in converted:
            bld, arc, conv = converted_character(file_name, extra, sound_mode)
            iga.write_v4(bld, os.path.join(out, file_name + ".bld"), compress=True)
            iga.write_v4(arc, os.path.join(out, file_name + ".arc"))
            for ext in (".bld", ".arc"):
                check_archive(test, iga.read(os.path.join(out, file_name + ext)))
            report[test]["characters"][name] = {"converted": conv["sizes"], "voice_lines": conv["voice_lines"]}
        else:
            for ext in (".arc", ".bld"):
                shutil.copy2(paths.ssa("character", STAND_INS[element] + ext), os.path.join(out, file_name + ext))
            report[test]["characters"][name] = "stand-in " + STAND_INS[element]
    for fid, name, _, stem, base, _ in alts:
        bld, _, conv = converted_character(stem, extra, sound_mode, with_arc=False)
        iga.write_v4(bld, os.path.join(out, stem + ".bld"), compress=True)
        check_archive(test, iga.read(os.path.join(out, stem + ".bld")))
        report[test]["characters"][name] = {"converted": conv["sizes"], "arc": base + ".arc"}


# Levels given the level fixes (tools/level_fixes.py): the 29 that carry the push-block script (found by scanning
# every level's IGZ for its 'Minion Pushing Me' variable; push_block_reach checks each has the three facing checks).
LEVEL_FIXES = [
    "Challenge_Level_004.bld", "Challenge_Level_007.bld", "Challenge_Level_018.bld", "Challenge_Level_023.bld",
    "Challenge_Level_025.bld", "Challenge_Level_028.bld", "Challenge_Level_029.bld", "Level_000_Mining.bld",
    "Level_001_Castle.bld", "Level_002_Dungeon.bld", "Level_006_IslandEscort.bld", "Level_008_IslandTown.bld",
    "Level_009_Minefield.bld", "Level_010b_FinalBattle.bld", "Level_014_OilIsland.bld", "Level_019_StoneGolem.bld",
    "Level_021_Sheep.bld", "Level_023_SpiderDungeon.bld", "Level_024_MineTrain.bld", "Level_026_AirCastle.bld",
    "Level_027_Tutorial.bld", "Level_032_Haunted_Castle.bld", "Level_034_TrollHub.bld",
    "Level_036_Haunted_Expansion.bld", "Level_038_Tree_Adventure.bld", "Level_039_UndeadVolcano.bld",
    "Level_040_TrollTrenches.bld", "Level_046_Dragon_Expansion.bld", "Level_Hub_stage4.bld",
]
# Fixed levels are kept between builds (they take a minute each to compress) and shared by the tests that use them.
LEVEL_CACHE = os.path.join(ROOT, "build", "level_cache")
LEVELS = "levels"  # folder of the fixed levels in the patch


def write_levels():
    """The fixed levels in <patch>/levels, from build/level_cache when neither the source level nor
    tools/level_fixes.py changed. Returns {level: what was done}."""
    out = os.path.join(OUT, PATCH, LEVELS)
    os.makedirs(out, exist_ok=True)
    os.makedirs(LEVEL_CACHE, exist_ok=True)
    fixer = hashlib.sha1(open(level_fixes.__file__, "rb").read()).hexdigest()
    done = {}
    for name in LEVEL_FIXES:
        src = paths.ssa("level", name)
        stamp = f"{fixer} {os.path.getsize(src)} {int(os.path.getmtime(src))}"
        cached, stamp_file = os.path.join(LEVEL_CACHE, name), os.path.join(LEVEL_CACHE, name + ".stamp")
        if os.path.exists(cached) and os.path.exists(stamp_file) and open(stamp_file).read() == stamp:
            done[name] = "cached"
        else:
            what = level_fixes.fix_level_archive(src, cached)
            if not what.startswith("3 "):
                raise SystemExit(f"{name}: {what}")
            check_archive(LEVELS, iga.read(cached), iga.read(src))
            with open(stamp_file, "w") as f:
                f.write(stamp)
            done[name] = what
        link_or_copy(cached, os.path.join(out, name))
    return done


def link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def sync_tree(src, dst):
    """Make dst a copy of src, copying only files whose size or modification time differ."""
    keep = set()
    for root, _, files in os.walk(src):
        rel = os.path.relpath(root, src)
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in files:
            a, b = os.path.join(root, f), os.path.join(dst, rel, f)
            keep.add(os.path.normcase(os.path.abspath(b)))
            sa = os.stat(a)
            if os.path.exists(b):
                sb = os.stat(b)
                if sb.st_size == sa.st_size and int(sb.st_mtime) == int(sa.st_mtime):
                    continue
            shutil.copy2(a, b)
    for root, _, files in os.walk(dst, topdown=False):
        for f in files:
            b = os.path.join(root, f)
            if os.path.normcase(os.path.abspath(b)) not in keep:
                os.remove(b)
        if root != dst and not os.listdir(root):
            os.rmdir(root)  # a test that is no longer built


def stand_in_positions(gdoc):
    """{element: Minion_Loads position of that element's stand-in}, by the load names' pack translations."""
    a = iga.read(paths.ssa("permanent", "global.bld"))
    eng = langpack.strings(IgzDoc(next(e for e in a.entries if e.name == "ENGLISH.pak").data))
    ordinal = {o: k for k, o in enumerate(minions.string_infos(gdoc))}
    files = [eng[ordinal[o]] for o in giants.set_members(gdoc, "Minion_Loads")]
    return {element: files.index(stem) for element, stem in STAND_INS.items()}


def write_misc(test, name, edit):
    """misc/<name> with edit(doc) applied to its level entry, compressed and checked."""
    out = os.path.join(OUT, PATCH, test)
    os.makedirs(out, exist_ok=True)
    a = iga.read(paths.ssa("misc", name))
    level = next(e for e in a.entries if e.name == "level.bld")
    doc = IgzDoc(level.data)
    edit(doc)
    level.data = doc.to_bytes()
    dst = os.path.join(out, name)
    iga.write_v4(a.entries, dst, compress=True)
    check_archive(test, iga.read(dst))
    return refcounts.summary(doc, doc.recounted)


def doc_set(doc, name):
    """The list object of ScriptSet `name`."""
    return doc.u32(minions.find_set(doc, name) + 0x18)


def global_archive():
    a = iga.read(paths.ssa("permanent", "global.bld"))
    level = max(a.entries, key=lambda e: len(e.data))
    return a, level, IgzDoc(level.data)


def write_global(test, a, level, doc, expect):
    """Write global.bld for a test and check that the StringInfo count matches every pack and that pack strings
    sit at the expected positions ({position: text})."""
    out = os.path.join(OUT, PATCH, test)
    os.makedirs(out, exist_ok=True)
    level.data = doc.to_bytes()
    dst = os.path.join(out, "global.bld")
    iga.write_v4(a.entries, dst, compress=True)
    back = iga.read(dst)
    check_archive(test, back)
    n = len(minions.string_infos(IgzDoc(max(back.entries, key=lambda e: len(e.data)).data)))
    for e in back.entries:
        if e.name.endswith(".pak"):
            values = langpack.strings(IgzDoc(e.data))
            if len(values) != n or any(values[k] != v for k, v in expect.items()):
                raise SystemExit(f"{test}: {e.name} does not match the level's {n} StringInfo objects")
    return {"size": os.path.getsize(dst), "string_infos": n,
            "references_recounted": refcounts.summary(doc, doc.recounted)}


def check_archive(test, archive, source=None):
    """Every IGZ entry of a written archive must pass IgzDoc.check (valid pointers, handles, string refs) and have
    every object's reference count equal to its live owning pointers (refcounts.py). With source (the archive it
    was made from), only problems the source entry does not have already count: some retail levels fail the check
    as shipped (Level_009_Minefield: 4 handle fields without the handle bit)."""
    old = {e.name: e.data for e in source.entries} if source else {}
    for e in archive.entries:
        if e.data[:4] == b"IGZ\x01":
            doc = IgzDoc(e.data)
            base = IgzDoc(old[e.name]) if old.get(e.name, b"")[:4] == b"IGZ\x01" else None
            known = set(base.check()) if base else set()
            problems = [p for p in doc.check() if p not in known]
            if problems:
                raise SystemExit(f"{test}: {e.name}: {len(problems)} bad fixups, first: {problems[:3]}")
            off = refcounts.balance(doc)
            if off and base is not None:
                known_off = refcounts.balance(base)
                off = {o: v for o, v in off.items() if known_off.get(o) != v}
            if off:
                raise SystemExit(f"{test}: {e.name}: {len(off)} reference counts off: "
                                 f"{refcounts.summary(doc, off)[:3]}")


def copy_spyro_as(test, stem):
    out = os.path.join(OUT, PATCH, test)
    for ext in (".arc", ".bld"):
        shutil.copy2(paths.ssa("character", "016_Spyro" + ext), os.path.join(out, stem + ext))


def write_init_setup(test, edit, want, absent):
    """misc/Init_Setup.bld with `edit` applied to its level, compressed; checks the toy table afterwards."""
    out = os.path.join(OUT, PATCH, test)
    os.makedirs(out, exist_ok=True)
    src = paths.ssa("misc", "Init_Setup.bld")
    lv = Level(src)
    edit(lv)
    a = iga.read(src)
    a.entries[0].data = lv.doc.to_bytes()
    dst = os.path.join(out, "Init_Setup.bld")
    iga.write_v4(a.entries, dst, compress=True)
    check_archive(test, iga.read(dst))
    codes = toys.item_codes(Level(dst))
    if not want <= set(codes) or absent & set(codes):
        raise SystemExit(f"{test}: toy table did not read back as expected")
    return {"size": os.path.getsize(dst), "retail_size": os.path.getsize(src), "entries": len(codes),
            "references_recounted": refcounts.summary(lv.doc, lv.doc.recounted)}


def file_line(disc, external, create=False):
    extra = ' create="true"' if create else ""
    return f'    <file disc="{disc}" external="/{PATCH}/{external}"{extra} />'


def memory_line(address, original, value):
    return f'    <memory offset="{address:#010x}" value="{value:08x}" original="{original:08x}" />'


def level_lines():
    return [file_line(f"/level/{name}", f"{LEVELS}/{name}") for name in LEVEL_FIXES]


def giants_lines(test):
    return ([file_line("/misc/Init_Setup.bld", f"{test}/Init_Setup.bld"),
             file_line("/permanent/global.bld", f"{test}/global.bld")]
            + [file_line(f"/misc/{f}", f"{test}/{f}") for f in PARALLEL_SETS]
            + [file_line(f"/character/{g[4]}{ext}", f"{test}/{g[4]}{ext}", create=True)
               for g in giants.GIANTS for ext in (".arc", ".bld")])


def variant_lines(test):
    """The variants' files: their own .bld, and the base Giant's .arc under the variant's name."""
    return [line for v in variants.VARIANTS
            for line in (file_line(f"/character/{v[3]}.bld", f"{test}/{v[3]}.bld", create=True),
                         file_line(f"/character/{v[3]}.arc", f"{test}/{v[4]}.arc", create=True))]


def new_character_lines(test):
    return [file_line("/misc/Init_Setup.bld", f"{test}/Init_Setup.bld"),
            file_line("/permanent/global.bld", f"{test}/global.bld"),
            file_line(f"/character/{NEW_FILE}.arc", f"{test}/{NEW_FILE}.arc", create=True),
            file_line(f"/character/{NEW_FILE}.bld", f"{test}/{NEW_FILE}.bld", create=True)]


def write_xml(path):
    """The test patches' Riivolution XML: one choice and one patch per test in TESTS."""
    patches = {
        "test1": [file_line("/character/016_Spyro.arc", "test1/016_Spyro.arc"),
                  file_line("/character/016_Spyro.bld", "test1/016_Spyro.bld")],
        "test7": [file_line("/misc/Init_Setup.bld", "test7/Init_Setup.bld")],
        "test8": [file_line("/misc/Init_Setup.bld", "test8/Init_Setup.bld")],
        "test9": new_character_lines("test9"),
        "test12": giants_lines("test12"),
        "test41": giants_lines("test41") + variant_lines("test41") + level_lines()
        + [memory_line(CHARACTER_POOL_B, 0x00100000, 0x00180000)],
    }
    choices = "\n".join(f'        <choice name="{name}">\n          <patch id="gp_{t}" />\n        </choice>'
                        for t, name in TESTS.items())
    body = "\n".join(f'  <patch id="gp_{t}">\n' + "\n".join(lines) + "\n  </patch>" for t, lines in patches.items())
    xml = f"""<wiidisc version="1">
  <id game="SSP">
    <region type="P" />
  </id>
  <options>
    <section name="Giants port tests">
      <option name="Test">
{choices}
      </option>
    </section>
  </options>
{body}
</wiidisc>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true",
                    help="install the patch for playing (RELEASE_TEST as RELEASE_MENU) into Dolphin's Load/Riivolution")
    ap.add_argument("--install-tests", action="store_true", help="install every test patch into Dolphin")
    ap.add_argument("--sd", metavar="ROOT", help="install the patch for playing at the root of a Wii SD card or USB "
                                                 "drive, for Riivolution (for example E:\\)")
    ap.add_argument("--no-build", action="store_true", help="install what build/riivolution already holds")
    args = ap.parse_args()

    if not args.no_build:
        if os.path.isdir(OUT):
            shutil.rmtree(OUT)
        report = {}
        build(report)
        os.makedirs(os.path.join(OUT, "riivolution"))
        write_xml(os.path.join(OUT, "riivolution", XML))
        with open(os.path.join(ROOT, "build", "report.json"), "w") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
    elif not os.path.isdir(os.path.join(OUT, PATCH)):
        raise SystemExit("nothing built yet: run without --no-build first")
    else:
        write_xml(os.path.join(OUT, "riivolution", XML))  # the XML depends on nothing the build reports

    dolphin = os.path.join(paths.DOLPHIN_USER, "Load", "Riivolution")
    if (args.install or args.install_tests) and not os.path.isdir(dolphin):
        raise SystemExit(f"Dolphin Riivolution folder not found: {dolphin}")
    if args.install_tests:
        sync_tree(os.path.join(OUT, PATCH), os.path.join(dolphin, PATCH))
        os.makedirs(os.path.join(dolphin, "riivolution"), exist_ok=True)
        shutil.copy2(os.path.join(OUT, "riivolution", XML), os.path.join(dolphin, "riivolution", XML))
        print(f"test patches installed into {dolphin}")
    if args.install:
        print(f"installed into {dolphin}: {install_release(dolphin)}")
    if args.sd:
        print(f"installed into {args.sd}: {install_release(args.sd)}")


def release_patch():
    """The patch for playing, from RELEASE_TEST's patch in the built test XML: (XML text, {path under
    RELEASE_FOLDER: built file}). Each built file appears once, under the disc path of its first use (the variants'
    .arc lines reuse their base Giant's .arc)."""
    import xml.etree.ElementTree as ET
    built = ET.parse(os.path.join(OUT, "riivolution", XML)).getroot()
    patch = next(p for p in built.findall("patch") if p.get("id") == f"gp_{RELEASE_TEST}")
    lines, files, names = [], {}, {}
    for el in patch:
        if el.tag == "file":
            source = el.get("external").strip("/")
            name = names.setdefault(source, el.get("disc").strip("/"))
            files[name] = os.path.join(OUT, *source.split("/"))
            create = ' create="true"' if el.get("create") == "true" else ""
            lines.append(f'    <file disc="{el.get("disc")}" external="/{RELEASE_FOLDER}/{name}"{create} />')
        elif el.tag == "memory":
            lines.append(f'    <memory offset="{el.get("offset")}" value="{el.get("value")}" '
                         f'original="{el.get("original")}" />')
        else:
            raise SystemExit(f"{RELEASE_TEST}: cannot carry <{el.tag}> into the release patch")
    section, option, choice = RELEASE_MENU
    xml = f"""<wiidisc version="1">
  <id game="SSP">
    <region type="P" />
  </id>
  <options>
    <section name="{section}">
      <option name="{option}">
        <choice name="{choice}">
          <patch id="giants_port" />
        </choice>
      </option>
    </section>
  </options>
  <patch id="giants_port">
""" + "\n".join(lines) + "\n  </patch>\n</wiidisc>\n"
    return xml, files


def install_release(root):
    """Install the patch for playing at a Riivolution root (Dolphin's Load/Riivolution, a Wii SD card or USB
    drive): riivolution/RELEASE_XML and exactly its files under RELEASE_FOLDER/ (anything else there is removed;
    files whose size and time already match are not copied again). A test XML installed there before the folders
    were renamed (one naming /giants-port/) is removed too. Returns {files, bytes copied}."""
    xml, files = release_patch()
    os.makedirs(os.path.join(root, "riivolution"), exist_ok=True)
    with open(os.path.join(root, "riivolution", RELEASE_XML), "w", encoding="utf-8") as f:
        f.write(xml)
    old = os.path.join(root, "riivolution", XML)
    if os.path.exists(old) and f'external="/{RELEASE_FOLDER}/' in open(old, encoding="utf-8").read():
        os.remove(old)
    keep, copied = set(), 0
    for name, src in files.items():
        dst = os.path.join(root, RELEASE_FOLDER, *name.split("/"))
        keep.add(os.path.normcase(os.path.abspath(dst)))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src) and \
                int(os.path.getmtime(dst)) == int(os.path.getmtime(src)):
            continue
        shutil.copy2(src, dst)
        copied += os.path.getsize(src)
    for folder, _, names in os.walk(os.path.join(root, RELEASE_FOLDER), topdown=False):
        for n in names:
            if os.path.normcase(os.path.abspath(os.path.join(folder, n))) not in keep:
                os.remove(os.path.join(folder, n))
        if not os.listdir(folder):
            os.rmdir(folder)
    return {"files": len(files), "bytes copied": copied}


if __name__ == "__main__":
    main()
