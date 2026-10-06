"""Find code that assembles a little-endian u16 from bytes at +0x10/+0x11 (figure ID) or +0x1C/+0x1D (variant)
of the same base register, within a few instructions."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

ASM = paths.decomp("build", "SSPP52", "asm")
INSN = re.compile(r"^/\* ([0-9A-F]{8}) [0-9A-F]{8}  [0-9A-F ]{11} \*/\t(\w+\.?) (.*)$")
LBZ = re.compile(r"(r\d+), (0x[0-9a-f]+|\d+)\((r\d+)\)")

pairs = {(0x10, 0x11): "figure ID", (0x1C, 0x1D): "variant"}
seen = set()
for root, _, files in os.walk(ASM):
    for fn in files:
        if "_text" not in fn:
            continue
        lines = open(os.path.join(root, fn), encoding="utf-8", errors="replace").read().splitlines()
        ins = []
        for line in lines:
            m = INSN.match(line)
            if m:
                ins.append((m.group(1), m.group(2), m.group(3)))
        for i, (addr, op, args) in enumerate(ins):
            if op != "lbz":
                continue
            m = LBZ.match(args)
            if not m:
                continue
            off, base = int(m.group(2), 0), m.group(3)
            for (lo, hi), label in pairs.items():
                if off not in (lo, hi):
                    continue
                want = hi if off == lo else lo
                for j in range(i + 1, min(len(ins), i + 4)):
                    m2 = LBZ.match(ins[j][2]) if ins[j][1] == "lbz" else None
                    if m2 and m2.group(3) == base and int(m2.group(2), 0) == want and addr not in seen:
                        seen.add(addr)
                        print(f"{addr} {label}: {op} {args} / {ins[j][1]} {ins[j][2]}  ({fn})")
