"""Local copies of Giants global.bld macros in a Giants character's own script (applied before conversion).

A converted Giants character calls Giants-only global macros through stubs that Spyro's Adventure cannot link,
and a call that does not link is skipped together with its block, statements after the call included. Tree Rex's
B charge needs two of them: "Movement - Displace Velocity" moves him every frame, and "Minion - Combat - Query to
Add Enemy to Already Hurt Handler" encloses the statements that hurt the creatures he runs into (tests 21-28: no
speed, no damage).

port() turns such a stub into a local macro of the script that calls it. A local macro is a definition op
(+0x1C 0, +0x18 the number of ops that follow) in the MACROS section, followed by its interface (count: the
parameters and OpFlowMacro; +0x1C the OpCreateVariableList of its local variables, or 0), the parameters (+0x38
the definition), OpFlowMacro, the body, and a closing 'flow continue'; calls reach it through the same
ScriptGroupStack as a stub (+0x18 and the one-element buffer). The stub itself becomes the definition op, so
every call and parameter already points at it, and Giants' own ops are copied after it: the interface, the
parameters (with their IDs, so every call binds as before), OpFlowMacro, the body chosen in PORTS (Giants' own ops,
or single ops of Spyro's Adventure's macros), and the closing 'flow continue'.

Objects are copied from Giants' global.bld with their fixups: pointers between copied objects are remapped,
buffers are copied with them (their size word, registered in list 0x0F, gives the size), strings are added, class
numbers (list 0x10) and imports of the file's own script classes ('level.bld' namespace, an index into record
1) are translated by name, and engine imports (member and class hashes) are copied as they are. Anything else a
copied object points to (another macro, a structure, a global variable, an op that is not copied) is refused, so a
body is limited to what stands alone; the interface's local variables are dropped. An op copied from Spyro's
Adventure's global.bld into the Giants-format file carries Spyro's Adventure's memory-size registrations, which are
the ones the conversion produces anyway.

Both files are in Giants' format here, so the conversion that follows treats the copies like the character's own
objects (and script objects have the same layout in both games: 61 of 61 shared script types have the same size).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import giants  # noqa: E402
import iga  # noqa: E402
import macro_dump as md  # noqa: E402
import minions  # noqa: E402
import paths  # noqa: E402
import script_edit  # noqa: E402
from igzdoc import IgzDoc, OBJECTS, POINTERS, STRINGS_REF  # noqa: E402
from macro_calls import used_macro  # noqa: E402
import script_fixes  # noqa: E402
from script_fixes import class_name, grow_in_place, script_classes  # noqa: E402
from toy_table import Level  # noqa: E402

HANDLES, MEM_SIZES, CLASS_NUMBERS = 0x07, 0x0F, 0x10
OWN_FILE = iga.fnv1a(b"level.bld")  # import namespace of a file's own objects
GLOBAL = iga.fnv1a(b"global.bld")
DEFAULT = 0  # object section 0
SIZE = 0x00FFFFFF  # a size word's byte count (its top bits are flags)

# Giants macro -> its body, a list of pieces copied in order: ("own", first, last) copies the ops first..last of
# Giants' definition (relative to the definition op) as one block; ("ssa", macro, statement) copies the op of Spyro's
# Adventure's macro that prints as statement (script_print). An empty list leaves the body empty: the call runs,
# then the statements in the call's block. The macro's local variables (the interface's +0x1C, an
# OpCreateVariableList) are copied only with a ("locals",) piece, for a body that uses them.
PORTS = {
    # Giants moves an actor on its mover list ("Movement Data . movers", which Spyro's Adventure lacks) through the
    # list's velocity data; any other actor it displaces directly, with the mode its 'displacement type' picks:
    # ops 33-40, "if type == 0: displace (mode 0) else: if == 1: displace (mode 1) else: if == 2: displace (mode 2)".
    # Mode 0 adds to the velocity: Spyro's Adventure's "Minion - Check for Minion Appropriate Ground" sets a velocity
    # by zeroing its horizontal length first, and Giants caps an accumulating one after every call through "Movement
    # - Get/Set Velocity", which need its mover data. Without either, Tree Rex's B charge, displaced every frame,
    # sped up without limit (test 29), so the horizontal length is zeroed first and each call sets it.
    "Movement - Displace Velocity": [
        ("ssa", "Minion - Check for Minion Appropriate Ground",
         "[my@optoplevelbehavior . import(0x32741c32 in 0x58709542) . horizontal length@vectormeasurement] := 0"),
        ("own", 33, 40)],
    # Giants keeps, per attack, the creatures hurt in the last 'cooldown duration' seconds in structures Spyro's
    # Adventure lacks ("Minion - Already Hurt Groupings"). Empty, the macro leaves 'enemy already in set' at the 0
    # every call passes, so the statements after the call hurt each creature in reach every time they run.
    "Minion - Combat - Query to Add Enemy to Already Hurt Handler": [],
    # Giants' whole body (ops 5-9): slide the sound's volume to 0 over 'fade out time', find the 'Music Control
    # Data' owned by Macros_Music and add the sound to its 'streaming sounds being faded out', which "Sound - System
    # Update" stops once their volume is 0 - in Spyro's Adventure too (same structure, IDs, member and actor).
    # Without it Tree Rex's loops were never stopped: the bird wing loop and the charge wind loop.
    "Sound - Stop Loop": [("own", 5, 9)],
    # Giants looks the actor up on its mover list; ops 18-25 are its branch for any other actor (every actor in
    # Spyro's Adventure): the remembered controller from the player's joined data, the current one from the actor.
    # Bouncer's rocket target (test 36: it stayed in front of him) and others steer with it.
    "Movement - Get Controller Reference": [("own", 18, 25)],
    # Giants' whole body (ops 5-64) and its four local variables: while the ground a few units ahead of the actor is
    # walkable it hands the actor the controller (the engine then moves it with the stick); otherwise it searches
    # the stick's direction and its sides for walkable ground and displaces the actor there. Bouncer's rocket
    # target moves with it.
    "Movement - Simple Safe Movement": [("locals",), ("own", 5, 64)],
    # Ops 15-16 (no 'degrees': return) and 34-37, the branch for an actor that is not on the mover list: turn it to
    # 'degrees' under OpControl (Crusher's A combo turns him with it).
    "Movement - Turn To": [("own", 15, 16), ("own", 34, 37)],
    # Ops 52-64, the branch for an actor that is not on the mover list: set each velocity component given (the
    # others are NaN) on the actor's own velocity.
    "Movement - Set Velocity": [("own", 52, 64)],
    # Giants returns 'velocity data', a member of its creature description (a structure Spyro's Adventure lacks),
    # filled from the actor's velocity vector. Empty, the call runs the statements of its block, which every Giant
    # nests in it (Hot Head's fire, Crusher's boulder target, ...): as a Giants-only macro the call skipped them.
    # script_fixes.read_velocity_directly turns their reads of the returned members into the engine paths Giants
    # copies them from.
    "Movement - Get Velocity": [],
    # Giants' whole body (ops 11-51): pick the sound from the set when no sound is given (next, or random), play it on
    # the actor with an optional fade-in, or through "Sound - Play With Delay" after a delay. It finds the same 'Music
    # Control Data' as Stop Loop. (Until test 31 the calls went to "Sound - Play From Set", which lost the delays and
    # fade-ins and played nothing for a single sound such as the charge wind loop.)
    "Sound - Ultra Sound": [("own", 11, 51)],
}


class Copier:
    """Copies objects of a source IgzDoc into a target IgzDoc (Giants format).

    exports: {source object: global.bld import index the target uses for it}, when the source is a global.bld:
    a pointer to such an object becomes an import handle in the target. Definitions (OpDefine*) and structure
    members (OpCreateVariable) that are not copied map to the target's stub of the same name (and IDs), or to a new
    stub copied from the source (an OpDefine* or OpCreateVariable object outside every op list is a stub)."""

    def __init__(self, target: Level, source: Level, exports=None):
        self.t, self.s = target, source
        self.td, self.sd = target.doc, source.doc
        self.map = {}  # source encoded address -> (target value, fixup list of the target word)
        self.allowed = set()  # source ops and variables that may be copied
        self.exports = exports or {}
        self.s_classes, self.t_classes = script_classes(self.sd), script_classes(self.td)
        self.s_imports = self.sd.record(0x02)
        self.t_imports = self.td.record(0x02)
        self.s_ops = set()
        for _, ops in md.op_lists(source):
            self.s_ops.update(ops)
        self.created = []  # (kind, name) of the stubs created
        self._declared = None
        # a reference to a parameter of a macro the body calls points, in global.bld, at that macro's own
        # parameter op (a call can even reuse those ops); here it points at the copied call's parameter op of the
        # same macro and IDs, which the interpreter binds the same way: {source param: source param copied}
        self.aliases = {}

    # -- fixups --
    def import_pair(self, rec, k):
        return struct.unpack_from(">II", rec.body, 8 * k)

    def add_import(self, a, b):
        for k in range(self.t_imports.count):
            if self.import_pair(self.t_imports, k) == (a, b):
                return 0x80000000 | k
        rec = self.t_imports
        n = rec.count
        rec.body = rec.body[:8 * n] + struct.pack(">II", a, b) + rec.body[8 * n:]
        rec.words[3] = n + 1
        return 0x80000000 | n

    def handle(self, h):
        a, b = self.import_pair(self.s_imports, h & 0x7FFFFFFF)
        if b == OWN_FILE:  # an index into the source file's own objects (each tfbSoundInfo +0x4C has its own)
            raise ValueError(f"import of the source's own object {a:#x}")
        if b == GLOBAL:
            raise ValueError(f"import of a global.bld object ({a:#x})")
        return self.add_import(a, b)

    def class_number(self, v):
        """A class number of the source (script_fixes.script_classes: an index into its named references), with or
        without the top-bit flag (a parameter's or a stack's value class, e.g. 0x80000006 for tfbActorInfo in
        Tree Rex), as the target's; a class the target's own script never used is added to it."""
        return script_fixes.class_number(self.td, self.t_classes, class_name(self.s_classes, v))

    def words(self, src, dst, size, skip=()):
        """Fixups and values of size bytes at src, written at dst; the words at offsets in skip become 0."""
        sd, td = self.sd, self.td
        for k in range(0, size, 4):
            sf, tf = src + k, dst + k
            if k in skip:
                td.set_u32(tf, 0)
                continue
            for tag in sd.tags_at(sf):
                v = sd.u32(sf)
                if tag == POINTERS:
                    if v:
                        v, tag = self.pointer(v, sf)
                        td.set_u32(tf, v)
                elif tag == HANDLES:
                    td.set_u32(tf, self.handle(v))
                elif tag == STRINGS_REF:
                    td.set_u32(tf, td.add_string(sd.cstr(v)))
                elif tag == CLASS_NUMBERS:
                    td.set_u32(tf, self.class_number(v))
                elif tag != MEM_SIZES:  # a memory-size word keeps its value
                    raise ValueError(f"fixup list {tag:#x} at {sf:#x}")
                td.add_fixup(tag, tf)

    # -- objects --
    def pointer(self, v, field):
        """(target value, fixup list) for a source pointer v found at field."""
        if v in self.map:
            return self.map[v]
        if v in self.aliases:
            self.map[v] = self.pointer(self.aliases[v], field)
            return self.map[v]
        s = self.s
        if s.obj_at(v) == v:
            t = s.type(v)
            if v in self.exports:  # a global.bld object: imported
                self.map[v] = (self.add_import(self.exports[v], GLOBAL), HANDLES)
            elif t.startswith("OpDefine") and v not in self.allowed:  # another macro or a structure
                self.map[v] = (self.stub(v), POINTERS)
            elif t == "OpCreateVariable" and v not in self.allowed:  # a member of a structure
                self.map[v] = (self.member(v), POINTERS)
            elif v in self.s_ops and v not in self.allowed:
                raise ValueError(f"{field:#x} points at {t} '{s.name_of(v)}', an op that is not copied")
            else:
                return self.object(v), POINTERS
            return self.map[v]
        # a buffer: its size word precedes the pointer (0x80000000 | bytes), registered in list 0x0F or not
        # depending on the type and the game (Giants does not list RHSReferenceStack +0x10; the conversion that
        # follows applies Spyro's Adventure's convention)
        word = self.sd.u32(field - 4)
        if not word & 0x80000000 or not 0 < word & SIZE < 0x10000:
            raise ValueError(f"buffer at {v:#x} (from {field:#x}): no size word before the pointer ({word:#x})")
        return self.buffer(v, word & SIZE), POINTERS

    def _stub_like(self, o):
        """Whether a target object is a stub: outside every op list and every list of declared variables."""
        if self._declared is None:
            t, td = self.t, self.td
            self._declared = set()
            for _, ops in md.op_lists(t):
                self._declared.update(ops)
            if "OpCreateVariableList" in td.types:
                lt = td.type_index("OpCreateVariableList")
                for lst in t.objs:
                    if td.u32(lst) == lt:
                        n, buf = td.u32(lst + 8), td.u32(lst + 0x14)
                        self._declared.update(td.u32(buf + 4 * k) for k in range(n))
        return o not in self._declared

    def stub(self, v):
        """The target's stub for the definition at v (same type, name and creation IDs +0x20/+0x24), else a new
        one: a copy of the definition object alone."""
        s, t, sd, td = self.s, self.t, self.sd, self.td
        kind, name, ids = s.type(v), s.name_of(v), (sd.u32(v + 0x20), sd.u32(v + 0x24))
        found = [o for o in t.objs if t.type(o) == kind and t.name_of(o) == name]
        if len(found) > 1 or (found and (td.u32(found[0] + 0x20), td.u32(found[0] + 0x24)) != ids):
            raise ValueError(f"{kind} '{name}': {len(found)} in the target, IDs {[hex(x) for x in ids]}")
        if found:
            return found[0]
        if any(v + k in s.ptrs for k in range(4, sd.type_sizes[sd.u32(v)], 4)):
            raise ValueError(f"{kind} '{name}' holds pointers; not copied as a stub")
        self.created.append((kind, name))
        return self.object(v)

    def _variable_key(self, lv, classes, o):
        """(name, value class, element class or structure) of an OpCreateVariable, as names."""
        d = lv.doc

        def class_of(f):
            w = d.u32(f)
            return class_name(classes, w) if CLASS_NUMBERS in d.tags_at(f) else ("raw", w)
        name = d.cstr(d.u32(o + 0x1C)) if d.u32(o + 0x1C) else None
        w = d.u32(o + 0x24)
        element = ("structure", lv.name_of(w)) if (o + 0x24 in lv.ptrs and w) else class_of(o + 0x24)
        return name, class_of(o + 0x20), element

    def member(self, v):
        """The target's stub for the structure member at v (same name, value class and element), else a copy."""
        key = self._variable_key(self.s, self.s_classes, v)
        t, td = self.t, self.td
        vt = td.type_index("OpCreateVariable")
        found = [o for o in t.objs if td.u32(o) == vt and self._stub_like(o)
                 and self._variable_key(t, self.t_classes, o) == key]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            raise ValueError(f"member {key}: {len(found)} candidates in the target")
        self.created.append(("OpCreateVariable", key[0]))
        return self.object(v)

    def object(self, src, skip=()):
        """Copy of the object at src; fields at the offsets in skip are left 0."""
        sd, td = self.sd, self.td
        name = sd.types[sd.u32(src)]
        size = sd.type_sizes[sd.u32(src)]
        if name not in td.types:  # a type the target's own script never used (OpTurnTo); the type records are
            td.types.append(name)  # rebuilt from these lists when the file is written
            td.type_sizes.append(size)
            td._types_dirty = True
        data = bytearray(sd.read(src, size))
        struct.pack_into(">I", data, 0, td.types.index(name))
        dst = td.add_object(DEFAULT, bytes(data), align=8)
        self.map[src] = (dst, POINTERS)
        self.words(src + 4, dst + 4, size - 4, {k - 4 for k in skip})
        return dst

    def buffer(self, src, size):
        dst = self.td.append(DEFAULT, self.sd.read(src, size), align=8)
        self.map[src] = (dst, POINTERS)
        self.words(src, dst, size)
        return dst


def _exports(doc, base):
    """{object: import index} of a global.bld's root list (import index = root position + base)."""
    n, buf = doc.u32(minions.ROOT_LIST + 8), doc.u32(minions.ROOT_LIST + 0x14)
    out = {}
    for k in range(n):
        o = doc.u32(buf + 4 * k)
        if not o & 0x80000000:
            out.setdefault(o, k + base)
    return out


def _definition(lv, name):
    """(op list object, ops, position) of the definition of `name` in a global.bld."""
    for lst, ops in md.op_lists(lv):
        for i, op in enumerate(ops):
            if lv.type(op) == "OpDefineMacro" and lv.name_of(op) == name:
                return lst, ops, i
    raise KeyError(name)


def _self_contained(lv, ops, first, last):
    d = lv.doc
    for j in range(first, last + 1):
        if lv.type(ops[j]) in script_edit.COUNTING and d.u32(ops[j] + 0x18) & 0xFFFF != 0xFFFF:  # not a return
            end = j + (d.u32(ops[j] + 0x18) & 0xFFFF)
            if end > last:
                raise ValueError(f"op {j} ({lv.type(ops[j])}) ends at {end}, past {last}")


def _macros_end(lv, ops):
    """Positions (first op inside, closing op) of the top-level MACROS section of an op list."""
    d = lv.doc
    i = 1
    while i < len(ops):
        t = lv.type(ops[i])
        n = d.u32(ops[i] + 0x18) & 0xFFFF if t in script_edit.COUNTING else 0
        if t == "OpMacroSection":
            return i + 1, i + n
        i += n + 1
    raise ValueError("no MACROS section")


def _ssa_op(ssa, macro, statement):
    """The op of Spyro's Adventure's `macro` that prints as `statement`."""
    import minions
    import script_print as sp
    lv, res = ssa
    pr = sp.Printer(lv, res)
    _, ops, i0 = _definition(lv, macro)
    for j in range(i0 + 1, i0 + 1 + (lv.doc.u32(ops[i0] + 0x18) & 0xFFFF)):
        if (pr.statement(ops[j]) or "").strip() == statement:
            if lv.type(ops[j]) in script_edit.COUNTING:
                raise ValueError(f"{macro!r}: {statement!r} has a block")
            return ops[j]
    raise ValueError(f"{macro!r} has no op {statement!r}")


def port(data: bytes, ports=None, giants_global=None, ssa_global=None):
    """Returns (bytes, {macro: what was done})."""
    import minions
    ports = PORTS if ports is None else ports
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    src = Level(giants_global or paths.giants("permanent", "global.bld"))
    sd = src.doc
    ssa = None
    if any(piece[0] == "ssa" for body in ports.values() for piece in body):
        ssa_path = ssa_global or paths.ssa("permanent", "global.bld")
        ssa_lv = Level(ssa_path)
        ssa = (ssa_lv, md.Resolver(ssa_lv, ssa_path, minions.EXPORT_BASE))
    lists = list(md.op_lists(lv))
    # every local macro goes into the main script's MACROS section; scripts of the same file call each other's
    # local macros (Tree Rex's lists 0 and 4 call "Minion - Giant Init" macros defined in list 8)
    main = max(lists, key=lambda x: len(x[1]))[0]
    exports = _exports(sd, giants.GIANTS_EXPORT_BASE)
    report, new_ops = {}, []
    for name, body in ports.items():
        stubs = [o for o in lv.objs if lv.type(o) == "OpDefineMacro" and lv.name_of(o) == name]
        if not stubs:
            report[name] = "not called"
            continue
        if len(stubs) != 1 or any(stubs[0] in ops for _, ops in lists):
            raise ValueError(f"{name!r}: {len(stubs)} stubs, or the stub is in an op list")
        stub = stubs[0]
        _, sops, i0 = _definition(src, name)
        sdef = sops[i0]
        if (sd.u32(sdef + 0x20), sd.u32(sdef + 0x24)) != (d.u32(stub + 0x20), d.u32(stub + 0x24)):
            raise ValueError(f"{name!r}: the stub's IDs differ from Giants' definition")
        n = sd.u32(sdef + 0x18) & 0xFFFF
        iface = sops[i0 + 1]
        header = list(range(i0 + 1, i0 + 2 + (sd.u32(iface + 0x18) & 0xFFFF)))
        # the ops to copy, in order, each with the copier of its file
        cp = Copier(lv, src, exports)
        cp.map[sdef] = (stub, POINTERS)
        ssa_cp = Copier(lv, ssa[0]) if ssa else None
        sequence = [(cp, sops[j]) for j in header]
        described = []
        local_vars = []
        if ("locals",) in body and sd.u32(iface + 0x1C):
            lst = sd.u32(iface + 0x1C)
            local_vars = [sd.u32(sd.u32(lst + 0x14) + 4 * k) for k in range(sd.u32(lst + 0x08))]
            described.append(f"{len(local_vars)} local variables")
        for piece in body:
            if piece[0] == "locals":
                continue
            if piece[0] == "own":
                _, first, last = piece
                _self_contained(src, sops, i0 + first, i0 + last)
                sequence += [(cp, sops[j]) for j in range(i0 + first, i0 + last + 1)]
                described.append(f"Giants' ops {first}-{last}")
            else:
                _, macro, statement = piece
                op = _ssa_op(ssa, macro, statement)
                ssa_cp.allowed.add(op)
                sequence.append((ssa_cp, op))
                described.append(f"one op of {macro!r}")
        sequence.append((cp, sops[i0 + n]))
        cp.allowed = {op for c, op in sequence if c is cp} | set(local_vars)  # locals: copies, not member stubs
        params = {}
        for c, op in sequence:
            if c is cp and src.type(op) == "OpMacroParameter":
                params.setdefault((sd.u32(op + 0x38), sd.u32(op + 0x40), sd.u32(op + 0x44)), op)
        for o in src.objs:
            if src.type(o) == "OpMacroParameter" and o not in cp.allowed:
                key = (sd.u32(o + 0x38), sd.u32(o + 0x40), sd.u32(o + 0x44))
                if key in params and sd.u32(o + 0x38) != sdef:
                    cp.aliases[o] = params[key]
        copies = []
        for c, op in sequence:
            if op in c.map:
                copies.append(c.map[op][0])
            else:  # the interface keeps its local variables (+0x1C) only when the body asked for them
                copies.append(c.object(op, skip=(0x1C,) if op == iface and not local_vars else ()))
        d.set_u32(stub + 0x1C, 0)
        d.set_u32(stub + 0x18, len(copies))
        new_ops.append([stub] + copies)
        report[name] = f"{len(copies)} ops, body: {', '.join(described) or 'empty'}"
    if not new_ops:
        return data, report
    # whole insertion in fours (script_fixes.grow_in_place): pad the last macro with 'flow continue' ops, which
    # follow its own closing one and are never reached
    flat = [op for ops in new_ops for op in ops]
    pad = -len(flat) % 4
    last = new_ops[-1]
    d.set_u32(last[0] + 0x18, d.u32(last[0] + 0x18) + pad)
    flat += [last[-1]] * pad
    lv._index(d)
    _, ops = list(md.op_lists(lv))[[x[0] for x in lists].index(main)]
    first, close = _macros_end(lv, ops)
    grow_in_place(lv, close, flat, first)
    problems = d.check()
    if problems:
        raise ValueError(f"macro port: {problems[:3]}")
    return d.to_bytes(), report


if __name__ == "__main__":
    a = iga.read(paths.giants("character", (sys.argv[1] if len(sys.argv) > 1 else "112_TitanLife") + ".bld"))
    level = next(e for e in a.entries if e.name == "level.bld")
    out, rep = port(level.data)
    for k, v in rep.items():
        print(f"{k}: {v}")
    print(f"{len(level.data)} -> {len(out)} bytes")
