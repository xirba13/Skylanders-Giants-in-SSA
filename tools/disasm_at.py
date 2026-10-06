"""Print the decomp's generated disassembly around an address, or a whole function.

usage: python tools/disasm_at.py ADDR [--before N] [--after N] [--function]
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

ASM = paths.decomp("build", "SSPP52", "asm")
LINE = re.compile(r"^/\* ([0-9A-F]{8}) [0-9A-F]{8}  [0-9A-F ]{11} \*/\t(.*)$")


def find(addr: int):
    tag = f"/* {addr:08X} "
    for root, _, files in os.walk(ASM):
        for fn in sorted(files):
            path = os.path.join(root, fn)
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
            for i, line in enumerate(lines):
                if line.startswith(tag):
                    return path, lines, i
    return None, None, None


def clean(line):
    m = LINE.match(line)
    return f"{m.group(1)}  {m.group(2)}" if m else line


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("addr")
    ap.add_argument("--before", type=int, default=20)
    ap.add_argument("--after", type=int, default=20)
    ap.add_argument("--function", action="store_true", help="print the whole enclosing function")
    a = ap.parse_args()
    addr = int(a.addr, 16) & ~3
    path, lines, i = find(addr)
    if path is None:
        raise SystemExit(f"{addr:#x} not found")
    if a.function:
        s = max(k for k in range(i + 1) if lines[k].startswith(".fn "))
        e = next(k for k in range(i, len(lines)) if lines[k].startswith(".endfn"))
        span = range(s, e + 1)
    else:
        span = range(max(0, i - a.before), min(len(lines), i + a.after + 1))
    print(f"== {os.path.basename(path)}")
    for k in span:
        print(clean(lines[k]))
