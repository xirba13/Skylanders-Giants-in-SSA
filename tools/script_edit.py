"""Structural script edits on IGZ levels: clone objects, insert ops into the OpCodeList, add toy-table entries.

Op stream (verified on Init_Setup.bld): one OpCodeList holds the script as a flat array of op pointers. Ops with
a control word at +0x18 (OpDefineMacro, OpAbstractFlow, OpUseMacro, OpMacroInterface, ...) store in its low half
the number of following ops that belong to them, so inserting ops inside a block means growing every enclosing
op's count. A toy-table entry is 9 ops: use macro, INTERFACE, level load, item code, info, element, name,
flow macro, flow continue; only the parameter ops (with their value objects) are per entry.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from igzdoc import OBJECTS, POINTERS  # noqa: E402
from opstream import op_list  # noqa: E402
from toy_table import Level  # noqa: E402

DEFAULT = 0  # object section 0 ("Default" pool)
# ops whose control word counts the ops of their block: every type seen with a non-zero count in global.bld,
# Init_Setup.bld and character scripts of both games (STARTUP and SHUTDOWN too: Tree Rex's STARTUP holds 503)
COUNTING = {"OpDefineMacro", "OpAbstractFlow", "OpUseMacro", "OpMacroInterface", "OpLoopValue",
            "OpMacroSection", "OpPreScript", "OpForEach", "OpStartUp", "OpShutDown", "OpCheckValue",
            "OpCheckReference", "OpCheckMembership", "OpCheckFOV", "OpControl", "OpDefineMacroSpecialization",
            "OpDefineStructure", "OpStructureSection", "OpFindSubSet", "OpFindVariable", "OpFlowBehavior",
            "OpMoveTo", "OpSlideValue", "OpSpawn", "OpStartSequence", "OpUserBehavior"}
# which pointer fields to follow when cloning a parameter's private value objects
FOLLOW = {"OpMacroParameter": (0x30,), "ValueRHSVariant": (0x08,), "RHSValueStack": (0x14,),
          "RHSReferenceStack": (0x14,)}


def check_unshared(ops, j):
    """Retail op arrays share identical op objects between positions (one OpFlowBuiltInBehavior serves 326
    positions in Tree Rex's script, one OpMacroInterface 46), so changing the block count of the op at j would change
    every block that shares it. Refuse rather than corrupt them."""
    if ops.count(ops[j]) > 1:
        raise ValueError(f"op {j} is shared by {ops.count(ops[j])} positions; its block count cannot change alone")


class Editor:
    def __init__(self, lv: Level):
        self.lv, self.d = lv, lv.doc
        self.member = {}
        for tag, lst in self.d.lists.items():
            for enc in lst:
                self.member.setdefault(enc, set()).add(tag)

    # ---- cloning ----
    def _buffer_size(self, owner, field):
        """Byte size of a raw buffer pointed to by owner+field (list buffers keep count at +0x08)."""
        d = self.d
        t = self.lv.type(owner)
        if t in ("RHSValueStack", "RHSReferenceStack") and field == 0x14:
            return 4 * max(d.u32(owner + 0x0C), 1) + 4  # elements plus the trailing word seen in retail
        raise ValueError(f"unknown buffer {t}+{field:#x}")

    def clone(self, root):
        """Deep-copy root and the private objects/buffers it reaches through FOLLOW fields.
        Returns the clone of root. Fixups of every copied field are duplicated; pointers between copies remapped."""
        d = self.d
        plan, order = {}, []  # src -> (size, is_object)

        def visit(src, size, is_obj):
            if src in plan:
                return
            plan[src] = (size, is_obj)
            order.append(src)
            if is_obj:
                for off in FOLLOW.get(self.lv.type(src), ()):
                    f = src + off
                    if POINTERS in self.member.get(f, ()) and d.u32(f):
                        tgt = d.u32(f)
                        if self.lv.obj_at(tgt) == tgt:
                            visit(tgt, d.type_sizes[d.u32(tgt)], True)
                        elif self.lv.obj_at(tgt) is None:
                            visit(tgt, self._buffer_size(src, off), False)

        visit(root, d.type_sizes[d.u32(root)], True)
        new = {}
        for src in order:
            size, is_obj = plan[src]
            data = d.read(src, size)
            new[src] = d.add_object(DEFAULT, data, align=8) if is_obj else d.append(DEFAULT, data, align=8)
        for src in order:
            size, _ = plan[src]
            for k in range(0, size, 4):
                for tag in self.member.get(src + k, ()):
                    if tag == OBJECTS:
                        continue
                    d.add_fixup(tag, new[src] + k)
                    if tag == POINTERS:
                        v = d.u32(src + k)
                        if v in new:
                            d.set_u32(new[src] + k, new[v])
        for src, dst in new.items():  # keep the membership index current for later clones
            for k in range(0, plan[src][0], 4):
                if src + k in self.member:
                    self.member.setdefault(dst + k, set()).update(self.member[src + k] - {OBJECTS})
        return new[root]

    # ---- op stream ----
    def insert_ops(self, position, new_ops, sibling_start, code_list=None):
        """Insert op pointers before index `position`, as siblings of the ops from `sibling_start` to
        position-1. Every counting op that starts before sibling_start and whose range covers those ops
        (an ancestor) grows by len(new_ops). code_list: the OpCodeList to edit (default: the largest)."""
        d = self.d
        if code_list is None:
            o, buf, ops = op_list(self.lv)
        else:
            o, buf = code_list, d.u32(code_list + 0x14)
            ops = [d.u32(buf + 4 * i) for i in range(d.u32(code_list + 0x08))]
        grown = []
        for j in range(0, sibling_start):
            op = ops[j]
            if self.lv.type(op) not in COUNTING:
                continue
            ctl = d.u32(op + 0x18)
            lo = ctl & 0xFFFF
            if j + lo >= position - 1:
                check_unshared(ops, j)
                if lo + len(new_ops) > 0xFFFF:
                    raise ValueError("count overflow")
                d.set_u32(op + 0x18, (ctl & 0xFFFF0000) | (lo + len(new_ops)))
                grown.append((j, self.lv.type(op), lo, lo + len(new_ops)))
        elems = ops[:position] + list(new_ops) + ops[position:]
        nbuf = d.append(DEFAULT, b"".join(struct.pack(">I", p) for p in elems), align=16)
        d.copy_words(buf, nbuf, position)
        for k in range(position, position + len(new_ops)):
            d.add_fixup(POINTERS, nbuf + 4 * k)
        d.copy_words(buf + 4 * position, nbuf + 4 * (position + len(new_ops)), len(ops) - position)
        d.set_u32(o + 0x08, len(elems))
        d.set_u32(o + 0x0C, len(elems))
        d.set_u32(o + 0x10, 0x80000000 | (4 * len(elems)))
        d.set_u32(o + 0x14, nbuf)
        return grown


def add_import(lv, index: int, file_name: str) -> int:
    """Append an import (record 2 entry: object index, FNV-1a of the file name); returns its handle value."""
    import iga
    d = lv.doc
    rec = d.record(0x02)
    n = rec.count
    rec.body = rec.body[:8 * n] + struct.pack(">II", index, iga.fnv1a(file_name.encode())) + rec.body[8 * n:]
    rec.words[3] = n + 1
    return 0x80000000 | n


def literal_slot(lv, param):
    d = lv.doc
    stack = d.u32(d.u32(param + 0x30) + 0x08)
    return stack + 0x20


def handle_slot(lv, param):
    """Address of the handle word of a reference parameter (first element of its RHSReferenceStack buffer)."""
    d = lv.doc
    return d.u32(d.u32(param + 0x30) + 0x14)


def import_of(lv, handle: int):
    """(object index, file-name hash) of an import handle (0x80000000 | record 2 entry)."""
    rec = lv.doc.record(0x02)
    return struct.unpack_from(">II", rec.body, 8 * (handle & 0x7FFFFFFF))


def toy_call(lv: Level, code: int):
    """(stream index, the 9 ops) of the toy-table call whose item code is `code`."""
    d = lv.doc
    _, _, ops = op_list(lv)
    # locate the call by its item-code parameter op in the stream
    codes = [i for i, op in enumerate(ops)
             if lv.type(op) == "OpMacroParameter" and d.cstr(d.u32(op + 0x1c)) == "item code"
             and d.u32(literal_slot(lv, op)) == code]
    if len(codes) != 1:
        raise ValueError(f"toy entry {code}: found {len(codes)}")
    i = codes[0] - 3  # call starts with use macro, INTERFACE, level load
    call = ops[i:i + 9]
    names = [lv.type(op) for op in call]
    if names[0] != "OpUseMacro" or names[1] != "OpMacroInterface" or names[8] != "OpFlowBuiltInBehavior":
        raise ValueError(f"unexpected call layout {names}")
    return i, call


def entry_handles(lv: Level, code: int):
    """Handles of the level-load and name parameters of toy entry `code`."""
    _, call = toy_call(lv, code)
    d = lv.doc
    return {"level load": d.u32(handle_slot(lv, call[2])), "name": d.u32(handle_slot(lv, call[6]))}


def add_toy_entry(lv: Level, template_code: int, new_code: int, level_load=None, name=None, element=None):
    """Clone the toy-table entry for template_code as a new entry for new_code, inserted right after it.
    level_load / name: new handle values (0x80000000 | n), or None to keep the template's.
    element: literal for a cloned element parameter, or None to share the template's element op."""
    return add_toy_entries(lv, template_code, [{"code": new_code, "level_load": level_load, "name": name,
                                                 "element": element}])


def add_toy_entries(lv: Level, template_code: int, specs):
    """Clone the template entry once per spec ({code, level_load, name, element}, see add_toy_entry) and insert
    all the new calls right after the template, in spec order, with one rewrite of the op stream."""
    d = lv.doc
    ed = Editor(lv)
    i, call = toy_call(lv, template_code)
    new_ops = []
    for spec in specs:
        lvl = ed.clone(call[2])
        code = ed.clone(call[3])
        d.set_u32(literal_slot(lv, code), spec["code"])
        elem = call[5]
        if spec.get("element") is not None:
            elem = ed.clone(call[5])
            d.set_u32(literal_slot(lv, elem), spec["element"])
        nm = ed.clone(call[6])
        if spec.get("level_load") is not None:
            d.set_u32(handle_slot(lv, lvl), spec["level_load"])
        if spec.get("name") is not None:
            d.set_u32(handle_slot(lv, nm), spec["name"])
        new_ops += [call[0], call[1], lvl, code, call[4], elem, nm, call[7], call[8]]
    return ed.insert_ops(i + 9, new_ops, sibling_start=i)
