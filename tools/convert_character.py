"""Convert a Giants character (character/<stem>.bld and .arc) for Spyro's Adventure.

usage: python tools/convert_character.py [stem, default 112_TitanLife]   (offline check only)

  .bld  level.bld: tools/convert.py with Havok templates from Spyro's Adventure's Spyro, lip-sync animations
        (tfbPhysicsAnimation data that is not a Havok packfile; only voice lines reference them) dropped, global.bld
        imports remapped by type and name. Language packs: converted the same way, each language's own from the
        Giants disc that has it (paths.giants_discs: Spanish, German and Italian on the DE/ES/IT disc, English,
        French and Dutch on the EN/FR/NL disc).
  .arc  both discs' entries together (giants_arc: each disc adds the voice lines of its three languages);
        upgrade-pose textures converted; FSB5 sounds re-wrapped as FSB4 (tools/fsb.py). Entry names and hashes
        are kept.
"""
import collections
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert  # noqa: E402
import convert_check  # noqa: E402
import fsb  # noqa: E402
import giant_imports  # noqa: E402
import giants  # noqa: E402
import hkpack  # noqa: E402
import iga  # noqa: E402
import langpack  # noqa: E402
import macro_port  # noqa: E402
import minions  # noqa: E402
import paths  # noqa: E402
import script_fixes  # noqa: E402
from igzdoc import IgzDoc, OBJECTS  # noqa: E402
from toy_table import Level  # noqa: E402

GLOBAL = iga.fnv1a(b"global.bld")
# Spyro's Adventure's packs: language name and id (LanguagePackInfo +0x08, +0x14), in its archive order
LANGUAGES = [("FRENCH", 8), ("SPANISH", 0x15), ("DUTCH", 5), ("ENGLISH", 6), ("GERMAN", 9), ("ITALIAN", 0xE)]


def havok_templates():
    """One Spyro's Adventure skeleton packfile and one animation packfile (header and class names are reused)."""
    lv = Level(paths.ssa("character", "016_Spyro.bld"))
    d = lv.doc
    blob0 = bytes(d.blobs[0])
    at = hkpack.packfiles_in(blob0)[0]
    skeleton = hkpack.parse(blob0[at:at + hkpack.length(blob0, at)])
    ai = next(i for i in range(1, len(d.sections)) if d.pool_name(i) == "AnimationData") - 1
    blob = bytes(d.blobs[ai])
    at = hkpack.packfiles_in(blob)[0]
    animation = hkpack.parse(blob[at:at + hkpack.length(blob, at)])
    return {"skeleton": skeleton, "animation": animation}


def lip_sync(doc: IgzDoc):
    """tfbPhysicsAnimation objects whose data is not a Havok packfile, and their data ranges."""
    if "tfbPhysicsAnimation" not in doc.types:
        return set(), []
    t = doc.type_index("tfbPhysicsAnimation")
    objs, ranges = set(), []
    for o in doc.lists[OBJECTS]:
        if doc.u32(o) != t:
            continue
        ptr, size = doc.u32(o + 0x18), doc.u32(o + 0x14) & 0xFFFFFF
        if doc.read(ptr, 8) != hkpack.MAGIC:
            objs.add(o)
            ranges.append((ptr, size))
    return objs, ranges


_GLOBALS = {}


def globals_pair():
    """(Giants global.bld, Spyro's Adventure global.bld) indexes, built once."""
    if not _GLOBALS:
        _GLOBALS["giants"] = giant_imports.Global(paths.giants("permanent", "global.bld"), giants.GIANTS_EXPORT_BASE)
        _GLOBALS["ssa"] = giant_imports.Global(paths.ssa("permanent", "global.bld"), minions.EXPORT_BASE)
    return _GLOBALS["giants"], _GLOBALS["ssa"]


def import_map(doc: IgzDoc, extra=None):
    """{(Giants index, hash): (Spyro's Adventure index, hash)} for global.bld imports, matched by type and name.
    extra: {(type, name): index} for objects added to Spyro's Adventure's global.bld. Returns (map, missing)."""
    if not any(r.tag == 0x02 for r in doc.records):
        return {}, []
    rec = doc.record(0x02)
    if not any(struct.unpack_from(">II", rec.body, 8 * k)[1] == GLOBAL for k in range(rec.count)):
        return {}, []
    gg, sg = globals_pair()
    rec = doc.record(0x02)
    out, missing = {}, []
    for k in range(rec.count):
        idx, h = struct.unpack_from(">II", rec.body, 8 * k)
        if h != GLOBAL:
            continue
        desc = gg.describe(idx)
        new = sg.find(desc)
        if new is None and extra:
            new = extra.get(desc[:2])
        if new is None:
            missing.append((k, idx, desc))
            continue
        out[(idx, h)] = (new, h)
    return out, missing


_SOUND_TEMPLATES = {}


def sound_templates():
    if not _SOUND_TEMPLATES:
        _SOUND_TEMPLATES.update(fsb.templates())
    return _SOUND_TEMPLATES


def convert_sound(blob, mode):
    if mode == "substitute":
        return sound_templates()[1]
    return fsb.convert(blob, sound_templates())


def convert_igz(data: bytes, templates=None, extra=None, strict=True, sound_mode="convert"):
    """Convert one IGZ blob; returns (bytes, report). strict: fail on unresolved global imports or check errors.
    Embedded FSB5 sound banks are always re-wrapped (sound_mode "substitute": replaced by a known-good Spyro's
    Adventure sound, for diagnosis); Havok packfiles need templates."""
    doc = IgzDoc(data)
    old = IgzDoc(data)
    drop_objs, drop_ranges = lip_sync(doc)
    imap, missing = import_map(doc, extra)
    if missing and strict:
        raise ValueError(f"global.bld imports without a Spyro's Adventure counterpart: {missing}")
    conv = convert.Converter(doc, templates, imap, drop_objs, drop_ranges, sound_templates())
    if sound_mode == "substitute":
        conv.sound_converter = lambda raw: sound_templates()[1]
    out = conv.run().to_bytes()
    back = IgzDoc(out)
    check = convert_check.check(old, conv, back, limit=0)
    unexpected = {k: v for k, v in check.items() if "field dropped" not in k}
    problems = back.check() + convert_check.check_blocks(conv, back)
    if strict and (unexpected or problems or conv.problems):
        raise ValueError(f"conversion check failed: {unexpected} {problems[:3]} {conv.problems[:3]}")
    return out, {"dropped_lip_sync": len(drop_objs), "check": dict(check), "missing": missing,
                 "blocks_converted": len(conv.resized)}


# UI conventions that differ between the games (docs/FORMATS.md, "Converting a Giants character")
# Ability pictures: Spyro's Adventure's are 512x512 with the picture in rows 77-434 (147 of 197 pictures) and
# transparent above and below; Giants' are the picture alone, 256x180. Its menu fits the texture into the same
# frame, so a 256x180 one is drawn about a third too large (test 16).
PICTURE_SIZE, PICTURE_TOP, GIANTS_PICTURE = (512, 512), 76, (256, 180)
# Life-bar head ("NNN_MinionHead" sprite, cloned by "UI - Create Player Health UI", which sets its position but not
# its size): the HUD draws it at the size of its texture. Spyro's Adventure's head textures are 80x80 cut-outs;
# Giants' is a 128x128 round portrait, drawn about 1.6 times too large (tests 16-18 looked identical with sprite
# sizes 128, 80 and 64, so the sprite's own +0xB4/+0xB8 does not matter there). The texture is scaled to 80x80 and
# every size that describes it set to match.
HEAD_SIZE = 80
HEAD_SPRITE = re.compile(r"\d+_MinionHead(_\w+)?")  # the life-bar head sprite's name


# Spyro's Adventure stores each ability picture as two 512x512 CMPR images, the colour (igImage2 +0x1C = 1) and a
# grey alpha mask (+0x1C = 0), which its tfbAlphaTextureUnitIDAttr (+0x10 = 1) binds to the alpha texture unit
# (every picture of its characters, e.g. 016_Spyro.arc). Giants' are mostly one CMPR image with 1-bit alpha
# (+0x1C = 3) and no alpha unit (-1); in Spyro's Adventure's upgrade menu such a picture takes its alpha from
# whatever texture the unit held before, so some of them did not show (test 36). A few Giants pictures are already
# colour and mask (Eye-Brawl's secondary attack). Either way the picture is redrawn into a copy of one of Spyro's
# Adventure's own picture files from the player's disc.
PICTURE_TEMPLATE = ("016_Spyro.arc", "/spyro_up1.png/")
_PICTURE_TEMPLATE = []


def picture_template() -> bytes:
    if not _PICTURE_TEMPLATE:
        a = iga.read(paths.ssa("character", PICTURE_TEMPLATE[0]))
        _PICTURE_TEMPLATE.append(next(e.data for e in a.entries if PICTURE_TEMPLATE[1] in e.name.lower()))
    return _PICTURE_TEMPLATE[0]


def _images(doc):
    t = doc.type_index("igImage2")
    return [o for o in doc.lists[OBJECTS] if doc.u32(o) == t]


def _image_pixels(doc, image):
    import gxtex
    wh = doc.u32(image + 0x0C)
    size, enc = struct.unpack_from(">II", doc.record(0x0A).body, 8 * doc.u32(image + 0x24))
    return gxtex.decode_cmpr(doc.read(enc, size & 0xFFFFFF), wh >> 16, wh & 0xFFFF)


def widen_picture(data: bytes) -> bytes:
    """A converted Giants ability picture (256x180: one CMPR image with 1-bit alpha, or a colour image and its mask)
    laid out as Spyro's Adventure's: a colour image and an alpha mask, 512x512, the picture scaled 2x into the middle
    band and transparent elsewhere, in a copy of one of its own picture files. Other textures are returned
    unchanged."""
    import gxtex
    doc = IgzDoc(data)
    if "igImage2" not in doc.types:
        return data
    images = _images(doc)
    if not images or any(doc.u32(o + 0x0C) != (GIANTS_PICTURE[0] << 16 | GIANTS_PICTURE[1]) for o in images):
        return data
    kinds = sorted(doc.u32(o + 0x1C) for o in images)
    if kinds == [3]:
        rgba = _image_pixels(doc, images[0])
    elif kinds == [0, 1]:
        colour = _image_pixels(doc, next(o for o in images if doc.u32(o + 0x1C) == 1))
        mask = _image_pixels(doc, next(o for o in images if doc.u32(o + 0x1C) == 0))
        rgba = [[c[:3] + (m[0],) for c, m in zip(crow, mrow)] for crow, mrow in zip(colour, mask)]
    else:
        raise ValueError(f"ability picture with images of kinds {kinds}")
    pw, ph = PICTURE_SIZE
    scaled = gxtex.resize(rgba, pw, 2 * GIANTS_PICTURE[1])  # colours weighted by alpha: no dark fringe
    black = [(0, 0, 0, 255)] * pw
    rows = [None] * PICTURE_TOP + scaled + [None] * (ph - PICTURE_TOP - len(scaled))
    colour = [black if r is None else [p[:3] + (255,) for p in r] for r in rows]
    alpha = [black if r is None else [(p[3], p[3], p[3], 255) for p in r] for r in rows]
    out = IgzDoc(picture_template())
    blocks = {}
    for o in _images(out):
        if out.u32(o + 0x0C) != (pw << 16 | ph):
            raise ValueError("picture template is not 512x512")
        blocks[out.u32(o + 0x24)] = gxtex.encode_cmpr(colour if out.u32(o + 0x1C) == 1 else alpha)
    convert.rewrite_blocks(out, blocks)
    return out.to_bytes()


def shrink_head(doc: IgzDoc, sprite):
    """Scale the texture of a life-bar head sprite to HEAD_SIZE (sprite -> +0xD0 AnimatableTextureDataInfo -> +0x30
    tfbAlphaTextureUnitIDAttr -> +0x14 igTextureAttr2 -> +0x30 igImage2, one CMPR image) and set the sizes that
    describe it: image, texture info and sprite."""
    import gxtex
    info = doc.u32(sprite + 0xD0)
    unit = doc.u32(info + 0x30)
    attr = doc.u32(unit + 0x14)
    image = doc.u32(attr + 0x30)
    wh = doc.u32(image + 0x0C)
    w, h = wh >> 16, wh & 0xFFFF
    if (w, h) == (HEAD_SIZE, HEAD_SIZE):
        return False
    rec = doc.record(0x0A)
    block = doc.u32(image + 0x24)
    size, enc = struct.unpack_from(">II", rec.body, 8 * block)
    if (size & 0xFFFFFF) != w * h // 2:
        raise ValueError(f"head texture: {w}x{h} with {size & 0xFFFFFF} bytes is not one CMPR level")
    picture = gxtex.decode_cmpr(doc.read(enc, size & 0xFFFFFF), w, h)
    convert.rewrite_blocks(doc, {block: gxtex.encode_cmpr(gxtex.resize(picture, HEAD_SIZE, HEAD_SIZE))})
    doc.set_u32(image + 0x0C, HEAD_SIZE << 16 | HEAD_SIZE)
    doc.set_u32(info + 0x24, HEAD_SIZE)
    doc.set_u32(info + 0x28, HEAD_SIZE)
    fsize = struct.unpack(">I", struct.pack(">f", float(HEAD_SIZE)))[0]
    doc.set_u32(sprite + 0xB4, fsize)
    doc.set_u32(sprite + 0xB8, fsize)
    return True


def adapt_ui(level: bytes) -> bytes:
    """Converted level with Spyro's Adventure's UI conventions: ability pictures declared 512x512 (they are widened
    by widen_picture), the life-bar head texture at HEAD_SIZE (shrink_head)."""
    doc = IgzDoc(level)
    strings = set(doc.lists.get(0x0E, ()))
    if "AnimatableTextureDataInfo" in doc.types:
        t = doc.type_index("AnimatableTextureDataInfo")
        for o in doc.lists[OBJECTS]:
            if doc.u32(o) != t or o + 8 not in strings:
                continue
            if "upgradeposes" in doc.cstr(doc.u32(o + 8)).lower() and \
                    (doc.u32(o + 0x24), doc.u32(o + 0x28)) == GIANTS_PICTURE:
                doc.set_u32(o + 0x24, PICTURE_SIZE[0])
                doc.set_u32(o + 0x28, PICTURE_SIZE[1])
    if "tfbSpriteInfo" in doc.types:
        t = doc.type_index("tfbSpriteInfo")
        for o in list(doc.lists[OBJECTS]):
            # "112_MinionHead"; the variants' files name theirs "112_MinionHead_Alt", "110_MinionHead_Legendary"
            if doc.u32(o) == t and o + 8 in strings and HEAD_SPRITE.fullmatch(doc.cstr(doc.u32(o + 8))):
                shrink_head(doc, o)
    return doc.to_bytes()


def needed_globals(stem):
    """Global objects the character imports that Spyro's Adventure's global.bld lacks (descs for
    giants.add_imported_globals)."""
    a = iga.read(paths.giants("character", stem + ".bld"))
    level = next(e for e in a.entries if e.name == "level.bld")
    _, missing = import_map(IgzDoc(level.data))
    return [d for _, _, d in missing]


def giants_packs(stem):
    """{language: pack} of a Giants character's .bld, from both discs (three languages each). Every pack fits the
    DE/ES/IT disc's level.bld that is converted: on both discs the level's StringInfo keys and the packs' voice-line
    names come in the same order (the levels differ only in macro-parameter build ids, and for Eye-Brawl and
    Legendary Bouncer in some script data)."""
    packs = langpack.packs(iga.read(p) for p in paths.giants_discs("character", stem + ".bld"))
    missing = [lang for lang, _ in LANGUAGES if lang not in packs]
    if missing:
        raise ValueError(f"{stem}: no Giants disc has the {missing} packs")
    return packs


def giants_arc(stem):
    """A Giants character's .arc entries from both discs. Each disc's .arc has the shared entries (textures, sound
    banks, wordless voice sounds), identical on both, and the voice lines of its own languages: german/, spanish/
    and italian/ folders on the DE/ES/IT disc; on the EN/FR/NL disc french/ and dutch/ folders and English in the
    character's own folder, as in Spyro's Adventure's .arc files. A pack's voice line is the entry whose hash is
    FNV-1a of "0x%08x" of its tfbSoundDataInfo key (+0x1C), so the union serves all six packs."""
    entries = {}
    for path in paths.giants_discs("character", stem + ".arc"):
        for e in iga.read(path).entries:
            have = entries.setdefault(e.hash, e)
            if have is not e and (have.name, have.data) != (e.name, e.data):
                raise ValueError(f"{stem}.arc: {e.name} differs between the Giants discs")
    return list(entries.values())


def voice_lines(pack: bytes):
    """Archive hashes of a pack's streamed voice lines: FNV-1a of "0x%08x" of the key (+0x1C) of each
    tfbSoundDataInfo without data of its own (+0x18)."""
    doc = IgzDoc(pack)
    t = doc.type_index("tfbSoundDataInfo")
    return {iga.fnv1a(f"0x{doc.u32(o + 0x1C):08x}".encode())
            for o in doc.lists[OBJECTS] if doc.u32(o) == t and not doc.u32(o + 0x18)}


def build(stem, extra, sound_mode="convert", with_arc=True):
    """New (.bld entries, .arc entries, report) for a Giants character. extra: global imports added to Spyro's
    Adventure's global.bld ({(type, name): index}). sound_mode "substitute" replaces every sound with one known-good
    Spyro's Adventure sound (diagnosis). with_arc False leaves the .arc out (None): a Giants variant's .arc is
    its base Giant's (variants.verify)."""
    templates = havok_templates()
    a = iga.read(paths.giants("character", stem + ".bld"))
    report = {}
    level = next(e for e in a.entries if e.name == "level.bld")
    giants_level, report["ported_macros"] = macro_port.port(level.data)
    level_data, report["level"] = convert_igz(giants_level, templates, extra, sound_mode=sound_mode)
    level_data = adapt_ui(level_data)
    level_data, report["starting_scale"] = script_fixes.set_starting_scale(level_data)
    level_data, report["renamed_stubs"] = script_fixes.rename_stubs(level_data)
    level_data, report["controller"] = script_fixes.redirect_controller_calls(level_data)
    level_data, report["redirected_calls"] = script_fixes.redirect_calls(level_data)
    level_data, report["parameters_by_name"] = script_fixes.rebind_parameters_by_name(level_data)
    level_data, report["omitted_parameters"] = script_fixes.fill_omitted_parameters(level_data)
    level_data, report["launch_particles"] = script_fixes.drop_post_processed_launch_particles(level_data)
    level_data, report["missing_members"] = script_fixes.drop_missing_member_writes(level_data)
    level_data, report["velocity_reads"] = script_fixes.read_velocity_directly(level_data)
    import variants
    base = next((v[4] for v in variants.VARIANTS if v[3] == stem), None)  # a variant may name its base's objects
    others = [Level(paths.giants("character", base + ".bld"))] if base else []
    level_data, report["definition_physics"] = script_fixes.literal_definition_physics(level_data, others)
    level_data, report["rocket_drops"] = script_fixes.drop_rockets_from_above(level_data)
    level_data, report["playback_rates"] = script_fixes.whole_playback_rates(level_data)
    packs = giants_packs(stem)
    arc_entries = giants_arc(base or stem)  # a variant's .arc is its base Giant's (variants.verify)
    arc_hashes = {e.hash for e in arc_entries}
    bld, report["voice_lines"] = [], {}
    for lang, lang_id in LANGUAGES:
        lines = voice_lines(packs[lang])
        if not lines <= arc_hashes:
            raise ValueError(f"{stem}: {len(lines - arc_hashes)} {lang} voice lines are not in {base or stem}.arc")
        report["voice_lines"][lang] = len(lines)
        data, _ = convert_igz(packs[lang], sound_mode=sound_mode)
        info = IgzDoc(data)
        label = (langpack.language(info), info.u32(langpack.pack_info(info) + 0x14))
        if label != (lang, lang_id):
            raise ValueError(f"{stem}: {lang} pack is labelled {label}")
        bld.append(iga.Entry(f"{lang}.pak", iga.fnv1a(f"{lang}.pak".encode()), data, 0))
    bld.insert(3, iga.Entry("level.bld", iga.fnv1a(b"level.bld"), level_data, 0))
    if not with_arc:
        report["sizes"] = {"level": len(level_data)}
        return bld, None, report
    out_arc, kinds = [], collections.Counter()
    for e in arc_entries:
        data = e.data
        if data[:4] == b"FSB5":
            data = convert_sound(data, sound_mode)
            kinds["sound"] += 1
        elif data[:4] == b"IGZ\x01":
            data, _ = convert_igz(data)
            if "upgradeposes" in e.name.lower():
                wide = widen_picture(data)
                kinds["ability picture widened" if wide != data else "texture"] += 1
                data = wide
            else:
                kinds["texture"] += 1
        else:
            kinds["other " + data[:4].hex()] += 1
        out_arc.append(iga.Entry(e.name, e.hash, data, 0))
    report["arc"] = dict(kinds)
    report["sizes"] = {"level": len(level_data), "arc": sum(len(e.data) for e in out_arc)}
    return bld, out_arc, report


def main():
    stem = sys.argv[1] if len(sys.argv) > 1 else "112_TitanLife"
    need = needed_globals(stem)
    print(f"{stem}: needs {len(need)} global objects added: {need}")
    ga = iga.read(paths.ssa("permanent", "global.bld"))
    gdoc = IgzDoc(max(ga.entries, key=lambda e: len(e.data)).data)
    extra = giants.add_imported_globals(ga, gdoc, need)
    bld, arc, report = build(stem, extra)
    print(report)


if __name__ == "__main__":
    main()
