"""Exploration helper: walk references upward from an object, printing the chain of referencing objects."""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from find_minions import global_igz  # noqa: E402
from igzobj import IgzFile  # noqa: E402


def build_index(f):
    """target start -> [(tag, field pos)]. Targets are objects, or raw buffers (pointed-to memory that is not an
    object, such as a list's element array); a field inside a buffer is attributed to the buffer's start."""
    fields = []
    for tag, offs in f.fixups.items():
        if tag == 5:
            continue
        for enc in offs:
            p = f.pos(enc)
            if p is not None:
                tgt = f.pos(f.u32(p))
                if tgt is not None:
                    fields.append((tag, p, tgt))
    buffer_starts = sorted({tgt for _, _, tgt in fields if f.object_at(tgt) is None})
    f.buffer_starts = buffer_starts
    into = collections.defaultdict(list)
    for tag, p, tgt in fields:
        o = f.object_at(tgt)
        into[o[0] if o else tgt].append((tag, p))
    return into


def owner(f, p):
    """(start, label) of the object or buffer that contains field position p."""
    o = f.object_at(p)
    if o:
        return o[0]
    import bisect
    i = bisect.bisect_right(f.buffer_starts, p) - 1
    return f.buffer_starts[i] if i >= 0 else None


def words(f, o, n=12):
    return " ".join(f"{f.u32(o[0] + 4 * k):08x}" for k in range(min(n, o[3] // 4)))


def walk(f, into, start, depth, seen, indent=0):
    o = f.object_at(start)
    if o:
        print("  " * indent + f"{o[2]} @ {o[0]:#x} size {o[3]:#x}: {words(f, o)}")
    else:
        print("  " * indent + f"[buffer] @ {start:#x}: {words(f, (start, 0, '', 0x30))}")
    if depth == 0 or start in seen:
        return
    seen.add(start)
    for tag, p in into.get(start, [])[:6]:
        parent = owner(f, p)
        if parent is not None:
            print("  " * (indent + 1) + f"<- fixup {tag:#04x} field +{p - parent:#x} of:")
            walk(f, into, parent, depth - 1, seen, indent + 2)


if __name__ == "__main__":
    f = IgzFile(global_igz(sys.argv[1]))
    into = build_index(f)
    for start in (int(a, 16) for a in sys.argv[2:]):
        walk(f, into, start, depth=5, seen=set())
        print()
