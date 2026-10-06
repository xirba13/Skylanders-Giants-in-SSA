"""Find code in the decomp's generated assembly that loads the address of a given string from main.dol."""
import bisect
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

DOL = paths.ssa_disc("sys", "main.dol")
ASM = paths.decomp("build", "SSPP52", "asm")
SYMBOLS = paths.decomp("config", "SSPP52", "symbols.txt")


def dol_find(needle: bytes):
    d = open(DOL, "rb").read()
    offs = struct.unpack(">18I", d[0:72]); addrs = struct.unpack(">18I", d[72:144]); sizes = struct.unpack(">18I", d[144:216])
    out = []
    for i in range(7, 18):
        seg = d[offs[i]:offs[i] + sizes[i]]
        for m in re.finditer(re.escape(needle), seg):
            if m.start() == 0 or seg[m.start() - 1] == 0:
                out.append(addrs[i] + m.start())
    return out


def symbols():
    syms = []
    for line in open(SYMBOLS):
        m = re.match(r"(\S+) = \.\w+:0x([0-9A-F]+);", line)
        if m:
            syms.append((int(m.group(2), 16), m.group(1)))
    syms.sort()
    return syms


if __name__ == "__main__":
    needle = sys.argv[1].encode() + b"\0"
    syms = symbols()
    starts = [a for a, _ in syms]
    for addr in dol_find(needle):
        i = bisect.bisect_right(starts, addr) - 1
        base, name = syms[i]
        off = addr - base
        print(f"'{sys.argv[1]}' at {addr:#x} = {name} + {off:#x}")
        pat = re.compile(rf"addi (r\d+), \1, {re.escape(name)}@l")
        seen = set()
        for root, _, files in os.walk(ASM):
            for fn in files:
                lines = open(os.path.join(root, fn), encoding="utf-8", errors="replace").read().splitlines()
                for k, line in enumerate(lines):
                    if f"{name}@l" not in line and f"{name}@sda21" not in line:
                        continue
                    window = " ".join(lines[k:k + 4])
                    if off == 0 or f"0x{off:x}" in window:
                        m = re.match(r"/\* ([0-9A-F]{8})", line)
                        if m and m.group(1) not in seen:
                            seen.add(m.group(1))
                            print(f"   used at {m.group(1)} ({fn})")
