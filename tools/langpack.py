"""Read and edit the language packs (FRENCH.pak, ENGLISH.pak, ...) stored next to level.bld in a .bld archive.

Layout (verified on permanent/global.bld, see docs/FORMATS.md):
  IGZ with types igObjectList, LanguagePackInfo, tfbSoundDataInfo; sections Default, String, Text.
  LanguagePackInfo  +0x08 language name (string ref), +0x14 language id, +0x18 0x80000000 | text bytes,
                    +0x1C -> Text section + 4
  Text section      4 zero bytes, then NUL-terminated UTF-16BE strings back to back.

The level's StringInfo objects, taken in address order, get the pack's strings in the same order: global.bld has
588 StringInfo objects and every pack 588 strings ("MinionLoad_004_RockDragon" -> "004_Rock_Dragon", the file
name; "016_Toy_Name_Legendary" -> "L-Spyro"). A new StringInfo therefore needs a new string in every pack, at the
same position.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from igzdoc import IgzDoc, OBJECTS  # noqa: E402

TEXT_START = 4


def pack_info(doc: IgzDoc) -> int:
    t = doc.type_index("LanguagePackInfo")
    return next(o for o in doc.lists[OBJECTS] if doc.u32(o) == t)


def strings(doc: IgzDoc) -> list:
    text = bytes(doc.blobs[doc.section_by_pool("Text")])
    out, i = [], TEXT_START
    while i + 1 < len(text):
        j = i
        while text[j:j + 2] != b"\0\0":
            j += 2
        out.append(text[i:j].decode("utf-16-be"))
        i = j + 2
    return out


def set_strings(doc: IgzDoc, values) -> None:
    """Replace the pack's text with values (same order as the level's StringInfo objects)."""
    sec = doc.section_by_pool("Text")
    body = b"".join(v.encode("utf-16-be") + b"\0\0" for v in values)
    doc.blobs[sec][:] = bytes(TEXT_START) + body
    info = pack_info(doc)
    doc.set_u32(info + 0x18, 0x80000000 | len(body))


def language(doc: IgzDoc) -> str:
    return doc.cstr(doc.u32(pack_info(doc) + 0x08))


def packs(archives) -> dict:
    """{language: pack data} of the .pak entries of several archives (the same .bld from both Giants discs, three
    languages each). A language found twice is an error."""
    out = {}
    for a in archives:
        for e in a.entries:
            if e.name.endswith(".pak"):
                lang = language(IgzDoc(e.data))
                if lang in out:
                    raise ValueError(f"{lang} pack found twice")
                out[lang] = e.data
    return out


def texts(archive) -> dict:
    """{language: {StringInfo key: text}} of a .bld archive: each pack's strings matched to level.bld's StringInfo
    objects in address order, by key, so that strings can be looked up in the packs of another disc's edition
    of the file."""
    import minions
    level = IgzDoc(next(e.data for e in archive.entries if e.name == "level.bld"))
    keys = [level.cstr(level.u32(o + 8)) for o in minions.string_infos(level)]
    if len(set(keys)) != len(keys):
        raise ValueError("StringInfo keys are not unique")
    out = {}
    for e in archive.entries:
        if e.name.endswith(".pak"):
            doc = IgzDoc(e.data)
            values = strings(doc)
            if len(values) != len(keys):
                raise ValueError(f"{e.name}: {len(values)} strings for {len(keys)} StringInfo objects")
            out[language(doc)] = dict(zip(keys, values))
    return out


def edit_packs(entries, fn) -> None:
    """Apply fn(language, list_of_strings) -> list_of_strings to every .pak entry of an archive, in place."""
    for e in entries:
        if not e.name.endswith(".pak"):
            continue
        doc = IgzDoc(e.data)
        values = fn(language(doc), strings(doc))
        set_strings(doc, values)
        e.data = doc.to_bytes()


if __name__ == "__main__":
    import iga
    a = iga.read(sys.argv[1])
    for e in a.entries:
        if e.name.endswith(".pak"):
            doc = IgzDoc(e.data)
            vals = strings(doc)
            print(e.name, language(doc), len(vals))
            for k in map(int, sys.argv[2:]):
                print(f"   {k}: {vals[k]!r}")
