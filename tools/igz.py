"""Alchemy IGZ object files: v5 (Spyro's Adventure) and v6 (Giants). Inspection and v6 -> v5 header conversion.

Spyro's Adventure's loader (fn_8011E5E8) checks the magic, requires version >= 5, and requires the word at
offset 8 ("user version") to equal the engine's value, which is 0 in every retail Spyro's Adventure file.
Giants files carry a per-file value there, so converting means rewriting the version and clearing that word.
Object layouts are NOT converted; whether they match between the two engines is what the tests measure.
"""
import struct

MAGIC = b"IGZ\x01"


def header(data: bytes) -> dict:
    if data[:4] != MAGIC:
        raise ValueError("not an IGZ file")
    version, user = struct.unpack_from(">II", data, 4)
    sections = []
    for at in range(0x10, 0x800, 16):
        off, size, align, pool = struct.unpack_from(">IIII", data, at)
        if off == 0:
            break
        sections.append((off, size, align, pool))
    return {"version": version, "user_version": user, "sections": sections}


def records(data: bytes) -> dict:
    """Fixup records of the metadata section (section 0), keyed by tag: (count, body)."""
    off, size = header(data)["sections"][0][:2]
    sec = data[off:off + size]
    out, cur = {}, 0x1C
    while cur + 24 <= len(sec):
        tag, _, _, count, rsize, hdr = struct.unpack_from(">6I", sec, cur)
        if rsize == 0:
            break
        out[tag] = (count, sec[cur + hdr:cur + rsize])
        cur += rsize
    return out


def types(data: bytes) -> list:
    """Object type names used by the file (fixup record 0)."""
    count, body = records(data)[0]
    return [s.decode("latin1") for s in body.split(b"\0") if s][:count]


def type_sizes(data: bytes) -> dict:
    """{type name: object size in bytes}, from record 0 (names) and record 0x0C (one u32 size per name)."""
    recs = records(data)
    names = types(data)
    count, body = recs[0x0C]
    sizes = struct.unpack_from(f">{count}I", body, 0)
    return dict(zip(names, sizes))


def to_v5(data: bytes) -> bytes:
    """Rewrite a v6 header so Spyro's Adventure's loader accepts it. Object data is left untouched."""
    h = header(data)
    if h["version"] not in (5, 6):
        raise ValueError(f"unexpected IGZ version {h['version']}")
    out = bytearray(data)
    struct.pack_into(">II", out, 4, 5, 0)
    meta = h["sections"][0][0]
    if out[meta:meta + 4] == MAGIC:  # the metadata section repeats the magic and version
        struct.pack_into(">I", out, meta + 4, 5)
    return bytes(out)


if __name__ == "__main__":
    import sys
    d = open(sys.argv[1], "rb").read()
    h = header(d)
    print(f"IGZ v{h['version']} user {h['user_version']:#x}, {len(h['sections'])} sections")
    print("types:", types(d))
