"""Find script objects whose fields hold given numbers (int or float), and what references them."""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import paths  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402

NUMBERS = [100, 200, 300, 400]
TARGETS = {}
for n in NUMBERS:
    TARGETS[n] = n
    TARGETS[struct.unpack(">I", struct.pack(">f", float(n)))[0]] = n

a = iga.read(paths.ssa("permanent", "global.bld"))
doc = IgzDoc(max(a.entries, key=lambda e: len(e.data)).data)
pointer_fields = set(doc.lists[0x06]) | set(doc.lists[0x0E])
objs = sorted((enc, doc.types[doc.u32(enc)], doc.type_sizes[doc.u32(enc)]) for enc in doc.lists[0x05])
starts = [o[0] for o in objs]

# reverse references: target object -> referencing objects
import bisect
def owner(field):
    i = bisect.bisect_right(starts, field) - 1
    if i >= 0 and objs[i][0] <= field < objs[i][0] + objs[i][2]:
        return objs[i]
    return None

refs = collections.defaultdict(list)
for f in doc.lists[0x06]:
    tgt = doc.u32(f)
    o = owner(f)
    if o:
        refs[tgt].append(o)

found = collections.Counter()
examples = collections.defaultdict(list)
for enc, t, size in objs:
    for k in range(1, size // 4):
        f = enc + 4 * k
        if f in pointer_fields:
            continue
        v = doc.u32(f)
        if v in TARGETS:
            key = (t, k * 4, TARGETS[v], "f32" if v > 0xFFFF else "int")
            found[key] += 1
            if len(examples[key]) < 3:
                examples[key].append(enc)
for key, n in sorted(found.items(), key=lambda kv: -kv[1])[:25]:
    t, off, num, kind = key
    users = collections.Counter(r[1] for e in examples[key] for r in refs.get(e, []))
    print(f"{n:5}x {t:24} +{off:#04x} = {num} ({kind})  referenced by {dict(users)}")
