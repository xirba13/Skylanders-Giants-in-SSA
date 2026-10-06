"""Compare the global-macro calls of a converted Giants character with Spyro's Adventure's macro interfaces.

A character script calls global.bld macros through a local stub (OpUseMacro +0x1C -> ScriptGroupStack +0x18 ->
OpDefineMacro named like the global macro); the call's OpMacroParameters bind to the macro's parameters by name.
For every macro the character calls, this prints the parameters its call passes that Spyro's Adventure's macro
does not have (ignored there) and the Spyro's Adventure parameters the call does not pass (0 or null at run time,
not the definition's default: script_fixes.fill_omitted_parameters), plus macros that Spyro's Adventure's
global.bld lacks altogether.

usage: python tools/macro_calls.py CHARACTER_BLD [GLOBAL_BLD]
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
from opstream import op_list  # noqa: E402,F401
import macro_dump as md  # noqa: E402
from toy_table import Level  # noqa: E402


def used_macro(lv, op):
    d = lv.doc
    if (op + 0x1C) not in lv.ptrs:
        return None
    g = lv.obj_at(d.u32(op + 0x1C))
    if g is None or lv.type(g) != "ScriptGroupStack":
        return None
    m = lv.obj_at(d.u32(g + 0x18))
    return lv.name_of(m) if m is not None else None


def interfaces(lv):
    """{macro name: [parameter names]} for the macros defined in a level's op streams."""
    d = lv.doc
    out = {}
    for _, ops in md.op_lists(lv):
        for i, op in enumerate(ops):
            if lv.type(op) != "OpDefineMacro":
                continue
            params = []
            for j in range(i + 1, min(len(ops), i + 400)):
                t = lv.type(ops[j])
                if t == "OpMacroParameter":
                    params.append(d.cstr(d.u32(ops[j] + 0x1C)))
                elif t == "OpFlowMacro":
                    break
            out.setdefault(lv.name_of(op), params)
    return out


def calls(lv):
    """[(macro name, [parameter names passed])] in op-stream order."""
    d = lv.doc
    out = []
    for _, ops in md.op_lists(lv):
        for i, op in enumerate(ops):
            if lv.type(op) != "OpUseMacro":
                continue
            name = used_macro(lv, op)
            if not name:
                continue
            params = []
            for j in range(i + 1, min(len(ops), i + 400)):
                t = lv.type(ops[j])
                if t == "OpMacroParameter":
                    params.append(d.cstr(d.u32(ops[j] + 0x1C)))
                elif t == "OpFlowMacro":
                    break
            out.append((name, params))
    return out


def main():
    char_path = sys.argv[1]
    global_path = sys.argv[2] if len(sys.argv) > 2 else paths.ssa("permanent", "global.bld")
    lv = Level(char_path)
    local = interfaces(lv)
    glob = interfaces(Level(global_path))
    seen = collections.OrderedDict()
    for name, params in calls(lv):
        seen.setdefault(name, set()).update(params)
    for name, passed in seen.items():
        if name in glob:
            want = glob[name]
            extra = [p for p in sorted(passed) if p not in want]
            missing = [p for p in want if p not in passed]
            if extra or missing:
                print(f"{name!r}: passes unknown {extra}; leaves out {missing}")
        elif name in local:
            continue  # the character's own macro
        else:
            print(f"{name!r}: not in Spyro's Adventure's global.bld")


if __name__ == "__main__":
    main()
