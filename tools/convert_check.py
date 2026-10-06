"""Check a conversion: every pointer, string reference, handle and memory block of the Giants file must reappear
in the converted file at the moved field, pointing at the moved target, with the target's type unchanged (or
renamed as TYPE_MAPS says). Prints the first problems and a summary."""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert  # noqa: E402
from igzdoc import IgzDoc, OBJECTS, POINTERS  # noqa: E402


def object_index(doc):
    starts = sorted(doc.lists[OBJECTS])
    sizes = {o: doc.type_sizes[doc.u32(o)] for o in starts}
    return starts, sizes


def owner(starts, sizes, enc):
    import bisect
    i = bisect.bisect_right(starts, enc) - 1
    if i >= 0 and starts[i] <= enc < starts[i] + sizes[starts[i]]:
        return starts[i]
    return None


def check_blocks(conv: convert.Converter, new: IgzDoc):
    """Every pointer to a converted data block must be preceded by a size word holding the block's new length,
    and the block must carry the converted format's magic (Havok version 7, FSB4)."""
    problems = []
    for size_field, old_len, new_len in conv.resized:
        size = new.u32(size_field) & 0xFFFFFF
        target = new.u32(size_field + 4)
        head = new.read(target, 0x10)
        if size != new_len:
            problems.append(f"size word at {size_field:#x} is {size:#x}, block is {new_len:#x}")
        if head[:4] == b"FSB4":
            n, shdr, data = struct.unpack_from("<III", head, 4)
            if 0x30 + shdr + data != new_len:
                problems.append(f"FSB4 at {target:#x}: header says {0x30 + shdr + data:#x}, block {new_len:#x}")
        elif head[:8] == bytes.fromhex("57e0e05710c0c010"):
            if struct.unpack_from(">I", head, 0x0C)[0] != 7:
                problems.append(f"packfile at {target:#x} is not version 7")
        else:
            problems.append(f"converted block at {target:#x} has magic {head[:4].hex()}")
    # vertex data blocks end with their buffer's pack data (convert.Converter._vertex_pack_data)
    if conv.pack_data:
        rec = new.record(convert.MEM_BLOCKS)
        for block, pack in conv.pack_data.items():
            size, enc = struct.unpack_from(">II", rec.body, 8 * block)
            n = size & 0xFFFFFF
            if new.read(enc + n - len(pack), len(pack)) != pack:
                problems.append(f"vertex data block {block} does not end with its pack data")
    return problems


def check(old: IgzDoc, conv: convert.Converter, new: IgzDoc, limit=10):
    problems = collections.Counter()
    shown = []
    o_starts, o_sizes = object_index(old)
    n_starts, n_sizes = object_index(new)
    old_lists = conv.old_lists
    for tag, lst in old_lists.items():
        if tag == OBJECTS:
            continue
        new_set = set(new.lists.get(tag, ()))
        for enc in lst:
            n = conv.addr(enc, field=True)
            if n is None:
                problems[f"tag {tag:#x}: field dropped"] += 1
                continue
            if n not in new_set:
                if tag == 0x0F and n in getattr(conv, "mem_removed", ()):
                    continue  # removed on purpose (convert.MEM_SIZE_CONVENTIONS)
                problems[f"tag {tag:#x}: fixup missing"] += 1
                if len(shown) < limit:
                    shown.append(f"tag {tag:#x} field {enc:#x}->{n:#x} missing")
                continue
            if tag == POINTERS:
                ov = conv.old_values[enc]
                nv = new.u32(n)
                want = conv.addr(ov) if ov else 0
                if nv != want:
                    problems["pointer value wrong"] += 1
                    if len(shown) < limit:
                        shown.append(f"pointer {enc:#x}: {ov:#x} -> {nv:#x}, expected {want:#x}")
                    continue
                ot = owner(o_starts, o_sizes, ov) if ov else None
                nt = owner(n_starts, n_sizes, nv) if nv else None
                if (ot is None) != (nt is None):
                    problems["pointer target kind changed"] += 1
                    continue
                if ot is not None:
                    tname = conv.old_types[conv.old_type_of[ot]]
                    want_name = convert.TYPE_MAPS[tname][0] if tname in convert.TYPE_MAPS else tname
                    if new.types[new.u32(nt)] != want_name:
                        problems["pointer target type changed"] += 1
                    elif ov - ot != 0 and nv - nt == 0:
                        problems["interior pointer moved to start"] += 1
            elif tag in (0x07, 0x0E, 0x0B, 0x10):
                if new.u32(n) != conv.old_values[enc]:
                    problems[f"tag {tag:#x}: value changed"] += 1
    for p in shown:
        print("  ", p)
    return problems
