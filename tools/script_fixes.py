"""Script fixes for converted Giants characters: places where a Giants character script relies on Giants'
global.bld macros doing something Spyro's Adventure's macros of the same name do not do.

Starting scale: Giants' "Minion - setup pre descriptions" sets the character's 'Starting Scale XYZ' from its
'default scale' parameter; Spyro's Adventure's version has no such parameter (parameters bind by name, so it is
ignored), and Spyro's Adventure characters set 'my Minion Description' . 'Starting Scale XYZ' in their own
script (Stump Smash: 150). "Minion - Run Minion" applies it to the in-game actor's scale, so without it a
converted Giants character is drawn at scale 0 in game (test 18: Tree Rex invisible, only his arm-spike sprites
showing, collapsed to his position; menus draw him through the display sprite and were fine).
set_starting_scale inserts the assignment right after the setup call, with the value the call passes.

The assignment's target path shares its elements with Tree Rex's own 'scale' reference, so those objects gain a
reference; IgzDoc.to_bytes recounts them (refcounts.py). Tests 19 and 20 crashed without that: the assignment
resolved the shared 'Starting Scale XYZ' stub first and released it to 0, destroying it under the 'scale' path.
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refcounts  # noqa: E402
import script_edit  # noqa: E402
from igzdoc import IgzDoc, OBJECTS, POINTERS  # noqa: E402
from macro_calls import used_macro  # noqa: E402
from opstream import op_list  # noqa: E402
from toy_table import Level  # noqa: E402

LITERAL_NUMBER = 6  # RHSValueStack +0x1C for a plain number (Stump Smash's 150; 7 marks true/false)


def _param(lv, ops, call, name):
    """The OpMacroParameter `name` of the macro call at ops[call]."""
    d = lv.doc
    for j in range(call + 1, min(len(ops), call + 200)):
        t = lv.type(ops[j])
        if t == "OpMacroParameter" and d.cstr(d.u32(ops[j] + 0x1C)) == name:
            return ops[j]
        if t == "OpFlowMacro":
            break
    return None


def _literal(lv, param):
    """(type word, value) of a parameter given as a literal, else None."""
    d = lv.doc
    v = lv.obj_at(d.u32(param + 0x30))
    if v is not None and lv.type(v) == "ValueRHSVariant":
        v = lv.obj_at(d.u32(v + 0x08))
    if v is None or lv.type(v) != "RHSValueStack" or d.u32(v + 0x08):
        return None
    return d.u32(v + 0x1C), d.u32(v + 0x20)


def _reference_elements(lv, param):
    """Objects a reference parameter's RHSReferenceStack names, in order."""
    d = lv.doc
    s = lv.obj_at(d.u32(param + 0x30))
    if s is not None and lv.type(s) == "ValueRHSVariant":
        s = lv.obj_at(d.u32(s + 0x08))
    if s is None or lv.type(s) not in ("RHSReferenceStack", "RHSValueStack"):
        return None
    n, buf = d.u32(s + 0x08), d.u32(s + 0x14)
    return [d.u32(buf + 4 * k) for k in range(n)]


def _sets_variable(lv, ops, variable):
    """Whether some OpSetValue's target path ends with `variable`."""
    d = lv.doc
    for op in ops:
        if lv.type(op) != "OpSetValue" or (op + 0x1C) not in lv.ptrs:
            continue
        lhs = lv.obj_at(d.u32(op + 0x1C))
        if lhs is None or lv.type(lhs) != "ValueStack":
            continue
        n, buf = d.u32(lhs + 0x08), d.u32(lhs + 0x14)
        if n and d.u32(buf + 4 * (n - 1)) == variable:
            return True
    return False


def set_starting_scale(data: bytes):
    """Insert "'my Minion Description' . 'Starting Scale XYZ' = <default scale>" after the character's call of
    "Minion - setup pre descriptions" when its script does not set the variable itself. Returns (bytes, what was
    done)."""
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    _, _, ops = op_list(lv)
    setup = next((i for i, op in enumerate(ops) if lv.type(op) == "OpUseMacro"
                  and used_macro(lv, op) == "Minion - setup pre descriptions"), None)
    if setup is None:
        return data, "no setup call"
    scale = _param(lv, ops, setup, "default scale")
    lit = _literal(lv, scale) if scale is not None else None
    if lit is None:
        return data, "setup call passes no literal default scale"
    # the variables, as the character's "Combat - Creature Definition" call names them for its 'scale'
    definition = next((i for i, op in enumerate(ops) if lv.type(op) == "OpUseMacro"
                       and used_macro(lv, op) == "Combat - Creature Definition"), None)
    path = _reference_elements(lv, _param(lv, ops, definition, "scale")) if definition is not None else None
    if not path or len(path) != 2 or {lv.name_of(o) for o in path} != {"my Minion Description",
                                                                        "Starting Scale XYZ"}:
        return data, f"unexpected scale path {path}"
    if _sets_variable(lv, ops, path[1]):
        return data, "the script sets Starting Scale XYZ itself"
    # templates: an existing "set value" whose target is a ValueStack and whose value is a literal
    template = next(op for op in ops if lv.type(op) == "OpSetValue" and (op + 0x1C) in lv.ptrs
                    and lv.obj_at(d.u32(op + 0x1C)) is not None
                    and lv.type(lv.obj_at(d.u32(op + 0x1C))) == "ValueStack"
                    and lv.obj_at(d.u32(op + 0x20)) is not None
                    and lv.type(lv.obj_at(d.u32(op + 0x20))) == "ValueRHSVariant"
                    and _literal_variant(lv, lv.obj_at(d.u32(op + 0x20))))
    ed = script_edit.Editor(lv)
    lhs = ed.clone(lv.obj_at(d.u32(template + 0x1C)))
    buf = d.append(script_edit.DEFAULT, b"".join(struct.pack(">I", o) for o in path) + bytes(4), align=8)
    for k in range(len(path)):
        d.add_fixup(POINTERS, buf + 4 * k)
    d.set_u32(lhs + 0x08, len(path))
    d.set_u32(lhs + 0x0C, len(path))
    d.set_u32(lhs + 0x10, 0x80000000 | 4 * len(path))
    d.set_u32(lhs + 0x14, buf)
    rhs = ed.clone(lv.obj_at(d.u32(template + 0x20)))
    stack = d.u32(rhs + 0x08)
    d.set_u32(stack + 0x1C, lit[0])
    d.set_u32(stack + 0x20, lit[1])
    new_ops = []
    for _ in range(COPIES):
        op = ed.clone(template)
        d.set_u32(op + 0x1C, lhs)
        d.set_u32(op + 0x20, rhs)
        new_ops.append(op)
    end = setup + (d.u32(ops[setup] + 0x18) & 0xFFFF) + 1
    grow_in_place(lv, end, new_ops, setup)
    problems = d.check()
    if problems:
        raise ValueError(f"starting scale: {problems[:3]}")
    out = d.to_bytes()
    return out, (f"Starting Scale XYZ = {lit[1]} set by {COPIES} ops inserted in place at op {end}; "
                 f"references recounted: {refcounts.summary(d, d.recounted)}")


# Ops are inserted in fours: 16 bytes keep every object after the op array on its alignment, and the op array
# stays where it is, directly followed by its first op object as in every retail file. (Test 19 rebuilt the
# array at the end of the section instead; its crash was the reference count above, not the move.)
COPIES = 4


def grow_in_place(lv, position, new_ops, sibling_start):
    """Insert op pointers into the main op array at `position` without moving the array: the section grows in
    place (IgzDoc.insert_bytes relocates everything after it). Enclosing blocks grow like script_edit.insert_ops."""
    d = lv.doc
    if len(new_ops) * 4 % 16:
        raise ValueError("insert ops in multiples of four")
    o, buf, ops = op_list(lv)
    for j in range(sibling_start):
        op = ops[j]
        if lv.type(op) not in script_edit.COUNTING:
            continue
        ctl = d.u32(op + 0x18)
        if j + (ctl & 0xFFFF) >= position - 1:
            if lv.type(op) == "OpAbstractFlow" and ops.count(op) > 1:
                # a jump shared with other positions (identical counts): this position gets a copy of its own,
                # which nothing else refers to (checks are referred to by the else-if tests after them; jumps not)
                op = script_edit.Editor(lv).clone(op)
                lv._index(d)
                d.set_u32(buf + 4 * j, op)
                ops[j] = op
            script_edit.check_unshared(ops, j)
            d.set_u32(op + 0x18, (ctl & 0xFFFF0000) | ((ctl & 0xFFFF) + len(new_ops)))
    gap = buf + 4 * position
    d.insert_bytes(gap >> 24, gap & 0xFFFFFF, 4 * len(new_ops))
    moved = {op: (op + 4 * len(new_ops) if op >> 24 == gap >> 24 and op >= gap else op) for op in new_ops}
    for k, op in enumerate(new_ops):
        d.set_u32(gap + 4 * k, moved[op])
        d.add_fixup(POINTERS, gap + 4 * k)
    o = o + 4 * len(new_ops) if o >= gap else o
    n = d.u32(o + 0x08) + len(new_ops)
    d.set_u32(o + 0x08, n)
    d.set_u32(o + 0x0C, n)
    d.set_u32(o + 0x10, 0x80000000 | 4 * n)
    lv._index(d)


def _literal_variant(lv, variant):
    d = lv.doc
    s = lv.obj_at(d.u32(variant + 0x08))
    return s is not None and lv.type(s) == "RHSValueStack" and not d.u32(s + 0x08) and not d.u32(s + 0x14)


# Stubs of renamed macros and structures. A character uses a global macro or structure through a local stub (an
# OpDefineMacro or OpDefineStructure with +0x1C = 1) holding its name (+0x08) and creation IDs (+0x20/+0x24, the
# same in both games for everything they share). Giants renamed a few it inherited; their IDs, and those of
# their parameters, are unchanged, but the game links stubs by name: Tree Rex's projectile calls ("Projectile -
# Fire Projectile", Spyro's Adventure's "Combat - Fire Projectile") and his projectile description's type
# ("Projectile - Projectile Description", "Combat - Projectile Description") were never linked, so his Z attack
# fired nothing (tests 21 and 22).
STUB_TYPES = ("OpDefineMacro", "OpDefineStructure")
_GLOBAL_DEFINITIONS = {}


def global_definitions(path=None):
    """{type: {(ID, ID): name}} of the macros and structures a global.bld defines (Spyro's Adventure's by
    default)."""
    import paths
    path = path or paths.ssa("permanent", "global.bld")
    if path not in _GLOBAL_DEFINITIONS:
        lv = Level(path)
        d = lv.doc
        out = {}
        for name in STUB_TYPES:
            t = d.type_index(name)
            out[name] = {(d.u32(o + 0x20), d.u32(o + 0x24)): lv.name_of(o)
                         for o in d.lists[OBJECTS] if d.u32(o) == t and d.u32(o + 0x1C) == 1}
        _GLOBAL_DEFINITIONS[path] = out
    return _GLOBAL_DEFINITIONS[path]


def rename_stubs(data: bytes, global_path=None):
    """Give every macro or structure stub whose name Spyro's Adventure's global.bld lacks, but whose IDs it defines,
    the name it has there. Returns (bytes, {old name: new name})."""
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    renamed = {}
    for type_name, by_id in global_definitions(global_path).items():
        if type_name not in d.types:
            continue
        names = set(by_id.values())
        t = d.type_index(type_name)
        for o in d.lists[OBJECTS]:
            if d.u32(o) != t or d.u32(o + 0x1C) != 1:
                continue
            name = lv.name_of(o)
            new = by_id.get((d.u32(o + 0x20), d.u32(o + 0x24)))
            if name in names or new is None or new == name:
                continue
            d.set_u32(o + 0x08, d.add_string(new))
            renamed[name] = new
    if not renamed:
        return data, renamed
    problems = d.check()
    if problems:
        raise ValueError(f"rename stubs: {problems[:3]}")
    return d.to_bytes(), renamed


# Controller. Giants turns a minion's controller off and on with "Movement - Activate/Deactivate Controller" (which
# also serves its newer movement system); Spyro's Adventure has no such macro. Its characters swap the actor's
# controller for the inactive one themselves (Stump Smash, entering his disabled state), which is what "Minion - Set
# Controller to Inactive" does for a minion description, and "Minion - Attempt to Restore Controller from Inactive"
# swaps it back. Tree Rex turns his controller off when entering the disabled state (dialogues and cutscenes; test
# 21: he could walk during them) and when his A attack winds up; Eye-Brawl also turns it back on. Each such call
# becomes a call of the matching Spyro's Adventure macro with the character's own minion description, taken from a
# call its script already makes (every Giant passes 'Minion Description' = 'my Minion Description' to one of the two);
# a character that never calls the macro gets a stub for it, a copy of one it does call with the other name and IDs.
# The call keeps its 'deactivate' parameter, which the new macro ignores like any parameter it does not have:
# removing it would mean shrinking the call's blocks, and retail scripts share identical op objects between
# positions (one OpMacroInterface serves 46 calls in Tree Rex's script), so a block count cannot be changed for one
# call alone.
CONTROLLER = "Movement - Activate/Deactivate Controller"
CONTROLLER_TARGETS = {1: "Minion - Set Controller to Inactive", 0: "Minion - Attempt to Restore Controller from Inactive"}


def _macro_group(lv, ops, name, template_names, ids):
    """The ScriptGroupStack through which the script calls `name`: an existing call's, or a copy of the group of a
    call of one of template_names whose stub is a copy renamed to `name` with IDs `ids`."""
    d = lv.doc
    for i, op in enumerate(ops):
        if lv.type(op) == "OpUseMacro" and used_macro(lv, op) == name:
            return d.u32(op + 0x1C)
    template = next(op for op in ops if lv.type(op) == "OpUseMacro" and used_macro(lv, op) in template_names)
    group = d.u32(template + 0x1C)
    ed = script_edit.Editor(lv)
    stub = ed.clone(d.u32(group + 0x18))
    d.set_u32(stub + 0x08, d.add_string(name))
    d.set_u32(stub + 0x20, ids[0])
    d.set_u32(stub + 0x24, ids[1])
    copy = ed.clone(group)
    n, buf = d.u32(group + 0x08), d.u32(group + 0x14)
    new = d.append(script_edit.DEFAULT, d.read(buf, 4 * n + 4), align=8)
    d.copy_words(buf, new, n + 1)
    d.set_u32(new, stub)
    d.set_u32(copy + 0x14, new)
    d.set_u32(copy + 0x18, stub)
    lv._index(d)
    return copy


def redirect_controller_calls(data: bytes, global_path=None):
    """Returns (bytes, what was done)."""
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    o, buf, ops = op_list(lv)
    calls = [i for i, op in enumerate(ops) if lv.type(op) == "OpUseMacro" and used_macro(lv, op) == CONTROLLER]
    if not calls:
        return data, "no calls"
    macros = global_macro_parameters(global_path)
    ids = {name: key for key, name in global_definitions(global_path)["OpDefineMacro"].items()}
    # the character's own minion description, as an argument of one of the target macros
    source = None
    for i, op in enumerate(ops):
        if lv.type(op) == "OpUseMacro" and used_macro(lv, op) in CONTROLLER_TARGETS.values():
            p = _param(lv, ops, i, "Minion Description")
            path = _reference_elements(lv, p) if p is not None else None
            if path and len(path) == 1 and lv.name_of(path[0]) == "my Minion Description":
                source = p
                break
    if source is None:
        raise ValueError("no call passes 'Minion Description' = 'my Minion Description' to copy")
    targets = {}
    for i in calls:
        minion, deactivate = _param(lv, ops, i, "minion"), _param(lv, ops, i, "deactivate")
        lit = _literal(lv, deactivate) if deactivate is not None else None
        if minion is None or lit is None or lit[1] not in CONTROLLER_TARGETS:
            raise ValueError(f"controller call at op {i}: deactivate is {lit}")
        targets[i] = CONTROLLER_TARGETS[lit[1]]
    groups = {name: _macro_group(lv, ops, name, CONTROLLER_TARGETS.values(), ids[name])
              for name in set(targets.values())}
    done = collections.Counter()
    for i, name in targets.items():
        op = ops[i]
        positions = [j for j, x in enumerate(ops) if x == op]
        if any(j not in targets or targets[j] != name for j in positions):
            op = script_edit.Editor(lv).clone(op)  # shared with calls that go elsewhere: this one gets its own
            lv._index(d)
            d.set_u32(buf + 4 * i, op)
            ops[i] = op
        group = groups[name]
        d.set_u32(op + 0x1C, group)
        p = next(x for x in macros[name] if x.name == "Minion Description")
        arg = script_edit.Editor(lv).clone(source)
        lv._index(d)
        d.set_u32(arg + 0x40, p.id_high)
        d.set_u32(arg + 0x44, p.id)
        d.set_u32(arg + 0x38, d.u32(group + 0x18))
        d.set_u32(buf + 4 * ops.index(_param(lv, ops, i, "minion"), i), arg)
        lv._index(d)
        done[name] += 1
    problems = d.check()
    if problems:
        raise ValueError(f"controller calls: {problems[:3]}")
    return d.to_bytes(), ", ".join(f"{n} calls of {CONTROLLER!r} now call {name!r}" for name, n in sorted(done.items()))


# Omitted parameters. Spyro's Adventure's editor writes every parameter into every call (the definition's default
# when the designer kept it), and the game uses only what the call passes: a parameter a call leaves out is 0
# (null for a reference); the defaults in the definition are never read. A converted Giants call leaves out the
# parameters Giants' macro does not have. Tree Rex's "Combat - Define Projectile" call has no 'is new-style
# projectile' (Spyro's Adventure's default 1; Giants has only that style), so his laser description got
# 'new projectile' 0 and "Combat - Fire Projectile" fired the lasers its other way, which no Spyro's Adventure
# content uses and where projectiles stay where they are fired (tests 21-27; in the test 27t trace Spyro's
# fireballs and Tree Rex's lasers take Fire's two branches). Each omitted parameter whose default is a literal
# other than 0 is passed with that default, in the slot of a parameter the call passes that the macro does not have
# (ignored there), so that no block changes size. The new parameter op is a copy of a value parameter of the same
# call (its class number, macro stub and macro ID are the file's own) with the name, ID, control word and literal
# of Spyro's Adventure's definition.
_GLOBAL_MACROS = {}


METAOBJECT = "metaobject"


def _name_strings(doc):
    """Record 1: the strings of the file's named references."""
    rec = doc.record(1)
    return [x.decode("latin1") for x in rec.body.split(b"\0")[:rec.count]]


def script_classes(doc):
    """The file's named references (record 3), by number. A class number (a field in fixup list 0x10, such as a
    literal's +0x1C) is an index into them, plain or with the top bit set. Each is a pair of record 1 strings,
    (namespace, name): ("metaobject", class) for a script class, given here as the class name; any other names an
    object, given as "namespace name" (Crusher's "SpriteInfo ^102_Shoulder_Gem_00_Legendary", global.bld's
    "ActorInfo ^metrics_master"). Class number n is record 1's string n + 1 only while no such object comes before
    it, so classes cannot be read off record 1 (test 37: a class number past the end of Crusher's references)."""
    strings = _name_strings(doc)
    rec = doc.record(3)
    out = []
    for k in range(rec.count):
        a, b = struct.unpack_from(">II", rec.body, 8 * k)
        out.append(strings[b] if strings[a] == METAOBJECT else f"{strings[a]} {strings[b]}")
    return out


def add_script_class(doc, classes, name):
    """Adds a reference to the script class name to doc (record 3, its strings to record 1) and to classes, the
    doc's script_classes. Returns its class number."""
    if " " in name:
        raise ValueError(f"{name!r} names an object, not a class")
    strings = _name_strings(doc)
    for s in (METAOBJECT, name):
        if s not in strings:
            strings.append(s)
    r1 = doc.record(1)
    body = b"".join(s.encode("latin1") + b"\0" for s in strings)
    r1.body = body + bytes(-len(body) % 4)
    r1.words[3] = len(strings)
    r3 = doc.record(3)
    n = r3.count
    r3.body = r3.body[:8 * n] + struct.pack(">II", strings.index(METAOBJECT), strings.index(name)) + r3.body[8 * n:]
    r3.words[3] = n + 1
    classes.append(name)
    return n


Param = collections.namedtuple("Param", "id_high id name control kind literal")
# A parameter of a macro definition: its 64-bit ID (+0x40, +0x44), name (+0x1C), control word (+0x18), value class
# (+0x24 when it is a class number, listed in fixup list 0x10: (flag, class name), as class numbers are per file;
# else None) and literal default ((class name, value) or None).


def class_name(classes, v):
    """(flag, class name) of a class-number field (script_classes), optionally with the top bit set."""
    n = v & 0x7FFFFFFF
    if n >= len(classes):
        raise ValueError(f"class number {v:#x} past the file's {len(classes)} named references")
    return v & 0x80000000, classes[n]


def value_class(doc, classes, param):
    """class_name of a parameter's +0x24 when that field is a class number, else None."""
    f = param + 0x24
    tags = getattr(doc, "_class_number_fields", None)
    if tags is None:
        tags = doc._class_number_fields = set(doc.lists.get(0x10, ()))
    return class_name(classes, doc.u32(f)) if f in tags else None


def class_number(doc, classes, flag_name):
    """The class-number field value of (flag, class name) in doc, whose script_classes are classes; a class the file
    lacks is added (add_script_class)."""
    flag, name = flag_name
    n = classes.index(name) if name in classes else add_script_class(doc, classes, name)
    return flag | n


def global_macro_parameters(path=None):
    """{macro name: [Param]} of the macros a global.bld defines (Spyro's Adventure's by default)."""
    import paths
    import macro_dump as md
    path = path or paths.ssa("permanent", "global.bld")
    if path not in _GLOBAL_MACROS:
        lv = Level(path)
        d = lv.doc
        classes = script_classes(d)
        out = {}
        for _, ops in md.op_lists(lv):
            for i, op in enumerate(ops):
                if lv.type(op) != "OpDefineMacro":
                    continue
                params = []
                for p in (ops[j] for j in _call_parameters(lv, ops, i)):
                    lit = _literal(lv, p)
                    params.append(Param(d.u32(p + 0x40), d.u32(p + 0x44), d.cstr(d.u32(p + 0x1C)), d.u32(p + 0x18),
                                        value_class(d, classes, p), (class_name(classes, lit[0])[1], lit[1]) if lit else None))
                name = lv.name_of(op)
                if len(params) > len(out.get(name, ())):
                    out[name] = params
        _GLOBAL_MACROS[path] = out
    return _GLOBAL_MACROS[path]


def _call_parameters(lv, ops, at):
    """Positions of the OpMacroParameter ops of the macro call (or definition) at ops[at]."""
    out = []
    for j in range(at + 1, min(len(ops), at + 1 + (lv.doc.u32(ops[at] + 0x18) & 0xFFFF))):
        t = lv.type(ops[j])
        if t == "OpMacroParameter":
            out.append(j)
        elif t == "OpFlowMacro":
            break
    return out


def fill_omitted_parameters(data: bytes, global_path=None):
    """Returns (bytes, what was done)."""
    import macro_dump as md
    macros = global_macro_parameters(global_path)
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    classes = script_classes(d)
    done = []
    for lst, ops in list(md.op_lists(lv)):
        buf = d.u32(lst + 0x14)
        for i, op in enumerate(ops):
            name = used_macro(lv, op) if lv.type(op) == "OpUseMacro" else None
            if name not in macros:
                continue
            known = {p.id for p in macros[name]}
            slots = _call_parameters(lv, ops, i)
            passed = {d.u32(ops[j] + 0x44) for j in slots}
            spare = [j for j in slots if d.u32(ops[j] + 0x44) not in known]
            for p in macros[name]:
                if p.id in passed or p.literal is None or p.literal[1] == 0:
                    continue
                if p.kind is None:
                    raise ValueError(f"{name!r} parameter {p.name!r} has no value class")
                kind = class_number(d, classes, p.kind)
                template = next((ops[j] for j in slots if d.u32(ops[j] + 0x24) == kind
                                 and _literal(lv, ops[j]) is not None), None)
                if not spare or template is None:
                    raise ValueError(f"{name!r} call at op {i} leaves out {p.name!r} and has no "
                                     f"{'template' if spare else 'spare slot'} for it")
                j = spare.pop(0)
                copy = script_edit.Editor(lv).clone(template)  # with private copies of its value objects
                lv._index(d)
                d.set_u32(copy + 0x18, p.control)
                d.set_u32(copy + 0x1C, d.add_string(p.name))
                d.set_u32(copy + 0x40, p.id_high)
                d.set_u32(copy + 0x44, p.id)
                stack = lv.obj_at(d.u32(copy + 0x30))
                if lv.type(stack) == "ValueRHSVariant":
                    stack = lv.obj_at(d.u32(stack + 0x08))
                d.set_u32(stack + 0x1C, class_number(d, classes, (0, p.literal[0])))
                d.set_u32(stack + 0x20, p.literal[1])
                replaced = d.cstr(d.u32(ops[j] + 0x1C))
                d.set_u32(buf + 4 * j, copy)
                lv._index(d)
                done.append(f"{name!r} at op {i}: {p.name!r} = {p.literal[1]} in the slot of {replaced!r}")
    if not done:
        return data, "none"
    problems = d.check()
    if problems:
        raise ValueError(f"omitted parameters: {problems[:3]}")
    return d.to_bytes(), done


# Redirected calls. Giants-only macros whose job a Spyro's Adventure macro does, closely enough: the stub takes that
# macro's name and IDs (stubs link by name), and each argument of every call through the stub is given the name and
# ID of the Spyro's Adventure parameter it maps to (same name unless renamed here); arguments with no counterpart
# are ignored there like any unknown argument. Argument ops are shared only between calls of the same macro (their
# IDs are the macro's own), so they are changed in place, and statements after a call that read an output argument
# keep reading it. Tree Rex plays his laser shots, smash whooshes and bird chirps through "Sound - Ultra Sound"
# (a sound picked from a set, or one sound, with an optional delay and fade-in) and his voice lines through
# "Sound - VO Request" (priorities, interruption, music ducking); neither exists in Spyro's Adventure, so all of
# them were silent (tests 21-28). "Sound - Play From Set" plays a sound from a set on an actor (Ultra Sound's
# delay and fade-in are lost; its one-sound calls, his charge wind loop, play nothing, which also keeps that loop
# from never being stopped: "Sound - Stop Loop" is Giants-only too). "Sound - Play Sound" plays one sound on the
# caller (priorities are lost).
REDIRECTS = {
    "Sound - VO Request": ("Sound - Play Sound", {"vo sound": "sound", "fail chance": "no-play chance"}),
}
# ("Sound - Ultra Sound" went to "Sound - Play From Set" in tests 29-30; it is a local copy of Giants' macro since
# test 31: tools/macro_port.py.)


def redirect_calls(data: bytes, redirects=None, global_path=None):
    """Returns (bytes, {Giants macro: what was done})."""
    import macro_dump as md
    redirects = REDIRECTS if redirects is None else redirects
    macros = global_macro_parameters(global_path)
    ids = {name: key for key, name in global_definitions(global_path)["OpDefineMacro"].items()}
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    classes = script_classes(d)
    lists = list(md.op_lists(lv))
    uses = collections.defaultdict(set)  # argument op -> macros whose calls pass it
    for _, ops in lists:
        for i, op in enumerate(ops):
            if lv.type(op) == "OpUseMacro":
                m = used_macro(lv, op)
                for j in _call_parameters(lv, ops, i):
                    uses[ops[j]].add(m)
    done = {}
    for giants, (ssa, renames) in redirects.items():
        stubs = [o for o in lv.objs if lv.type(o) == "OpDefineMacro" and lv.name_of(o) == giants]
        if not stubs:
            continue
        if len(stubs) != 1 or ssa not in macros or ssa not in ids:
            raise ValueError(f"redirect {giants!r} -> {ssa!r}: {len(stubs)} stubs")
        params = {p.name: p for p in macros[ssa]}
        rebound, ignored = 0, set()
        for arg, users in uses.items():
            if giants not in users:
                continue
            if users != {giants}:
                raise ValueError(f"an argument of {giants!r} is shared with calls of {sorted(users - {giants})}")
            name = d.cstr(d.u32(arg + 0x1C))
            p = params.get(renames.get(name, name))
            if p is None:
                ignored.add(name)
                continue
            kind = value_class(d, classes, arg)
            if kind != p.kind:
                raise ValueError(f"{giants!r} argument {name!r} is a {kind}, {ssa!r}'s {p.name!r} a {p.kind}")
            if p.name != name:
                d.set_u32(arg + 0x1C, d.add_string(p.name))
            d.set_u32(arg + 0x40, p.id_high)
            d.set_u32(arg + 0x44, p.id)
            rebound += 1
        stub = stubs[0]
        d.set_u32(stub + 0x08, d.add_string(ssa))
        d.set_u32(stub + 0x20, ids[ssa][0])
        d.set_u32(stub + 0x24, ids[ssa][1])
        done[giants] = f"now {ssa!r}: {rebound} argument ops rebound, ignored: {sorted(ignored)}"
    if not done:
        return data, done
    problems = d.check()
    if problems:
        raise ValueError(f"redirect calls: {problems[:3]}")
    return d.to_bytes(), done


# Launch particles. Giants' "Combat - Define Projectile" also takes post-process macros for a projectile's particles,
# which Spyro's Adventure's ignores (they are arguments its macro does not have). Tree Rex's laser passes one for its
# launch particle, the muzzle flash "112_Megaseed_muzzle" ("112 - LifeLaser Muzzle" attaches it to his own node and
# removes it 0.2 s later). In Spyro's Adventure that flash shows as a big yellow sphere: riding on every laser, as
# Spyro's Adventure's "Combat - Fire Projectile" leaves the launch particle attached to the projectile (tests 28-29),
# and over his hand when the macro's attachments were added after his Fire call (test 31). A launch particle that
# comes with a post-process macro is therefore left out: the call passes null, taken from another argument of the
# same call and value class (test 30: the lasers fly without the sphere).
NULL_IMPORT = ("null", "abstractscriptgroup")
DEFINE = "Combat - Define Projectile"


def _is_null(lv, param):
    """Whether a parameter's value is the engine's null (a one-element path naming null@abstractscriptgroup)."""
    import engine_names
    elements = _reference_elements(lv, param)
    if not elements or len(elements) != 1 or not elements[0] & 0x80000000:
        return False
    member, namespace = script_edit.import_of(lv, elements[0])
    return engine_names.import_name(member, namespace) == "@".join(NULL_IMPORT)


def drop_post_processed_launch_particles(data: bytes):
    """Returns (bytes, what was done)."""
    import macro_dump as md
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    classes = script_classes(d)
    lists = list(md.op_lists(lv))
    params = [op for _, ops in lists for op in set(ops) if lv.type(op) == "OpMacroParameter"]
    done = []
    for _, ops in lists:
        for i, op in enumerate(ops):
            if lv.type(op) != "OpUseMacro" or used_macro(lv, op) != DEFINE:
                continue
            args = {d.cstr(d.u32(ops[j] + 0x1C)): ops[j] for j in _call_parameters(lv, ops, i)}
            post, launch = args.get("launch particle post-process macro"), args.get("launch particle")
            if post is None or launch is None or _is_null(lv, post) or _is_null(lv, launch):
                continue
            kind = value_class(d, classes, launch)
            # a null of the same value class: in the same call, else anywhere in the script (Ninjini's call has none)
            null = next((p for p in list(args.values()) + params if p is not launch and _is_null(lv, p)
                         and value_class(d, classes, p) == kind), None)
            if null is None:
                raise ValueError(f"Define call at op {i}: no null {kind} argument to copy")
            d.set_u32(launch + 0x30, d.u32(null + 0x30))
            done.append(f"Define call at op {i}: launch particle left out")
    if not done:
        return data, "none"
    problems = d.check()
    if problems:
        raise ValueError(f"launch particles: {problems[:3]}")
    return d.to_bytes(), done


# Parameters by name. A macro Giants inherited and renamed keeps its creation IDs, and usually those of its
# parameters (rename_stubs), but not always: Giants' "Projectile - Add Homing Logic" ("Combat - Projectile Add Homing
# Logic") has Spyro's Adventure's seven parameter names with new IDs (0x147b2e00-06; Ninjini, Bouncer). Whether the
# game binds an argument to its parameter by ID or by name, an argument that matches a Spyro's Adventure parameter
# by name only gets that parameter's IDs here, so that it binds either way (and fill_omitted_parameters does not
# take it for an argument the macro does not have).
def rebind_parameters_by_name(data: bytes, global_path=None):
    """Returns (bytes, what was done)."""
    import macro_dump as md
    macros = global_macro_parameters(global_path)
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    lists = list(md.op_lists(lv))
    uses = collections.defaultdict(set)  # argument op -> macros whose calls pass it
    calls = []
    for _, ops in lists:
        for i, op in enumerate(ops):
            if lv.type(op) == "OpUseMacro":
                m = used_macro(lv, op)
                slots = _call_parameters(lv, ops, i)
                for j in slots:
                    uses[ops[j]].add(m)
                if m in macros:
                    calls.append((m, [ops[j] for j in slots]))
    done = collections.Counter()
    rebound = set()
    for m, args in calls:
        by_id = {p.id for p in macros[m]}
        by_name = {p.name: p for p in macros[m]}
        passed = {d.u32(a + 0x44) for a in args}
        for a in args:
            if a in rebound or d.u32(a + 0x44) in by_id:
                continue
            p = by_name.get(d.cstr(d.u32(a + 0x1C)))
            if p is None or p.id in passed:
                continue
            if uses[a] != {m}:
                raise ValueError(f"{m!r} argument {p.name!r} is shared with calls of {sorted(uses[a] - {m})}")
            d.set_u32(a + 0x40, p.id_high)
            d.set_u32(a + 0x44, p.id)
            passed.add(p.id)
            rebound.add(a)
            done[m] += 1
    if not done:
        return data, "none"
    problems = d.check()
    if problems:
        raise ValueError(f"rebind parameters: {problems[:3]}")
    return d.to_bytes(), {m: f"{n} argument ops given Spyro's Adventure's parameter IDs" for m, n in done.items()}


# Engine members Giants' engine has and Spyro's Adventure's lacks, as (member, namespace) name hashes: the import
# pairs of the converted characters that no Spyro's Adventure file uses (tools/import_pairs.py), confirmed in game.
# A script assignment to one crashes: fn_800588B8 (the assignment to an engine member) calls the accessors of the
# member's field descriptor, which the path resolver leaves null (test 35: Bouncer's "110 - Rocket Shutdown" sets
# 'attenuates' on the rumble sequence "Game - Player Rumble" returns; Giants' global.bld sets it on playing sounds
# too, so it is whether a playing sound fades with distance).
MISSING_MEMBERS = {(0x235BF273, 0xAD36AAE8): "attenuates"}
ASSIGNMENTS = ("OpSetValue", "OpSetReference")


def drop_missing_member_writes(data: bytes, missing=None):
    """Replace every assignment to a member in `missing` (default MISSING_MEMBERS) by a jump over no ops (an
    OpAbstractFlow of count 0, as in the retail scripts' empty else branches), in its slot of the op array, so the
    count of every enclosing block stays right. Raises if such a member is used any other way.
    Returns (bytes, what was done)."""
    import macro_dump as md
    missing = MISSING_MEMBERS if missing is None else missing
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    rec = d.record(0x02)
    handles = {0x80000000 | k: missing[pair] for k in range(rec.count)
               for pair in [struct.unpack_from(">II", rec.body, 8 * k)] if pair in missing}
    if not handles:
        return data, "none"
    stacks = {}
    handle_fields = set(d.lists.get(0x07, ()))
    for o in lv.objs:
        if lv.type(o) in md.STACKS and d.u32(o + 0x14):
            buf = d.u32(o + 0x14)
            for k in range(d.u32(o + 0x08)):
                if buf + 4 * k in handle_fields and d.u32(buf + 4 * k) in handles:
                    stacks[o] = handles[d.u32(buf + 4 * k)]
    replaced, writes = [], set()
    for code_list, ops in md.op_lists(lv):
        buf = d.u32(code_list + 0x14)
        noop = None
        for i, op in enumerate(ops):
            if lv.type(op) not in ASSIGNMENTS or lv.obj_at(d.u32(op + 0x1C)) not in stacks:
                continue
            if ops.count(op) > 1:
                raise ValueError(f"assignment at op {i} is shared by {ops.count(op)} positions")
            if noop is None:
                noop = next((o for o in ops if lv.type(o) == "OpAbstractFlow" and not d.u32(o + 0x18) & 0xFFFF),
                            None)
                if noop is None:
                    raise ValueError("no empty jump to reuse in this op list")
            d.set_u32(buf + 4 * i, noop)
            writes.add(op)
            replaced.append(f"op {i}: {stacks[lv.obj_at(d.u32(op + 0x1C))]}")
    # assignments to such a member, in an op list or left over from an earlier pass, are not reads
    writes |= {o for o in lv.objs if lv.type(o) in ASSIGNMENTS and lv.obj_at(d.u32(o + 0x1C)) in stacks}
    pointers = d.lists[POINTERS]
    readers = [hex(lv.obj_at(p)) for p in pointers if lv.obj_at(d.u32(p)) in stacks
               and lv.obj_at(p) not in writes and lv.obj_at(p) is not None]
    if readers:
        raise ValueError(f"members Spyro's Adventure lacks are read by {readers[:5]}")
    problems = d.check()
    if problems:
        raise ValueError(f"drop missing member writes: {problems[:3]}")
    return d.to_bytes(), f"{len(replaced)} assignments replaced by an empty jump ({', '.join(replaced)})"


# Velocity reads. Giants' "Movement - Get Velocity" returns 'returned velocity data', the 'velocity data' member of
# its creature description ('Combat - Creature Description - Movement Velocity Data', which Spyro's Adventure
# lacks), after copying five components of the actor's velocity vector into it (ops 664-668 of its definition, the
# branch for an actor that is not on Giants' mover list, which is every actor here). As a Giants-only macro the call
# did nothing, statements of its block included (Hot Head's A fire, Crusher's boulder target, ...); macro_port now
# defines it locally with an empty body, and each read of a returned member becomes the engine path Giants copies it
# from, on the call's actor (all 17 calls of the six Giants that use it pass 'my'):
# [returned velocity data . velocity length] -> [my . velocity . length@vectormeasurement].
GET_VELOCITY = "Movement - Get Velocity"
VELOCITY = (0x32741C32, 0x58709542)  # the actor's velocity vector (an engine member 118 Spyro's Adventure files use)
VECTOR = 0x37AF5C5E  # namespace of the vector measurement members
VELOCITY_MEMBERS = {"velocity length": 0x83D03615, "velocity heading": 0x9F481715, "velocity pitch": 0xBD324AB1,
                    "vertical difference": 0xECFB5226, "horizontal length": 0xFAA02963}


def _import_handle(doc, pair):
    """Handle (0x80000000 | record 2 entry) of an import pair, added when the file lacks it."""
    rec = doc.record(0x02)
    for k in range(rec.count):
        if struct.unpack_from(">II", rec.body, 8 * k) == pair:
            return 0x80000000 | k
    n = rec.count
    rec.body = rec.body[:8 * n] + struct.pack(">II", *pair) + rec.body[8 * n:]
    rec.words[3] = n + 1
    return 0x80000000 | n


def read_velocity_directly(data: bytes):
    """Returns (bytes, what was done)."""
    import macro_dump as md
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    handle_fields = set(d.lists.get(0x07, ()))
    pointers = set(d.lists[POINTERS])
    calls, returned, actor = 0, set(), None
    for _, ops in md.op_lists(lv):
        for i, op in enumerate(ops):
            if lv.type(op) != "OpUseMacro" or used_macro(lv, op) != GET_VELOCITY:
                continue
            calls += 1
            for j in _call_parameters(lv, ops, i):
                p = ops[j]
                name = d.cstr(d.u32(p + 0x1C))
                if name == "returned velocity data":
                    returned.add(p)
                elif name == "actor":
                    s = lv.obj_at(d.u32(p + 0x30))
                    if s is not None and lv.type(s) == "ValueRHSVariant":
                        s = lv.obj_at(d.u32(s + 0x08))
                    buf = d.u32(s + 0x14) if s is not None and len(_reference_elements(lv, p) or []) == 1 else 0
                    if buf not in handle_fields:
                        raise ValueError(f"{GET_VELOCITY} call at op {i}: 'actor' is not a single import")
                    pair = script_edit.import_of(lv, d.u32(buf))
                    if actor not in (None, pair):
                        raise ValueError(f"{GET_VELOCITY} calls pass different actors")
                    actor = pair
    if not calls:
        return data, "none"
    # the definition's own parameter op too (a call can reuse it)
    for o in lv.objs:
        if lv.type(o) == "OpMacroParameter" and d.cstr(d.u32(o + 0x1C)) == "returned velocity data":
            m = lv.obj_at(d.u32(o + 0x38)) if o + 0x38 in pointers else None
            if m is not None and lv.name_of(m) == GET_VELOCITY:
                returned.add(o)
    my, velocity = _import_handle(d, actor), _import_handle(d, VELOCITY)
    rewritten, other = collections.Counter(), []
    for o in list(lv.objs):  # every *Stack type keeps its path as (+0x08 count, +0x14 element buffer)
        if not lv.type(o).endswith("Stack") or not d.u32(o + 0x08) or o + 0x14 not in pointers:
            continue
        buf, n = d.u32(o + 0x14), d.u32(o + 0x08)
        uses = [k for k in range(n) if buf + 4 * k in pointers and lv.obj_at(d.u32(buf + 4 * k)) in returned]
        if not uses:
            continue
        if uses != [0]:
            other.append(f"{lv.type(o)}@{o:#x}")
            continue
        member = lv.obj_at(d.u32(buf + 4)) if n == 2 and buf + 4 in pointers else None
        name = d.cstr(d.u32(member + 0x1C)) if member is not None and lv.type(member) == "OpCreateVariable" else None
        if name not in VELOCITY_MEMBERS:
            other.append(f"{lv.type(o)}@{o:#x}")
            continue
        words = (my, velocity, _import_handle(d, (VELOCITY_MEMBERS[name], VECTOR)))
        new = d.append(buf >> 24, struct.pack(">IIII", *words, 0), align=4)  # with a spare word, as retail
        for k in range(3):
            d.add_fixup(0x07, new + 4 * k)
        d.set_u32(o + 0x08, 3)
        d.set_u32(o + 0x0C, 3)
        d.set_u32(o + 0x10, 0x80000000 | 12)
        d.set_u32(o + 0x14, new)
        rewritten[name] += 1
    if other:
        raise ValueError(f"other uses of '{GET_VELOCITY}' returned data: {other[:5]}")
    problems = d.check()
    if problems:
        raise ValueError(f"read velocity directly: {problems[:3]}")
    return d.to_bytes(), f"{calls} calls; reads rewritten: {dict(rewritten)}"


# Physics read off an actor definition. Bouncer's B aims each rocket with "Calc - Ballistics - Get Angle FROM
# Constant Velocity", passing [tfbActorInfo('110_RocketProjectile') . physics . gravity acceleration@actorphysics]:
# the gravity of the rocket's definition, its ActorParameters +0x30 (20 ft/s²; characters have 32, Hot Head's rising
# fire -5). Giants' engine answers that from the definition. Spyro's Adventure's evaluates such engine members only on
# actors in the world: its level scripts read them on placed tfbActorInfo objects, and none of its character files
# reads one off a definition (Bouncer's is the only such read in either game's character files). So the angle came
# out as if there were no gravity, and the rockets, launched flat from high above him, fell far from the target
# (test 38, with and without the upgrade that moves it). Each such read becomes a literal of the definition's value.
PHYSICS = (0x05562E58, 0x58709542)  # an actor's physics component
DEFINITION_PHYSICS = {(0x776BC7EB, 0xBE54191B): ("gravity acceleration", 0x30)}  # member: ActorParameters field


def _actor_definition(lv, name):
    """The tfbActorInfo named name in a level, else None."""
    return next((o for o in lv.objs if lv.type(o) == "tfbActorInfo" and lv.name_of(o) == name), None)


def literal_definition_physics(data: bytes, others=()):
    """others: Levels a named reference ("ActorInfo ^name") may name a definition of; Legendary Bouncer's reads its
    base Giant's rocket, 110_RobotGiant's 110_RocketProjectile, that way (its own is 110_RocketProjectileLegendary,
    with the same parameters). Returns (bytes, what was done)."""
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    ptrs = set(d.lists[POINTERS])
    handles = set(d.lists.get(0x07, ()))
    cls_fields = set(d.lists.get(0x10, ()))
    classes = script_classes(d)
    stacks = {}
    for o in lv.objs:
        if not lv.type(o).endswith("Stack") or d.u32(o + 0x08) != 3 or o + 0x14 not in ptrs:
            continue
        buf = d.u32(o + 0x14)
        if buf + 4 not in handles or buf + 8 not in handles or script_edit.import_of(lv, d.u32(buf + 4)) != PHYSICS:
            continue
        if buf in ptrs:
            where, actor = lv, lv.obj_at(d.u32(buf))
            if actor is None or lv.type(actor) != "tfbActorInfo":
                continue
            name = lv.name_of(actor)
        elif buf in cls_fields and class_name(classes, d.u32(buf))[1].startswith("ActorInfo ^"):
            name = class_name(classes, d.u32(buf))[1][len("ActorInfo ^"):]
            where = next((x for x in (lv, *others) if _actor_definition(x, name) is not None), None)
            if where is None:
                raise ValueError(f"named reference to actor {name!r}: in none of the files given")
            actor = _actor_definition(where, name)
        else:
            continue
        member = script_edit.import_of(lv, d.u32(buf + 8))
        if member not in DEFINITION_PHYSICS:
            raise ValueError(f"{name}: physics member {member[0]:#x}@{member[1]:#x} read off its definition")
        what, field = DEFINITION_PHYSICS[member]
        wd = where.doc
        params = where.obj_at(wd.u32(actor + 0xE0)) if actor + 0xE0 in where.ptrs else None
        if params is None or where.type(params) != "ActorParameters":
            raise ValueError(f"{name}: no ActorParameters")
        stacks[o] = (wd.u32(params + field), f"{name} {what}")
    if not stacks:
        return data, "none"
    template = next((o for o in lv.objs if lv.type(o) == "RHSValueStack" and not d.u32(o + 0x08)
                     and o + 0x1C in cls_fields and class_name(classes, d.u32(o + 0x1C))[1] == "FloatMeasurement"),
                    None)
    if template is None:
        raise ValueError("no FloatMeasurement literal to copy")
    size = d.type_sizes[d.u32(template)]
    holders, done = set(), []
    for o in list(lv.objs):
        if lv.type(o) != "ValueRHSVariant" or o + 0x08 not in ptrs or lv.obj_at(d.u32(o + 0x08)) not in stacks:
            continue
        value, what = stacks[lv.obj_at(d.u32(o + 0x08))]
        new = d.add_object(script_edit.DEFAULT, d.read(template, size), align=8)
        d.copy_words(template, new, size // 4)
        d.set_u32(new + 0x20, value)
        d.set_u32(o + 0x08, new)
        holders.add(o)
        done.append(f"{what} = {struct.unpack('>f', struct.pack('>I', value))[0]:g}")
    leftover = [hex(lv.obj_at(p)) for p in d.lists[POINTERS] if lv.obj_at(d.u32(p)) in stacks
                and lv.obj_at(p) is not None and lv.obj_at(p) not in holders]
    if leftover:
        raise ValueError(f"definition physics read outside a value holder: {leftover[:5]}")
    problems = d.check()
    if problems:
        raise ValueError(f"literal definition physics: {problems[:3]}")
    return d.to_bytes(), done


# Rockets launched from above their target. Bouncer's B fires each rocket from a 'scratch rocket positioning actor'
# spawned at the rocket's target and moved 75 ft up (and 5 ft aside), with the pitch "Calc - Ballistics - Get Angle
# FROM Constant Velocity" works out from the target's horizontal distance and vertical offset. In Giants the rockets
# rain down onto the target, so the angle must come out close to straight down there (about -85 degrees from that
# launch point). In Spyro's Adventure it sends them forward from high above, and they fell far beyond the target:
# test 38 (no gravity in the aim) and test 39 (the rocket's own 20 ft/s², farther still and slower). Spyro's
# Adventure's own volley, Flameslinger's arrows, measures its target through a remembered placement instead. The
# rocket call's pitch becomes -90, straight down from above the target.
ROCKET_DROPS = {("scratch rocket positioning actor", "Sky Rocket target"): -90.0}  # (location, target): pitch


def drop_rockets_from_above(data: bytes):
    """Returns (bytes, what was done)."""
    import macro_dump as md
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    ptrs = set(d.lists[POINTERS])
    cls_fields = set(d.lists.get(0x10, ()))
    classes = script_classes(d)

    def variable(param):
        els = _reference_elements(lv, param) or []
        o = lv.obj_at(els[0]) if len(els) == 1 else None
        return d.cstr(d.u32(o + 0x1C)) if o is not None and lv.type(o) == "OpCreateVariable" else None
    template = next((o for o in lv.objs if lv.type(o) == "RHSValueStack" and not d.u32(o + 0x08)
                     and o + 0x1C in cls_fields and class_name(classes, d.u32(o + 0x1C))[1] == "FloatMeasurement"),
                    None)
    done = []
    for _, ops in md.op_lists(lv):
        for i, op in enumerate(ops):
            if lv.type(op) != "OpUseMacro" or used_macro(lv, op) != "Combat - Fire Projectile":
                continue
            params = {d.cstr(d.u32(ops[j] + 0x1C)): ops[j] for j in _call_parameters(lv, ops, i)}
            key = (variable(params["location"]), variable(params["projected target actor"])) \
                if "location" in params and "projected target actor" in params else None
            if key not in ROCKET_DROPS:
                continue
            if template is None:
                raise ValueError("no FloatMeasurement literal to copy")
            v = lv.obj_at(d.u32(params["pitch"] + 0x30))
            if v is None or lv.type(v) != "ValueRHSVariant" or sum(1 for f in d.lists[POINTERS] if d.u32(f) == v) != 1:
                raise ValueError(f"Fire call at op {i}: its pitch value is not a value holder of its own")
            size = d.type_sizes[d.u32(template)]
            new = d.add_object(script_edit.DEFAULT, d.read(template, size), align=8)
            d.copy_words(template, new, size // 4)
            d.set_u32(new + 0x20, struct.unpack(">I", struct.pack(">f", ROCKET_DROPS[key]))[0])
            d.set_u32(v + 0x08, new)
            done.append(f"Fire call at op {i} from {key[0]!r}: pitch {ROCKET_DROPS[key]:g}")
    if not done:
        return data, "none"
    problems = d.check()
    if problems:
        raise ValueError(f"drop rockets from above: {problems[:3]}")
    return d.to_bytes(), done


# Fractional playback rates. Crusher starts the sequence his B gaze scrubs with a playback rate of 0.001, not the 0
# both games use everywhere else to stop a sequence, and then sets its position ('percent remaining'), which his
# steering reads back every frame: apparently a stopped sequence's position cannot be read back. Spyro's Adventure's
# scripts only ever set whole rates, as IntMeasurement literals (percent of normal speed: 0, 5, 10, 50, 100, 150,
# 200, ...), and with 0.001 his steering behaved as if the position read back were NaN: the test 39t trace shows
# both stick directions taking the same branch, one that needs the position to fail "percent remaining >= 1" right
# after it was set to 51. Where a script positions a sequence it has started with a fractional rate, the rate
# becomes 1, the smallest whole rate (the gaze lasts 4 s, so it drifts by 4% of its length at most; the steering
# sets it every frame). Sequences paused that way and never positioned (Tree Rex's head turn, Eye-Brawl's eyeball,
# Crusher's slider) keep their rate.
PLAYBACK_RATE = (0xD56CBB96, 0x3C43EF68)  # playback rate@sequence
PERCENT_REMAINING = (0xC718ADAE, 0x3C43EF68)  # percent remaining@sequence


def whole_playback_rates(data: bytes):
    """Returns (bytes, what was done)."""
    doc = IgzDoc(data)
    lv = Level.from_doc(doc)
    d = doc
    ptrs = set(d.lists[POINTERS])
    handles = set(d.lists.get(0x07, ()))
    cls_fields = set(d.lists.get(0x10, ()))
    classes = script_classes(d)

    def sequence_member(op):
        """(OpStartSequence, member import pair) an OpSetValue assigns, else None."""
        if op + 0x1C not in ptrs:
            return None
        target = lv.obj_at(d.u32(op + 0x1C))
        if target is None or d.u32(target + 0x08) != 2 or target + 0x14 not in ptrs:
            return None
        buf = d.u32(target + 0x14)
        first = lv.obj_at(d.u32(buf)) if buf in ptrs else None
        if first is None or lv.type(first) != "OpStartSequence" or buf + 4 not in handles:
            return None
        return first, script_edit.import_of(lv, d.u32(buf + 4))
    sets = [(o, sequence_member(o)) for o in lv.objs if lv.type(o) == "OpSetValue"]
    positioned = {m[0] for _, m in sets if m and m[1] == PERCENT_REMAINING}
    done = []
    for op, m in sets:
        if not m or m[1] != PLAYBACK_RATE or m[0] not in positioned or op + 0x20 not in ptrs:
            continue
        v = lv.obj_at(d.u32(op + 0x20))
        if v is None or lv.type(v) != "ValueRHSVariant" or d.u32(v + 0x0C) != 0xFFFFFFFF:
            continue
        lit = lv.obj_at(d.u32(v + 0x08))
        if lit is None or lv.type(lit) != "RHSValueStack" or d.u32(lit + 0x08) or lit + 0x1C not in cls_fields                 or class_name(classes, d.u32(lit + 0x1C))[1] != "FloatMeasurement":
            continue
        value = struct.unpack(">f", struct.pack(">I", d.u32(lit + 0x20)))[0]
        if not 0 < value < 1:
            continue
        copies = []
        for src in (v, lit):  # a private value holder and literal: the 0.001 is shared with other assignments
            size = d.type_sizes[d.u32(src)]
            new = d.add_object(script_edit.DEFAULT, d.read(src, size), align=8)
            d.copy_words(src, new, size // 4)
            copies.append(new)
        new_v, new_lit = copies
        d.set_u32(new_lit + 0x20, struct.unpack(">I", struct.pack(">f", 1.0))[0])
        d.set_u32(new_v + 0x08, new_lit)
        d.set_u32(op + 0x20, new_v)
        done.append(f"sequence started with rate {value:g} and positioned: rate 1")
    if not done:
        return data, "none"
    problems = d.check()
    if problems:
        raise ValueError(f"whole playback rates: {problems[:3]}")
    return d.to_bytes(), done
