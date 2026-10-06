"""Exploration helper: dump the fixup records of an IGZ file so their meaning can be worked out."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import igz  # noqa: E402


def load(path, entry="level.bld"):
    """An IGZ file on disk, or the named entry inside an IGA archive."""
    data = open(path, "rb").read()
    if data[:4] == iga.MAGIC:
        return next(e for e in iga.read(path).entries if e.name == entry).data
    return data


def strings(body, count):
    return [s.decode("latin1") for s in body.split(b"\0") if s][:count]


if __name__ == "__main__":
    data = load(sys.argv[1])
    recs = igz.records(data)
    for tag in sorted(recs):
        count, body = recs[tag]
        head = body[:32].hex()
        print(f"tag {tag:#04x} count {count:6} bytes {len(body):7}  {head}")
    names = strings(recs[0][1], recs[0][0])
    count, body = recs[0xC]
    vals = struct.unpack_from(f">{count}I", body, 0)
    print("tag 0 names with tag 0xC values:")
    for nm, v in list(zip(names, vals))[:30]:
        print(f"   {v:#8x}  {nm}")
