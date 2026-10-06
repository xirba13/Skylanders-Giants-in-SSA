"""IGZ object model (read side): objects, their types and sizes, and the reference fixup lists.

Packed fixup records hold offsets as nibble varints (3 data bits + continuation bit, low nibble first); each value
is a delta, applied as delta * 4 + 4. An offset is (object section << 24) | offset, where object section 0 is the
section after the metadata section. Record 5 lists every object; an object's first word is its type index into
record 0, and record 0x0C gives each type's size. Verified on Spyro's Adventure (v5) and Giants (v6) files.
"""
import bisect
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import igz  # noqa: E402

OBJECT_LIST = 0x05
PACKED = (0x05, 0x06, 0x07, 0x0B, 0x0E, 0x0F, 0x10)


def unpack_offsets(body: bytes, count: int) -> list:
    out, pos, prev = [], 0, 0
    for _ in range(count):
        value, shift = 0, 0
        while True:
            b = body[pos >> 1]
            nib = (b & 0xF) if (pos & 1) == 0 else (b >> 4)
            pos += 1
            value |= (nib & 7) << shift
            shift += 3
            if not nib & 8:
                break
        prev += value * 4 + 4
        out.append(prev)
    return out


class IgzFile:
    def __init__(self, data: bytes):
        self.data = data
        self.header = igz.header(data)
        self.sections = self.header["sections"]
        self.records = igz.records(data)
        self.types = igz.types(data)
        self.sizes = igz.type_sizes(data)
        self.fixups = {t: unpack_offsets(self.records[t][1], self.records[t][0]) for t in PACKED if t in self.records}
        self.objects = []  # (file position, encoded offset, type name, size)
        for enc in self.fixups[OBJECT_LIST]:
            p = self.pos(enc)
            t = self.types[self.u32(p)]
            self.objects.append((p, enc, t, self.sizes[t]))
        self.objects.sort()
        self._starts = [o[0] for o in self.objects]

    def pos(self, enc: int):
        """File position of an encoded offset (None if it does not fall inside its section)."""
        sec, off = enc >> 24, enc & 0xFFFFFF
        if sec + 1 >= len(self.sections):
            return None
        start, size = self.sections[sec + 1][:2]
        return start + off if off < size else None

    def enc(self, pos: int):
        for i, (start, size, _, _) in enumerate(self.sections[1:]):
            if start <= pos < start + size:
                return (i << 24) | (pos - start)
        return None

    def u32(self, p: int) -> int:
        return struct.unpack_from(">I", self.data, p)[0]

    def object_at(self, p: int):
        """The object whose [start, start + size) contains file position p, if any."""
        i = bisect.bisect_right(self._starts, p) - 1
        if i >= 0:
            o = self.objects[i]
            if o[0] <= p < o[0] + o[3]:
                return o
        return None

    def cstr(self, p: int) -> str:
        return self.data[p:self.data.index(b"\0", p)].decode("latin1")
