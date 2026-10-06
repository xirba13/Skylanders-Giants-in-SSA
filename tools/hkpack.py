"""Read Havok binary packfiles (versions 7 and 9, as used by Spyro's Adventure and Giants on Wii, big-endian).

Layout (hkPackfileHeader, 0x40 bytes): magic 57E0E057 10C0C010, userTag, fileVersion, layoutRules[4],
numSections, contentsSectionIndex, contentsSectionOffset, contentsClassNameSectionIndex,
contentsClassNameSectionOffset, contentsVersion[16], flags, pad. Then numSections section headers of 0x30 bytes:
tag[20], absoluteDataStart, localFixupsOffset, globalFixupsOffset, virtualFixupsOffset, exportsOffset,
importsOffset, endOffset (offsets relative to absoluteDataStart).

Fixups: local (src, dst) pairs inside a section; global (src, dst section, dst) triples; virtual (src, class-name
section, class-name offset) triples, one per object, giving each object's class.
"""
import struct
from dataclasses import dataclass, field

MAGIC = bytes.fromhex("57e0e05710c0c010")


@dataclass
class Section:
    tag: str
    start: int
    local: int
    glob: int
    virtual: int
    exports: int
    imports: int
    end: int
    data: bytes = b""
    local_fixups: list = field(default_factory=list)
    global_fixups: list = field(default_factory=list)
    virtual_fixups: list = field(default_factory=list)


@dataclass
class Packfile:
    version: int
    contents_version: str
    header: bytes
    sections: list
    raw: bytes

    def section(self, tag):
        return next(s for s in self.sections if s.tag == tag)

    def class_name(self, sec_index, off):
        s = self.sections[sec_index]
        return s.data[off:s.data.index(b"\0", off)].decode("latin1")

    def objects(self, tag="__data__"):
        """[(offset in section, class name)] from the virtual fixups, in order."""
        s = self.section(tag)
        return [(src, self.class_name(ci, co)) for src, ci, co in s.virtual_fixups]


def _triples(blob, start, end, n):
    out = []
    for k in range(start, end - 4 * n + 1, 4 * n):  # regions are padded to 16 bytes with 0xFF
        vals = struct.unpack_from(f">{n}I", blob, k)
        if vals[0] == 0xFFFFFFFF:
            continue
        out.append(vals)
    return out


def parse(blob: bytes) -> Packfile:
    if blob[:8] != MAGIC:
        raise ValueError("not a Havok packfile")
    hdr = blob[:0x40]
    version = struct.unpack_from(">I", hdr, 0x0C)[0]
    nsec = struct.unpack_from(">I", hdr, 0x14)[0]
    cv = hdr[0x28:0x38].split(b"\0")[0].decode("latin1")
    secs = []
    for k in range(nsec):
        sh = blob[0x40 + 0x30 * k: 0x40 + 0x30 * (k + 1)]
        tag = sh[:20].split(b"\0")[0].decode("latin1")
        s = Section(tag, *struct.unpack_from(">7I", sh, 0x14))
        base = s.start
        s.data = blob[base:base + s.local]
        s.local_fixups = _triples(blob, base + s.local, base + s.glob, 2)
        s.global_fixups = _triples(blob, base + s.glob, base + s.virtual, 3)
        s.virtual_fixups = _triples(blob, base + s.virtual, base + s.exports, 3)
        secs.append(s)
    return Packfile(version, cv, hdr, secs, blob)


def packfiles_in(blob: bytes):
    """Offsets of packfiles inside a larger blob (an IGZ section)."""
    out, i = [], blob.find(MAGIC)
    while i >= 0:
        out.append(i)
        i = blob.find(MAGIC, i + 8)
    return out


def length(blob: bytes, at: int) -> int:
    """Total size of the packfile starting at `at` (end of its last section)."""
    nsec = struct.unpack_from(">I", blob, at + 0x14)[0]
    end = 0
    for k in range(nsec):
        start = struct.unpack_from(">I", blob, at + 0x40 + 0x30 * k + 0x14)[0]
        end = max(end, start + struct.unpack_from(">I", blob, at + 0x40 + 0x30 * k + 0x2C)[0])
    return end
