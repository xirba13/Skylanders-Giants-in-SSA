"""Read and extend the character list (ScriptSet 'Minion_Loads' in permanent/global.bld).

Layout (verified, see docs/FORMATS.md):
  ScriptSet      +0x08 name (string ref), +0x18 -> ScriptSetList
  ScriptSetList  +0x08 count, +0x0C capacity, +0x10 0x80000000 | buffer bytes, +0x14 -> element buffer
  buffer         count pointers to StringInfo objects
  StringInfo     +0x04 reference count, +0x08 string ref ("MinionLoad_016_Spyro")

Adding entries appends new StringInfo objects, their strings, and a new, larger element buffer at the end of
their sections, then points the list at the new buffer. Nothing existing moves, so no other pointer changes.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from igzdoc import IgzDoc, OBJECTS, POINTERS, STRINGS_REF  # noqa: E402

DEFAULT_SECTION = 0  # object section 0: the "Default" pool, where the existing list objects live


def find_set(doc: IgzDoc, name: str) -> int:
    t = doc.type_index("ScriptSet")
    for enc in doc.lists[OBJECTS]:
        if doc.u32(enc) == t and doc.cstr(doc.u32(enc + 8)) == name:
            return enc
    raise KeyError(name)


def entries(doc: IgzDoc, set_name: str) -> list:
    lst = doc.u32(find_set(doc, set_name) + 0x18)
    count, buf = doc.u32(lst + 0x08), doc.u32(lst + 0x14)
    return [doc.cstr(doc.u32(doc.u32(buf + 4 * k) + 8)) for k in range(count)]


ROOT_LIST = 4  # the file's root igObjectList (fixup record 8); other files import its objects by position
EXPORT_BASE = 0x29  # verified for global.bld: an import's index = root-list position + 0x29 (all 56 toy entries)


def new_string_info(doc: IgzDoc, text: str, template: int) -> int:
    """A new StringInfo object (copy of template) holding text; returns its address."""
    obj = bytearray(doc.read(template, doc.type_sizes[doc.type_index("StringInfo")]))
    struct.pack_into(">I", obj, 8, doc.add_string(text))
    enc = doc.add_object(DEFAULT_SECTION, bytes(obj), align=8)
    doc.add_fixup(STRINGS_REF, enc + 8)
    return enc


def append_to_list(doc: IgzDoc, lst: int, ptrs) -> int:
    """Append object pointers to an igObjectList/ScriptSetList (count +8, capacity +0xC, bytes +0x10, data +0x14)
    by moving its elements to a new buffer. Returns the index of the first appended element."""
    count, buf = doc.u32(lst + 0x08), doc.u32(lst + 0x14)
    elems = [doc.u32(buf + 4 * k) for k in range(count)] + list(ptrs)
    nbuf = doc.append(DEFAULT_SECTION, b"".join(struct.pack(">I", p) for p in elems), align=16)
    doc.copy_words(buf, nbuf, count)  # old elements keep their own fixup (pointer or import handle)
    for k in range(count, len(elems)):
        doc.add_fixup(POINTERS, nbuf + 4 * k)
    doc.set_u32(lst + 0x08, len(elems))
    doc.set_u32(lst + 0x0C, len(elems))
    doc.set_u32(lst + 0x10, 0x80000000 | (4 * len(elems)))
    doc.set_u32(lst + 0x14, nbuf)
    return count


def string_infos(doc: IgzDoc) -> list:
    """StringInfo objects in address order; the n-th one takes the n-th string of every language pack."""
    t = doc.type_index("StringInfo")
    return [enc for enc in doc.lists[OBJECTS] if doc.u32(enc) == t]


def export(doc: IgzDoc, encs) -> list:
    """Append objects to the root list; returns the import index other files use for each."""
    first = append_to_list(doc, ROOT_LIST, encs)
    return [first + k + EXPORT_BASE for k in range(len(encs))]


def root_index(doc: IgzDoc, enc: int) -> int:
    """Import index of an object already in the root list."""
    n, buf = doc.u32(ROOT_LIST + 0x08), doc.u32(ROOT_LIST + 0x14)
    hits = [k for k in range(n) if doc.u32(buf + 4 * k) == enc]
    if len(hits) != 1:
        raise ValueError(f"{enc:#x} appears {len(hits)} times in the root list")
    return hits[0] + EXPORT_BASE


def exported(doc: IgzDoc, index: int, base: int = EXPORT_BASE) -> int:
    """Object behind an import index (inverse of root_index). base: 0x29 for Spyro's Adventure's global.bld,
    0x27 for Giants'."""
    return doc.u32(doc.u32(ROOT_LIST + 0x14) + 4 * (index - base))


def add_entries(doc: IgzDoc, set_name: str, names) -> None:
    lst = doc.u32(find_set(doc, set_name) + 0x18)
    count, buf = doc.u32(lst + 0x08), doc.u32(lst + 0x14)
    old = [doc.u32(buf + 4 * k) for k in range(count)]
    existing = set(entries(doc, set_name))
    template = doc.read(old[0], doc.type_sizes[doc.type_index("StringInfo")])
    new = []
    for name in names:
        if name in existing:
            continue
        obj = bytearray(template)
        struct.pack_into(">I", obj, 8, doc.add_string(name))
        enc = doc.add_object(DEFAULT_SECTION, bytes(obj), align=8)
        doc.add_fixup(STRINGS_REF, enc + 8)
        new.append(enc)
    if not new:
        return
    elems = old + new
    nbuf = doc.append(DEFAULT_SECTION, b"".join(struct.pack(">I", p) for p in elems), align=16)
    doc.copy_words(buf, nbuf, count)
    for k in range(count, len(elems)):
        doc.add_fixup(POINTERS, nbuf + 4 * k)
    doc.set_u32(lst + 0x08, len(elems))
    doc.set_u32(lst + 0x0C, len(elems))
    doc.set_u32(lst + 0x10, 0x80000000 | (4 * len(elems)))
    doc.set_u32(lst + 0x14, nbuf)


if __name__ == "__main__":
    import iga
    a = iga.read(sys.argv[1])
    level = max(a.entries, key=lambda e: len(e.data))
    doc = IgzDoc(level.data)
    for set_name in ("Minion_Loads", "Minion_Loads_Legendary"):
        print(set_name, entries(doc, set_name))
