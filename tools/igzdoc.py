"""Editable IGZ document: parse, modify, and write back IGZ object files.

Layout (see docs/FORMATS.md):
  0x000  header: magic, version, user version, then the section table at 0x0C as (pool name offset, file offset,
         size, alignment) entries, then the pool names ("Default", "String", "Image", ...). Section 0 is metadata.
  0x800  metadata section: a 0x1C-byte header, then fixup records (tag, ?, ?, count, size, header size) + body.
  then   object sections, back to back with no padding in the file.

Encoded offsets (object fields and fixup lists) are (object section << 24) | offset, where object section 0 is
file section 1. Appending data at the end of a section never moves existing data, so existing pointers stay valid.
"""
import bisect
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from igzobj import unpack_offsets  # noqa: E402

MAGIC = b"IGZ\x01"
HEADER_SIZE = 0x800
POOL_NAMES = 0x56C  # pool name table inside the header; section entries hold offsets into it
EMPTY = 0xFFFFFFFF  # v6 marks an empty section with this size; it still occupies 4 bytes in the file
PACKED = (0x05, 0x06, 0x07, 0x0B, 0x0E, 0x0F, 0x10)
OBJECTS, POINTERS, STRINGS_REF = 0x05, 0x06, 0x0E
TYPE_NAMES, TYPE_SIZES = 0x00, 0x0C


def pack_offsets(offsets) -> bytes:
    """Inverse of unpack_offsets: sorted encoded offsets -> nibble varints, padded to 4 bytes."""
    nibbles, prev = [], 0
    for off in offsets:
        delta = off - prev - 4
        if delta < 0 or delta % 4:
            raise ValueError(f"offset {off:#x} cannot follow {prev:#x}")
        v = delta // 4
        while True:
            nib = v & 7
            v >>= 3
            nibbles.append(nib | (8 if v else 0))
            if not v:
                break
        prev = off
    out = bytearray((len(nibbles) + 1) // 2)
    for i, nib in enumerate(nibbles):
        out[i >> 1] |= nib << (4 * (i & 1))
    out += bytes(-len(out) % 4)
    return bytes(out)


def pack_strings(names) -> bytes:
    """String records: NUL-terminated names back to back, the whole body padded to 4 bytes."""
    out = b"".join(n.encode("latin1") + b"\0" for n in names)
    return out + bytes(-len(out) % 4)


class Record:
    def __init__(self, words, body):
        self.words = list(words)  # full header words (tag, a, b, count, size, header size, extra...)
        self.body = body

    @property
    def tag(self):
        return self.words[0]

    @property
    def count(self):
        return self.words[3]


class IgzDoc:
    def __init__(self, data: bytes):
        if data[:4] != MAGIC:
            raise ValueError("not an IGZ file")
        self.header = bytearray(data[:HEADER_SIZE])
        self.sections = []  # (pool, offset, size, align)
        at = 0x0C
        while True:
            pool, off, size, align = struct.unpack_from(">IIII", data, at)
            if off == 0:
                break
            self.sections.append([pool, off, size, align])
            at += 16
        meta_off, meta_size = self.sections[0][1], self.sections[0][2]
        meta = data[meta_off:meta_off + meta_size]
        self.meta_header = meta[:0x1C]
        self.records = []
        cur = 0x1C
        while cur + 24 <= len(meta):
            tag, a, b, count, size, hdr = struct.unpack_from(">6I", meta, cur)
            if size == 0:
                break
            words = struct.unpack_from(f">{hdr // 4}I", meta, cur)
            self.records.append(Record(words, meta[cur + hdr:cur + size]))
            cur += size
        self.meta_tail = meta[cur:]
        self.empty = [s[2] == EMPTY for s in self.sections]
        self.blobs = []
        for i, s in enumerate(self.sections[1:], 1):
            if self.empty[i]:
                end = self.sections[i + 1][1] if i + 1 < len(self.sections) else len(data)
                self.blobs.append(bytearray(data[s[1]:end]))  # placeholder bytes, kept verbatim
            else:
                self.blobs.append(bytearray(data[s[1]:s[1] + s[2]]))
        self.tail = data[self.sections[-1][1] + len(self.blobs[-1]):] if len(self.sections) > 1 else b""
        self.lists = {r.tag: unpack_offsets(r.body, r.count) for r in self.records if r.tag in PACKED}
        rec = self.record(TYPE_NAMES)
        self.types = [s.decode("latin1") for s in rec.body.split(b"\0") if s][:rec.count]
        sizes = self.record(TYPE_SIZES)
        self.type_sizes = list(struct.unpack_from(f">{sizes.count}I", sizes.body, 0))
        self._packed_dirty = set()
        self._types_dirty = False

    # ----- access -----
    def record(self, tag):
        return next(r for r in self.records if r.tag == tag)

    def u32(self, enc):
        sec, off = enc >> 24, enc & 0xFFFFFF
        return struct.unpack_from(">I", self.blobs[sec], off)[0]

    def set_u32(self, enc, value):
        sec, off = enc >> 24, enc & 0xFFFFFF
        struct.pack_into(">I", self.blobs[sec], off, value)

    def read(self, enc, n):
        sec, off = enc >> 24, enc & 0xFFFFFF
        return bytes(self.blobs[sec][off:off + n])

    def cstr(self, enc):
        sec, off = enc >> 24, enc & 0xFFFFFF
        b = self.blobs[sec]
        return b[off:b.index(b"\0", off)].decode("latin1")

    def pool_name(self, section):
        p = POOL_NAMES + self.sections[section][0]
        return self.header[p:self.header.index(b"\0", p)].decode()

    def section_by_pool(self, name):
        """Object section index (0 = first section after metadata) whose pool is called name."""
        for i in range(1, len(self.sections)):
            if self.pool_name(i) == name and not self.empty[i]:
                return i - 1
        raise KeyError(name)

    # ----- editing -----
    def append(self, sec, data: bytes, align: int = 4) -> int:
        """Append raw bytes to object section sec; returns their encoded offset."""
        blob = self.blobs[sec]
        blob += bytes(-len(blob) % align)
        off = len(blob)
        if off >= 1 << 24:
            raise ValueError("section too large for 24-bit offsets")
        blob += data
        return (sec << 24) | off

    def add_fixup(self, tag, enc):
        lst = self.lists[tag]
        i = bisect.bisect_left(lst, enc)
        if i < len(lst) and lst[i] == enc:
            return
        lst.insert(i, enc)
        self._packed_dirty.add(tag)

    def tags_at(self, enc):
        """Fixup tags, other than the object list, that cover the word at enc (pointer, handle, string, ...)."""
        out = []
        for tag, lst in self.lists.items():
            if tag == OBJECTS:
                continue
            i = bisect.bisect_left(lst, enc)
            if i < len(lst) and lst[i] == enc:
                out.append(tag)
        return out

    def copy_words(self, src, dst, count):
        """Give the count words at dst the same fixups as the words at src (their values are copied by the caller).
        A list buffer can mix pointers and import handles (global.bld's root list does), so this must not assume
        every element is a pointer."""
        for k in range(count):
            for tag in self.tags_at(src + 4 * k):
                self.add_fixup(tag, dst + 4 * k)

    def check(self):
        """Offline sanity check of the fixups: pointers decode to a place inside an object section, handles name an
        existing import, string references point into the String section, class numbers name an existing named
        reference (record 3; true of all 4.8 million in both games' 738 level files). Returns a list of problems."""
        problems = []
        sizes = [len(b) for b in self.blobs]
        imports = next((r.count for r in self.records if r.tag == 0x02), 0)
        refs = next((r.count for r in self.records if r.tag == 0x03), 0)
        for enc in self.lists.get(0x10, ()):
            v = self.u32(enc)
            if (v & 0x7FFFFFFF) >= refs:
                problems.append(f"class number at {enc:#x} = {v:#x} ({refs} named references)")
        try:
            strings = self.section_by_pool("String")
        except KeyError:
            strings = None
        for enc in self.lists.get(POINTERS, ()):
            v = self.u32(enc)
            if v and ((v >> 24) >= len(sizes) or (v & 0xFFFFFF) > sizes[v >> 24]):
                problems.append(f"pointer at {enc:#x} = {v:#x}")
        for enc in self.lists.get(0x07, ()):
            v = self.u32(enc)
            if not v & 0x80000000 or (v & 0x7FFFFFFF) >= imports:
                problems.append(f"handle at {enc:#x} = {v:#x} ({imports} imports)")
        for enc in self.lists.get(STRINGS_REF, ()):
            v = self.u32(enc)
            if strings is None or v >> 24 != strings or (v & 0xFFFFFF) >= sizes[strings]:
                problems.append(f"string ref at {enc:#x} = {v:#x}")
        both = set(self.lists.get(POINTERS, ())) & set(self.lists.get(0x07, ()))
        problems += [f"word at {enc:#x} is both pointer and handle" for enc in sorted(both)]
        return problems

    def insert_bytes(self, sec, offset, length):
        """Insert `length` zero bytes into object section `sec` at `offset`, moving everything after it: fixup
        locations, pointer values, data-block records and the root. length should be a multiple of 16 so that
        objects keep their alignment. Returns the encoded address of the gap."""
        if length % 16:
            raise ValueError("insert a multiple of 16 bytes")
        blob = self.blobs[sec]
        blob[offset:offset] = bytes(length)

        def moved(enc):
            if enc >> 24 == sec and (enc & 0xFFFFFF) >= offset:
                return enc + length
            return enc
        for tag, lst in self.lists.items():
            self.lists[tag] = [moved(e) for e in lst]
            self._packed_dirty.add(tag)
        for p in self.lists.get(POINTERS, ()):
            v = self.u32(p)
            if v:
                self.set_u32(p, moved(v))
        for r in self.records:
            if r.tag == 0x0A:
                body = bytearray(r.body)
                for k in range(r.count):
                    size, enc = struct.unpack_from(">II", body, 8 * k)
                    struct.pack_into(">II", body, 8 * k, size, moved(enc))
                r.body = bytes(body)
            elif r.tag == 0x08:
                (root,) = struct.unpack_from(">I", r.body, 0)
                r.body = struct.pack(">I", moved(root)) + r.body[4:]
        return (sec << 24) | offset

    def add_string(self, text: str) -> int:
        return self.append(self.section_by_pool("String"), text.encode("latin1") + b"\0", align=2)

    def type_index(self, name):
        return self.types.index(name)

    def add_object(self, sec, data: bytes, align: int = 16) -> int:
        """Append an object (its first word must already hold its type index); registers it in the object list."""
        enc = self.append(sec, data, align)
        self.add_fixup(OBJECTS, enc)
        return enc

    # ----- writing -----
    def to_bytes(self) -> bytes:
        # Reference counts (+0x04) are derived from the pointer graph like the packed fixup lists below, so edits
        # do not track them: they are recounted here (no change for a retail file, see refcounts.py).
        import refcounts
        self.recounted = refcounts.recount(self)
        meta = bytearray(self.meta_header)
        for r in self.records:
            body = r.body
            if r.tag in self._packed_dirty:
                body = pack_offsets(self.lists[r.tag])
                r.words[3] = len(self.lists[r.tag])
            elif r.tag == TYPE_NAMES and self._types_dirty:
                body = pack_strings(self.types)
                r.words[3] = len(self.types)
            elif r.tag == TYPE_SIZES and self._types_dirty:
                body = struct.pack(f">{len(self.type_sizes)}I", *self.type_sizes)
                r.words[3] = len(self.type_sizes)
            hdr = 4 * len(r.words)
            r.words[4] = hdr + len(body)
            r.words[5] = hdr
            meta += struct.pack(f">{len(r.words)}I", *r.words) + body
            r.body = body
        meta += self.meta_tail
        self._packed_dirty.clear()
        self._types_dirty = False
        out = bytearray(self.header)
        lengths = [len(meta)] + [len(b) for b in self.blobs]
        pos = HEADER_SIZE
        for i, length in enumerate(lengths):
            size = EMPTY if self.empty[i] else length
            struct.pack_into(">II", out, 0x10 + 16 * i, pos, size)
            self.sections[i][1:3] = [pos, size]
            pos += length
        return bytes(out) + bytes(meta) + b"".join(bytes(b) for b in self.blobs) + self.tail
