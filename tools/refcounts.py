"""Reference counts of IGZ objects.

Every igObject keeps its reference count in the low 19 bits of +0x04 (the bits above are flags): main.dol's
fn_800E6BA0 adds a reference with an atomic increment, fn_800E6968 drops one and destroys the object when the
count falls from 1. Files store the counts precomputed and the loader adds none: in retail files each object's
count is exactly the number of live owning pointers to it in the same file. Two fields are non-owning, in both
games: tfbActorInfo +0xA8 (-> its tfbScriptInfo) and AnimationBlendInfo +0x18 (-> a tfbPhysicsAnimation).
recount() reproduces every retail level file of both discs byte for byte (python tools/refcounts.py --verify).

So every edit that writes a pointer to an existing object has to add a reference to it. Test 20 crashed because
it did not: the inserted "Starting Scale XYZ" assignment shares the path objects of Tree Rex's own 'scale'
reference (a 2-element stack: 'my Minion Description', then the local stub 'Starting Scale XYZ', count 1). The
interpreter resolves a member stub the first time a path is evaluated (fn_80053730): it stores the real member
in the path and releases the stub. The new assignment ran first and released the stub to 0, which destroyed it;
when the 'scale' path was evaluated as Tree Rex appeared, its stub's name was gone and fn_80053730 read a name
at address 0 (DSI at 0x800537C4). The toy-table entries (shared ops) and the UI/global list edits had the same
kind of deficit.

Rather than tracking references at every edit, edited files are recounted before they are written. Live
pointers are object fields and words of buffers that a live field points to; a buffer's extent is the size word
before its data pointer (every buffer field in retail has one). Buffers abandoned when an edit rebuilt a list
elsewhere still hold their old pointers in the fixup table, but nothing reaches them, so they do not count.
"""
import bisect
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from igzdoc import OBJECTS, POINTERS  # noqa: E402

COUNT = 0x7FFFF  # low 19 bits of +0x04; fn_800E6968 compares the old count masked with clrlwi 13
SIZED = 0x80000000  # igMemory size word, the word before the data pointer: flags in the top bits (0x80000000
SIZE = 0x00FFFFFF  # always; tfbPhysicsBody and igSkeleton2 also set 0x10000000), size in bytes below
WEAK = {("tfbActorInfo", 0xA8), ("AnimationBlendInfo", 0x18)}  # non-owning pointer fields


def count(doc, obj):
    return doc.u32(obj + 4) & COUNT


def set_count(doc, obj, n):
    if not 0 <= n <= COUNT:
        raise ValueError(f"reference count of {obj:#x} would be {n}")
    doc.set_u32(obj + 4, (doc.u32(obj + 4) & ~COUNT & 0xFFFFFFFF) | n)


def live_refs(doc):
    """Counter: object -> number of live owning pointers to it."""
    objs = sorted(doc.lists[OBJECTS])
    objset = set(objs)
    sizes = {o: doc.type_sizes[doc.u32(o)] for o in objs}
    ptrs = doc.lists[POINTERS]

    def obj_at(p):
        i = bisect.bisect_right(objs, p) - 1
        if i >= 0 and objs[i] <= p < objs[i] + sizes[objs[i]]:
            return objs[i]
        return None

    buffers = {}  # start -> size in bytes (None: no size word, up to the next object or buffer)
    work = [p for p in ptrs if obj_at(p) is not None]
    seen = set(work)
    refs = collections.Counter()
    while work:
        new_buffers = []
        for p in work:
            v = doc.u32(p)
            if not v:
                continue
            owner = obj_at(p)
            if v in objset:
                if owner is None or (doc.types[doc.u32(owner)], p - owner) not in WEAK:
                    refs[v] += 1
            elif obj_at(v) is None and v not in buffers:
                size = None
                if owner is not None and obj_at(p - 4) == owner and doc.u32(p - 4) & SIZED:
                    size = doc.u32(p - 4) & SIZE
                buffers[v] = size
                new_buffers.append(v)
        work = []
        starts = sorted(set(objs) | set(buffers))
        for b in new_buffers:
            size = buffers[b]
            if size is None:
                i = bisect.bisect_right(starts, b)
                end = starts[i] if i < len(starts) and starts[i] >> 24 == b >> 24 else (b & ~0xFFFFFF) + (1 << 24)
            else:
                end = b + size
            i = bisect.bisect_left(ptrs, b)
            while i < len(ptrs) and ptrs[i] < end:
                if ptrs[i] not in seen:
                    seen.add(ptrs[i])
                    work.append(ptrs[i])
                i += 1
    return refs


def balance(doc):
    """{object: count - live owning pointers} for every object where it is not 0 (none in retail)."""
    refs = live_refs(doc)
    return {o: count(doc, o) - refs[o] for o in doc.lists[OBJECTS] if count(doc, o) != refs[o]}


def recount(doc):
    """Set every object's count to its live owning pointers; returns {object: new count - old count}."""
    refs = live_refs(doc)
    changed = {}
    for o in doc.lists[OBJECTS]:
        if count(doc, o) != refs[o]:
            changed[o] = refs[o] - count(doc, o)
            set_count(doc, o, refs[o])
    return changed


def summary(doc, changed):
    """'type +n: objects' lines for a balance() or recount() result."""
    hist = collections.Counter((doc.types[doc.u32(o)], v) for o, v in changed.items())
    return [f"{t} {v:+d}: {n}" for (t, v), n in sorted(hist.items(), key=lambda kv: (kv[0][1], kv[0][0]))]


def _igz_entries(path):
    import iga
    if path.endswith((".bld", ".arc")):
        return [(e.name, e.data) for e in iga.read(path).entries if e.data[:4] == b"IGZ\x01"]
    data = open(path, "rb").read()
    return [(os.path.basename(path), data)] if data[:4] == b"IGZ\x01" else []


def main():
    """python tools/refcounts.py FILE...: print each file's off-balance objects.
    python tools/refcounts.py --verify DIR...: recount every IGZ file under DIR and check nothing changes."""
    import glob
    from igzdoc import IgzDoc
    args = sys.argv[1:]
    verify = args[:1] == ["--verify"]
    paths = args[1:] if verify else args
    if verify:
        paths = [p for d in paths for p in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True))
                 if p.lower().endswith((".bld", ".arc", ".igz", ".lvl", ".pak"))]
    files = objects = bad = 0
    for path in paths:
        try:
            entries = _igz_entries(path)
        except Exception as e:  # not an archive this tool reads
            print(f"skip {path}: {e}")
            continue
        for name, data in entries:
            d = IgzDoc(data)
            b = balance(d)
            files += 1
            objects += len(d.lists[OBJECTS])
            if verify:
                if b:
                    bad += 1
                    print(f"{path} {name}: {len(b)} off balance")
                    for line in summary(d, b)[:8]:
                        print("    " + line)
                else:
                    recount(d)
                    if d.to_bytes() != data:
                        bad += 1
                        print(f"{path} {name}: balanced but the rewrite differs")
                continue
            print(f"{os.path.basename(path)} {name}: {len(d.lists[OBJECTS])} objects, {len(b)} off balance")
            for line in summary(d, b):
                print("    " + line)
    if verify:
        print(f"{files} IGZ files, {objects} objects, {bad} not reproduced")


if __name__ == "__main__":
    main()
