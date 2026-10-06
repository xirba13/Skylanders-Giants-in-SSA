"""Print a script macro as readable statements: assignments with their expressions, conditions with their
comparison, macro calls with the called macro's name and arguments.

usage: python tools/script_print.py <archive .bld> "<macro name>" [--global <global.bld>] [--base 0x29]
       python tools/script_print.py <archive .bld> --list            (every macro defined in the archive)
       python tools/script_print.py <archive .bld> --range 100:180 [--oplist N]   (ops 100-180 of op list N)

Value expressions (verified on "Minion - Tune Minions", which computes the HP categories): a ValueRHSVariant is a
binary node, +0x08 left operand, +0x0C operator (0 +, 1 -, 2 *, 3 /; 0xFFFFFFFF: none, a plain value), +0x10
right operand; operands are value stacks or further nodes. OpCheckValue: +0x1C the tested value, +0x20 the
comparison (COMPARISONS), +0x24 the value it is compared with.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macro_dump as md  # noqa: E402
import minions  # noqa: E402
import paths  # noqa: E402
import script_edit  # noqa: E402
from macro_calls import used_macro  # noqa: E402
from toy_table import Level  # noqa: E402

ARITHMETIC = {0: "+", 1: "-", 2: "*", 3: "/"}
# OpCheckValue +0x20. The codes come in pairs whose second member negates the first (code ^ 1 negates):
# 0 !=, 1 ==; 2 <, 3 >=; 4 >, 5 <=. Settled by two tests of "Combat - Define Projectile"'s "is new-style projectile
# > 0" (code 4, true for Spyro's 1): code 5 (test 24) and code 2 (test 26) each made it false for 1 against 0, which
# stopped every Spyro's Adventure projectile, so neither is >=, and with the pairs 5 is <= and 2 is <. Consistent
# with "Save - Get/Set Minion Save Val" ("if limit to val cmp4 0: if val cmp4 limit to val: val := limit to val",
# 4 is >; getter path on "if set cmp1 0", 1 is ==) and with set counts tested == 0, != 0, > 0 and <= 0.
COMPARISONS = {0: "!=", 1: "==", 2: "<", 3: ">=", 4: ">", 5: "<="}
# Else: an OpAbstractFlow jumps over the ops its count covers, so "if X: A else: B" is a check whose block is A
# followed by an OpAbstractFlow whose count covers B, and B follows it ("if X: (nothing) else: B" is a check whose
# block is only the OpAbstractFlow). The flags in a check's control word (high half) do not tell: bit 3 is set on
# checks with and without an else. OpFlowBehavior 'flow end' with count 0xFFFF returns from the macro.
STACKS = ("RHSValueStack", "RHSReferenceStack", "ReferenceStack", "ValueStack")


def _float(word):
    return struct.unpack(">f", struct.pack(">I", word))[0]


class Printer:
    def __init__(self, lv, res):
        self.lv, self.res, self.d = lv, res, lv.doc

    def obj(self, field):
        """Object a pointer field points to, or None."""
        if field not in self.lv.ptrs or not self.d.u32(field):
            return None
        return self.lv.obj_at(self.d.u32(field))

    def expr(self, o):
        lv, d = self.lv, self.d
        if o is None:
            return "?"
        t = lv.type(o)
        if t == "ValueRHSVariant":
            left = self.expr(self.obj(o + 0x08)) if self.obj(o + 0x08) is not None else "0"
            op = d.u32(o + 0x0C)
            right = self.obj(o + 0x10)
            if op == 0xFFFFFFFF or right is None:
                return left
            return f"({left} {ARITHMETIC.get(op, f'op{op}')} {self.expr(right)})"
        if t in STACKS:
            if d.u32(o + 0x08) == 0 and t == "RHSValueStack":  # a literal: +0x1C class number, +0x20 value
                raw = d.u32(o + 0x20)
                return str(raw) if raw < 0x10000 or raw == 0xFFFFFFFF else f"{_float(raw):.6g}"
            return "[" + (self.res.value(o) or lv.ref_path(o) or t) + "]"
        return self.res.value(o) or f"{t}('{lv.name_of(o)}')"

    def statement(self, op):
        lv, d = self.lv, self.d
        t = lv.type(op)
        if t in ("OpSetValue", "OpSetReference"):
            return f"{self.expr(self.obj(op + 0x1C))} {':=' if t == 'OpSetValue' else ':=&'} " \
                   f"{self.expr(self.obj(op + 0x20))}"
        if t == "OpCheckValue":
            code = d.u32(op + 0x20)
            return f"if {self.expr(self.obj(op + 0x1C))} {COMPARISONS.get(code, f'cmp{code}')} " \
                   f"{self.expr(self.obj(op + 0x24))}"
        if t == "OpUseMacro":
            return f"call '{used_macro(lv, op)}'"
        if t == "OpMacroParameter":
            return f"  {d.cstr(d.u32(op + 0x1C))} = {self.expr(self.obj(op + 0x30))}"
        if t in ("OpMacroInterface", "OpFlowMacro", "OpFlowBuiltInBehavior", "OpAbstractFlow"):
            return None
        if t == "OpFlowBehavior" and d.u32(op + 0x18) & 0xFFFF == 0xFFFF:
            return "return"
        return md.describe(lv, self.res, op)


def macros(lv):
    """[(op list, ops, index)] of every OpDefineMacro."""
    out = []
    for lst, ops in md.op_lists(lv):
        for i, op in enumerate(ops):
            if lv.type(op) == "OpDefineMacro":
                out.append((lst, ops, i))
    return out


def else_ops(lv, ops):
    """Positions of the OpAbstractFlow ops that hold an else branch: those ending the block of a check (or of
    another conditional op: membership checks, find subset/variable, control)."""
    d = lv.doc
    out = set()
    for j, op in enumerate(ops):
        if lv.type(op) not in script_edit.COUNTING or lv.type(op) == "OpAbstractFlow":
            continue
        last = j + (d.u32(op + 0x18) & 0xFFFF)
        if last < len(ops) and lv.type(ops[last]) == "OpAbstractFlow":
            out.add(last)
    return out


def opens_block(lv, op):
    """Whether the ops after `op` are indented under it (a return's count 0xFFFF is not a block)."""
    return lv.type(op) in script_edit.COUNTING and not (
        lv.type(op) == "OpFlowBehavior" and lv.doc.u32(op + 0x18) & 0xFFFF == 0xFFFF)


def print_macro(lv, res, name):
    d = lv.doc
    pr = Printer(lv, res)
    found = next(((ops, i) for _, ops, i in macros(lv) if lv.name_of(ops[i]) == name), None)
    if found is None:
        raise SystemExit(f"{name!r} is not defined here")
    ops, i0 = found
    elses = else_ops(lv, ops)
    end = i0 + (d.u32(ops[i0] + 0x18) & 0xFFFF)
    closes = []
    for i in range(i0, min(end, len(ops) - 1) + 1):
        while closes and i > closes[-1]:
            closes.pop()
        op = ops[i]
        text = f"macro '{name}'" if i == i0 else ("else:" if i in elses else pr.statement(op))
        if text is not None:
            print(f"{i:5d} " + "  " * (len(closes) - (i in elses)) + text)
        if opens_block(lv, op) and i != i0:
            closes.append(i + (d.u32(op + 0x18) & 0xFFFF))


def print_range(lv, res, first, last, op_list=0):
    """Ops first..last of an archive's op list (the first by default), indented by the blocks that enclose them,
    each line prefixed with its enclosing macro when it is inside one."""
    d = lv.doc
    pr = Printer(lv, res)
    ops = list(md.op_lists(lv))[op_list][1]
    elses = else_ops(lv, ops)
    closes = []
    for i in range(0, min(last, len(ops) - 1) + 1):
        while closes and i > closes[-1][0]:
            closes.pop()
        op = ops[i]
        if i >= first:
            macro = next((name for end, name in reversed(closes) if name), None)
            text = "else:" if i in elses else (
                pr.statement(op) if lv.type(op) != "OpDefineMacro" else f"macro '{lv.name_of(op)}'")
            if text is not None:
                print(f"{i:5d} " + "  " * (len(closes) - (i in elses)) + text
                      + (f"    [{macro}]" if macro and i == first else ""))
        if opens_block(lv, op):
            closes.append((i + (d.u32(op + 0x18) & 0xFFFF),
                           lv.name_of(op) if lv.type(op) == "OpDefineMacro" else None))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archive")
    ap.add_argument("macro", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--range", help="FIRST:LAST op indexes to print instead of a macro")
    ap.add_argument("--oplist", type=int, default=0, help="which op list --range reads (a level can have several)")
    ap.add_argument("--global", dest="global_path", default=paths.ssa("permanent", "global.bld"))
    ap.add_argument("--base", type=lambda s: int(s, 0), default=minions.EXPORT_BASE)
    a = ap.parse_args()
    lv = Level(a.archive)
    if a.list:
        for _, ops, i in macros(lv):
            print(f"{i:6d} {lv.doc.u32(ops[i] + 0x18) & 0xFFFF:5d} ops  {lv.name_of(ops[i])}")
        return
    res = md.Resolver(lv, a.global_path, a.base)
    if a.range:
        first, last = (int(x) for x in a.range.split(":"))
        print_range(lv, res, first, last, a.oplist)
        return
    print_macro(lv, res, a.macro)


if __name__ == "__main__":
    main()
