"""List the functions that reference a data label (e.g. a string pool), with the pool offsets they use nearby.

usage: python tools/pool_users.py lbl_8042BB38
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

ASM = paths.decomp("build", "SSPP52", "asm")
INSN = re.compile(r"^/\* ([0-9A-F]{8}) [0-9A-F]{8}  [0-9A-F ]{11} \*/\t(.*)$")

label = sys.argv[1]
funcs = {}
for root, _, files in os.walk(ASM):
    for fn in sorted(files):
        if "_text" not in fn:
            continue
        cur, lines = None, []
        for line in open(os.path.join(root, fn), encoding="utf-8", errors="replace"):
            if line.startswith(".fn "):
                cur = line.split()[1].rstrip(",")
                lines = []
            m = INSN.match(line)
            if m and cur:
                lines.append((m.group(1), m.group(2)))
                if f"{label}@l" in m.group(2):
                    funcs.setdefault(cur, set()).add(m.group(1))
            if line.startswith(".endfn") and cur in funcs and cur not in getattr(sys.modules[__name__], "_done", set()):
                # collect small immediates added to registers in this function (likely pool offsets)
                offs = set()
                for _, ins in lines:
                    mm = re.match(r"addi r\d+, r\d+, (0x[0-9a-f]+)$", ins)
                    if mm and 0x10 <= int(mm.group(1), 16) < 0x1000:
                        offs.add(int(mm.group(1), 16))
                funcs[cur] = (funcs[cur], offs) if isinstance(funcs[cur], set) else funcs[cur]
for f, v in sorted(funcs.items()):
    addrs, offs = v if isinstance(v, tuple) else (v, set())
    print(f"{f:16} uses at {sorted(addrs)[:2]}  offsets {sorted(hex(o) for o in offs)[:20]}")
