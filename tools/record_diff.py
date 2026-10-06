"""Exploration helper: which records re-encode differently, and how."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
from igzdoc import IgzDoc, pack_offsets, pack_strings, PACKED  # noqa: E402

path, name = sys.argv[1], sys.argv[2]
data = next(e.data for e in iga.read(path).entries if e.name == name)
doc = IgzDoc(data)
print("header words:", [hex(x) for x in struct.unpack_from(">8I", data, 0)])
print("meta header:", doc.meta_header.hex(), "meta tail:", len(doc.meta_tail), doc.meta_tail[:16].hex())
for r in doc.records:
    if r.tag in PACKED:
        new = pack_offsets(doc.lists[r.tag])
    elif r.tag == 0:
        new = pack_strings(doc.types)
    elif r.tag == 0x0C:
        new = struct.pack(f">{len(doc.type_sizes)}I", *doc.type_sizes)
    else:
        continue
    if new != r.body:
        n = next((i for i in range(min(len(new), len(r.body))) if new[i] != r.body[i]), None)
        print(f"tag {r.tag:#04x}: original {len(r.body)} bytes, ours {len(new)}; first diff at {n}; "
              f"orig {r.body[max(0,(n or 0)-8):(n or 0)+16].hex()} ours {new[max(0,(n or 0)-8):(n or 0)+16].hex()}")
as_is = doc.to_bytes()
if as_is != data:
    n = next((i for i in range(min(len(as_is), len(data))) if as_is[i] != data[i]), None)
    print(f"as-is: len {len(as_is)} vs {len(data)}, first diff {n}: orig {data[n:n+16].hex() if n is not None else ''} ours {as_is[n:n+16].hex() if n is not None else ''}")
