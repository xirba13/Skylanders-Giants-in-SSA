"""Convert Giants Havok packfiles (hk_2011.2.0-r1, file version 9) to Spyro's Adventure's (Havok-7.1.0-r1, v7).

Verified layouts (tools/hk_dump.py on Spyro, who exists in both games):
  hkRootLevelContainer, hkaAnimationContainer, hkaAnimationBinding, hkaSplineCompressedAnimation: identical,
  except hkaAnimation::type, 3 (HK_SPLINE_COMPRESSED_ANIMATION in 2011) -> 5 (in 7.1).
  hkaSkeleton: 2011 adds referenceFloats (an hkArray, +0x30) before floatSlots and localFrames.
Spyro's Adventure packfiles carry an extra "Resource Data" hkMemoryResourceContainer; it is not added here.

The output reuses a Spyro's Adventure packfile's header and __classnames__ section (the class signatures its
Havok checks); objects point at the class names of the same classes there.
"""
import struct

import hkpack

TYPE_SPLINE_2011, TYPE_SPLINE_71 = 3, 5


def _pad16(b: bytes, fill=b"\0") -> bytes:
    return b + fill * (-len(b) % 16)


def _fixups(rows, n) -> bytes:
    out = b"".join(struct.pack(f">{n}I", *r) for r in rows)
    return out + b"\xff" * (-len(out) % 16)


def class_offsets(template: hkpack.Packfile) -> dict:
    """Class name -> offset of the name in the template's __classnames__ section."""
    data = template.section("__classnames__").data
    out, i = {}, 0
    while i + 5 <= len(data):
        if data[i + 4] != 0x09:
            break
        end = data.index(b"\0", i + 5)
        out[data[i + 5:end].decode("latin1")] = i + 5
        i = end + 1
    return out


def write(template: hkpack.Packfile, data: bytes, local, glob, virtual) -> bytes:
    """A version-7 packfile: template header and class names, the given __data__ and fixups."""
    names = _pad16(template.section("__classnames__").data, b"\xff")
    head = 0x40 + 0x30 * 3
    data_start = head + len(names)
    body = _pad16(data)
    lo = _fixups(sorted(local), 2)
    gl = _fixups(sorted(glob), 3)
    vi = _fixups(virtual, 3)
    rel = [len(body), len(body) + len(lo), len(body) + len(lo) + len(gl)]
    end = rel[2] + len(vi)
    sections = [
        ("__classnames__", head, [len(names)] * 6),
        ("__types__", data_start, [0] * 6),
        ("__data__", data_start, rel + [end, end, end]),
    ]
    out = bytearray(template.header)
    for tag, start, offs in sections:
        out += tag.encode().ljust(19, b"\0") + b"\xff" + struct.pack(">7I", start, *offs)
    out += names + body + lo + gl + vi
    return bytes(out)


def convert(blob: bytes, template: hkpack.Packfile) -> bytes:
    """Convert one Giants packfile (animation or skeleton) to version 7."""
    pf = hkpack.parse(blob)
    if pf.version == 7:
        return blob
    if pf.version != 9:
        raise ValueError(f"unexpected packfile version {pf.version}")
    s = pf.section("__data__")
    data = bytearray(s.data)
    local = {src: dst for src, dst in s.local_fixups}
    glob = {src: (sec, dst) for src, sec, dst in s.global_fixups}
    names = class_offsets(template)
    virtual = []
    for off, cls in pf.objects():
        if cls not in names:
            raise ValueError(f"class {cls} is not in the template packfile")
        virtual.append((off, 0, names[cls]))
        if cls == "hkaSplineCompressedAnimation":
            t = struct.unpack_from(">I", data, off + 8)[0]
            if t != TYPE_SPLINE_2011:
                raise ValueError(f"spline animation type {t}")
            struct.pack_into(">I", data, off + 8, TYPE_SPLINE_71)
        elif cls == "hkaSkeleton":
            _skeleton_in_place(data, off, local, glob)
    return write(template, bytes(data), [(a, b) for a, b in local.items()],
                 [(a, sec, b) for a, (sec, b) in glob.items()], virtual)


def _skeleton_in_place(data, off, local, glob):
    """hkaSkeleton 2011 -> 7.1: drop referenceFloats (+0x30, must be empty), move floatSlots (+0x3C) and
    localFrames (+0x48) to +0x30 and +0x3C, zero the freed words. The object keeps its place, so the arrays
    that follow it do not move."""
    rf = struct.unpack_from(">III", data, off + 0x30)
    if rf[1] != 0 or (off + 0x30) in local or (off + 0x30) in glob:
        raise ValueError("skeleton has reference floats")
    for new, old in ((0x30, 0x3C), (0x3C, 0x48)):
        for k in range(0, 12, 4):
            data[off + new + k:off + new + k + 4] = data[off + old + k:off + old + k + 4]
            for table in (local, glob):
                if off + old + k in table:
                    table[off + new + k] = table.pop(off + old + k)
    data[off + 0x48:off + 0x54] = bytes(12)
