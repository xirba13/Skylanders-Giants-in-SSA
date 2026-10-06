"""Map the spawn ops in a script trace (tools/script_trace.py: "TRACE ctx=... op=... clone..." lines in Dolphin's
log) back to op lists and indices of a character file. A file's objects load together, so its ops keep their
distances in memory: the load base that explains the most logged ops is taken as the file's, and every logged op at
that base is named by its op list and index.

usage: python tools/trace_map.py <character .bld> [dolphin.log] [--last N] [--label INDEX=TEXT ...]
"""
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macro_dump as md  # noqa: E402
import paths  # noqa: E402
from toy_table import Level  # noqa: E402

TRACE = re.compile(r"TRACE ctx=([0-9a-f]{8}) op=([0-9a-f]{8}) (\S+)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bld")
    ap.add_argument("log", nargs="?", default=os.path.join(paths.DOLPHIN_USER, "Logs", "dolphin.log"))
    ap.add_argument("--last", type=int, default=400000, help="read only the last N lines of the log")
    ap.add_argument("--label", action="append", default=[], help="name an op: LIST:INDEX=TEXT")
    args = ap.parse_args()
    labels = {}
    for item in args.label:
        where, text = item.split("=", 1)
        labels[tuple(int(x) for x in where.split(":"))] = text
    lv = Level(args.bld)
    ops = {}  # encoded offset -> (list, index); an op shared by several positions keeps its first
    for n, (_, lst) in enumerate(md.op_lists(lv)):
        for i, op in enumerate(lst):
            ops.setdefault(op, (n, i))
    with open(args.log, "rb") as f:
        lines = f.read().decode("latin1").splitlines()[-args.last:]
    seen = []
    for line in lines:
        m = TRACE.search(line)
        if m:
            seen.append((int(m.group(1), 16), int(m.group(2), 16), m.group(3)))
    # each logged op address against each op of the file: the base (address - offset in its section) with the most
    # votes is where the file's Default section loaded
    votes = collections.Counter()
    spawn_offsets = [enc & 0xFFFFFF for enc in ops if (enc >> 24) == 0]
    for _, addr, _ in set(seen):
        for off in spawn_offsets:
            votes[addr - off] += 1
    if not votes:
        raise SystemExit("no TRACE lines")
    base, n = votes.most_common(1)[0]
    print(f"{len(seen)} TRACE lines; load base {base:#x} explains {n} distinct ops")
    last = None
    for ctx, addr, label in seen:
        enc = addr - base
        if enc in ops:
            where = ops[enc]
            text = labels.get(where, "")
            key = (where, text)
            if key != last:
                print(f"  op {where[0]}:{where[1]} {label} ctx {ctx:#x} {text}")
            last = key


if __name__ == "__main__":
    main()
