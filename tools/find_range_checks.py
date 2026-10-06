"""Find functions whose immediates include several figure-ID range boundaries (100/200/300/400, 32/33, 99/199...)."""
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

ASM = paths.decomp("build", "SSPP52", "asm")
INSN = re.compile(r"^/\* ([0-9A-F]{8}) [0-9A-F]{8}  [0-9A-F ]{11} \*/\t(\w+\.?) (.*)$")
INTEREST = {0x64: 100, 0xc8: 200, 0x12c: 300, 0x190: 400, -0x190: -400, -0xc8: -200, -0x12c: -300, -0x64: -100,
            0x1f4: 500, 0x3e8: 1000}


def immediates(ops):
    for m in re.finditer(r"(-?0x[0-9a-f]+|\b-?\d+\b)", ops):
        try:
            yield int(m.group(1), 0)
        except ValueError:
            pass


funcs = collections.defaultdict(set)
names = {}
for root, _, files in os.walk(ASM):
    for fn in files:
        if not fn.endswith("_text.s") and not fn.endswith("_text2.s"):
            continue
        cur = None
        for line in open(os.path.join(root, fn), encoding="utf-8", errors="replace"):
            if line.startswith(".fn "):
                cur = line.split()[1].rstrip(",")
                continue
            m = INSN.match(line)
            if not m or cur is None:
                continue
            op, args = m.group(2), m.group(3)
            if not re.match(r"cmp|subi|addi|li\b|cmpl", op):
                continue
            for v in immediates(args.split(",")[-1]):
                if v in INTEREST:
                    funcs[cur].add(INTEREST[v])
                    names[cur] = m.group(1)
hits = sorted(((len(v), f, sorted(v)) for f, v in funcs.items() if len({abs(x) for x in v} & {100, 200, 300, 400}) >= 3),
              reverse=True)
for n, f, v in hits[:30]:
    print(f"{f:20} {v}")
