"""Look for the table of supported figure IDs: places where several known Spyro's Adventure toy IDs
(Dark Spyro 28, Legendaries 404/416/419/430, items 200-207, adventure packs 300-303) appear close together."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
from find_minions import global_igz  # noqa: E402

PROBES = [28, 404, 416, 419, 430, 200, 207, 300, 303]


def encodings(v):
    return {"u32": struct.pack(">I", v), "u16": struct.pack(">H", v), "f32": struct.pack(">f", float(v)),
            "u16le": struct.pack("<H", v)}


def scan(label, data, window=0x400):
    for kind in ("u32", "u16", "f32", "u16le"):
        hits = {v: [i for i in range(0, len(data) - 4, 2 if kind.startswith("u16") else 4)
                    if data[i:i + len(encodings(v)[kind])] == encodings(v)[kind]] for v in PROBES}
        # positions where at least 5 different probe values occur within one window
        events = sorted((p, v) for v, ps in hits.items() for p in ps)
        best = []
        j = 0
        for i in range(len(events)):
            while events[i][0] - events[j][0] > window:
                j += 1
            vals = {v for _, v in events[j:i + 1]}
            if len(vals) >= 5:
                best.append((events[j][0], sorted(vals)))
        seen = set()
        for start, vals in best:
            key = start // window
            if key in seen:
                continue
            seen.add(key)
            print(f"{label} {kind}: cluster at {start:#x} with {vals}")


if __name__ == "__main__":
    scan("global level", global_igz(paths.ssa("permanent", "global.bld")))
    d = open(paths.ssa_disc("sys", "main.dol"), "rb").read()
    offs = struct.unpack(">18I", d[0:72]); addrs = struct.unpack(">18I", d[72:144]); sizes = struct.unpack(">18I", d[144:216])
    for i in range(18):
        if sizes[i]:
            seg = d[offs[i]:offs[i] + sizes[i]]
            print(f"-- DOL section at {addrs[i]:#x}")
            scan(f"dol@{addrs[i]:#x}", seg, window=0x200)
