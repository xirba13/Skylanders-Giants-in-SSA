"""Look for an array indexed by figure ID: real values at Spyro's Adventure IDs, one filler value elsewhere."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

VALID = [0, 1, 4, 16, 27, 28, 32, 200, 203, 207, 300, 302, 303, 404, 416, 419, 430, 505, 514, 526]
FILLER = [33, 40, 64, 99, 100, 101, 112, 115, 150, 199, 208, 250, 299, 310, 350, 399, 400, 405, 450, 500, 504, 527]
need = max(VALID + FILLER) + 1

d = open(paths.ssa_disc("sys", "main.dol"), "rb").read()
offs = struct.unpack(">18I", d[0:72]); addrs = struct.unpack(">18I", d[72:144]); sizes = struct.unpack(">18I", d[144:216])
fmt = {1: "B", 2: ">H", 4: ">I"}
for i in range(7, 18):
    if not sizes[i]:
        continue
    seg = d[offs[i]:offs[i] + sizes[i]]
    for es in (1, 2, 4):
        f = fmt[es]
        for base in range(0, len(seg) - need * es, es):
            fill = struct.unpack_from(f, seg, base + FILLER[0] * es)[0]
            if any(struct.unpack_from(f, seg, base + k * es)[0] != fill for k in FILLER[1:]):
                continue
            if all(struct.unpack_from(f, seg, base + k * es)[0] != fill for k in VALID):
                vals = [struct.unpack_from(f, seg, base + k * es)[0] for k in VALID]
                print(f"candidate: {addrs[i] + base:#x} element size {es}, filler {fill:#x}, values at IDs {vals}")
print("done")
