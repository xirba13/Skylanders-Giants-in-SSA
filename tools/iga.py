"""Skylanders IGA archives: read v4 (Spyro's Adventure) and v8 (Giants), write v4.

Layout notes are in docs/FORMATS.md. The writer stores every entry uncompressed (flags 0xFFFFFFFF),
the same way the retail .arc archives store their files, so no LZMA encoder is involved.
"""
import lzma
import struct
from dataclasses import dataclass

MAGIC = b"IGA\x1a"
SECTOR = 0x800
BLOCK = 0x8000
RAW = 0xFFFFFFFF


def fnv1a(data: bytes, h: int = 0x811C9DC5) -> int:
    """32-bit FNV-1a, as computed by fn_80125B4C. Retail .bld entry names hash this way (case-sensitive)."""
    for c in data:
        h = ((h ^ c) * 0x01000193) & 0xFFFFFFFF
    return h


def _align(n: int, a: int = SECTOR) -> int:
    return (n + a - 1) & ~(a - 1)


@dataclass
class Entry:
    name: str
    hash: int
    data: bytes
    offset: int = 0  # data offset in the source archive; used to keep the original data order


@dataclass
class Archive:
    version: int
    entries: list  # hash order, as stored


def _layout(ver: int):
    """(hash table offset, offset of the name-table offset/size pair) per archive version."""
    if ver == 4:
        return 0x30, 0x18
    if ver == 8:
        return 0x34, 0x1C
    raise ValueError(f"unsupported IGA version {ver}")


def _lzma_block(d: bytes, at: int, want: int, ver: int) -> bytes:
    # block = [u16 compressed size (big-endian in v4, little-endian in v8)][5-byte LZMA props][payload]
    size = struct.unpack_from(">H" if ver == 4 else "<H", d, at)[0]
    props = d[at + 2]
    lc, rem = props % 9, props // 9
    lp, pb = rem % 5, rem // 5
    dict_size = struct.unpack_from("<I", d, at + 3)[0]
    dec = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[
        {"id": lzma.FILTER_LZMA1, "lc": lc, "lp": lp, "pb": pb, "dict_size": dict_size}])
    out = dec.decompress(d[at + 7:at + 7 + size], max_length=want)
    if len(out) != want:
        raise lzma.LZMAError(f"block at {at:#x}: {len(out)} of {want} bytes")
    return out


SMALL = 127 * SECTOR  # entries up to this size list their blocks in the u8 table, bigger ones in the u16 table


def _tables(d: bytes, ver: int, n: int, ents_at: int):
    """The two block tables that follow the entries: u16 values (bit 15 = compressed) and u8 values (bit 7)."""
    n16, n8 = struct.unpack_from("<II", d, 0x24 if ver == 4 else 0x28)
    at = ents_at + 12 * n
    return struct.unpack_from(f"<{n16}H", d, at), d[at + 2 * n16:at + 2 * n16 + n8]


def _extract(d: bytes, ver: int, off: int, size: int, flags: int, t16, t8) -> bytes:
    if flags == RAW or (flags >> 28) == 0:
        return d[off:off + size]
    # each entry lists the sector offset (from its start) of every block, then an end offset
    nblocks = (size + BLOCK - 1) // BLOCK
    idx = flags & 0xFFFFFF
    if size <= SMALL:
        vals, bit = t8[idx:idx + nblocks], 0x80
    else:
        vals, bit = t16[idx:idx + nblocks], 0x8000
    out = bytearray()
    for v in vals:
        want = min(BLOCK, size - len(out))
        at = off + (v & (bit - 1)) * SECTOR
        out += _lzma_block(d, at, want, ver) if v & bit else d[at:at + want]
    return bytes(out)


def read(path) -> Archive:
    with open(path, "rb") as f:
        d = f.read()
    if d[:4] != MAGIC:
        raise ValueError(f"{path}: not an IGA archive")
    ver, _, n = struct.unpack_from("<III", d, 4)
    hash_at, nt_field = _layout(ver)
    hashes = struct.unpack_from(f"<{n}I", d, hash_at)
    ents_at = hash_at + 4 * n
    raw = [struct.unpack_from("<III", d, ents_at + 12 * i) for i in range(n)]
    t16, t8 = _tables(d, ver, n, ents_at)
    nt_off, nt_size = struct.unpack_from("<II", d, nt_field)
    nt = d[nt_off:nt_off + nt_size]
    # name table: n u32 offsets (relative to the table), then NUL-terminated names (v8 adds 4 bytes after each)
    name_offs = struct.unpack_from(f"<{n}I", nt, 0)
    names = [nt[o:nt.index(b"\0", o)].decode("latin1") for o in name_offs]
    entries = [Entry(names[i], hashes[i], _extract(d, ver, off, size, flags, t16, t8), off)
               for i, (off, size, flags) in enumerate(raw)]
    return Archive(ver, entries)


def _compress(data: bytes):
    """Split into 0x8000 blocks; returns (stored bytes, [sector offsets with compressed flag], end sector, small)."""
    small = len(data) <= SMALL
    bit = 0x80 if small else 0x8000
    out, vals = bytearray(), []
    for i in range(0, max(len(data), 1), BLOCK):
        raw = data[i:i + BLOCK]
        payload = lzma.compress(raw, format=lzma.FORMAT_RAW, filters=[
            {"id": lzma.FILTER_LZMA1, "lc": 3, "lp": 0, "pb": 2, "dict_size": 0x8000}])
        sector = len(out) // SECTOR
        if 7 + len(payload) < len(raw):
            out += struct.pack(">H", len(payload)) + bytes([0x5D]) + struct.pack("<I", 0x8000) + payload
            vals.append(sector | bit)
        else:
            out += raw
            vals.append(sector)
        out += bytes(-len(out) % SECTOR)
    return bytes(out), vals, len(out) // SECTOR, small


def search_window(hashes):
    """(divider, slop) of a v4 header (0x10, 0x14) for the sorted hashes. The engine looks a name up only among
    the entries within slop of position hash // divider (fn_800F0F94), so slop is the largest distance of an
    entry from its guessed position, as in all 278 retail archives. floor(log2 n), which it was before test 38,
    left entries of six Giants' .arc unreachable: pictures, Swarm's portal voice and other voice lines."""
    divider = 0xFFFFFFFF // max(len(hashes), 1)
    return divider, max((abs(k - h // divider) for k, h in enumerate(hashes)), default=0)


def write_v4(entries, path, keep_order: bool = True, compress: bool = False) -> None:
    """Write a v4 archive. Entries are stored raw (flags 0xFFFFFFFF), or LZMA-compressed in 0x8000-byte blocks
    like the retail .bld archives. keep_order lays data out in source-offset order."""
    entries = sorted(entries, key=lambda e: e.hash)
    hashes = [e.hash for e in entries]
    if len(set(hashes)) != len(hashes):
        raise ValueError("duplicate name hashes")
    n = len(entries)
    stored, flags, t16, t8 = [], [], [], bytearray()
    for e in entries:
        if not compress:
            stored.append(e.data)
            flags.append(RAW)
            continue
        blob, vals, end, small = _compress(e.data)
        stored.append(blob)
        if small:
            flags.append(0x10000000 | len(t8))
            t8 += bytes(vals + [end])
        else:
            flags.append(0x10000000 | len(t16))
            t16 += vals + [end]
    toc = 16 * n + 2 * len(t16) + len(t8)
    order = sorted(range(n), key=lambda i: entries[i].offset) if keep_order else list(range(n))
    offsets = [0] * n
    pos = _align(0x30 + toc)
    for i in order:
        offsets[i] = pos
        pos = _align(pos + len(stored[i]))
    nt_off = pos
    blobs = [e.name.encode("latin1") + b"\0" for e in entries]
    name_offs, o = [], 4 * n
    for b in blobs:
        name_offs.append(o)
        o += len(b)
    nt = struct.pack(f"<{n}I", *name_offs) + b"".join(blobs)

    out = bytearray(nt_off + len(nt))
    divider, slop = search_window(hashes)
    struct.pack_into("<4sIIIIIIIIIII", out, 0, MAGIC, 4, toc, n, divider,
                     slop, nt_off, len(nt), 0, len(t16), len(t8), 0)
    struct.pack_into(f"<{n}I", out, 0x30, *hashes)
    ents_at = 0x30 + 4 * n
    for i, e in enumerate(entries):
        struct.pack_into("<III", out, ents_at + 12 * i, offsets[i], len(e.data), flags[i])
        out[offsets[i]:offsets[i] + len(stored[i])] = stored[i]
    struct.pack_into(f"<{len(t16)}H", out, ents_at + 12 * n, *t16)
    out[ents_at + 12 * n + 2 * len(t16):ents_at + 12 * n + 2 * len(t16) + len(t8)] = t8
    out[nt_off:] = nt
    with open(path, "wb") as f:
        f.write(out)


if __name__ == "__main__":
    import sys
    a = read(sys.argv[1])
    print(f"IGA v{a.version}, {len(a.entries)} entries")
    for e in a.entries:
        kind = e.data[:4].decode("latin1") if e.data[:4].isascii() else e.data[:4].hex()
        print(f"  {e.hash:08x} {len(e.data):9} {kind!r:10} {e.name}")
