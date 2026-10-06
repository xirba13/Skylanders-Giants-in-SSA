"""Script trace for Dolphin: Riivolution memory patches that make the script interpreter log ops through OSReport.

The interpreter's op loop (main.dol fn_800570B8: r3 the interpreter state, r4 the op list) calls each op's execute
function, the op's +0x0C, at two places: 0x80057160 (`lwz r27, 0xc(r27)`, the op in r27) and 0x80057224
(`lwz r26, 0xc(r26)`, the op in r26). Both pass r3 = the state's +0x00, the op whose block is running (the context:
a macro definition, a spawn's block, ...), and r4 = the state. Each of those instructions becomes a `bl` to a hook
at 0x80001800, the free area between the exception vectors and the OS globals that Riivolution and Gecko code use.
(The first try used the hole after .text2, which no section loads; it was zero when the game got there, apparently
reclaimed together with the one-time initialization code in .text2.) The hook saves every register, logs, restores
everything, runs the replaced instruction and returns. OSReport (0x8000B398) is an empty stub in the retail game;
Dolphin logs its calls (OSREPORT_HLE) when the symbol map %APPDATA%\\Dolphin Emulator\\Maps\\SSPP52.map names it
(docs/FORMATS.md, "Debugging in Dolphin"). Every line appears twice in Dolphin's log.

Only spawn ops ("clone||at|facing||cloned" and "clones") reach these two sites (test 27t: no macro call, displace,
set or check op ever did): the other ops are dispatched from the handlers that each op class installs at +0x0C,
so a trigger on one of those never fires. The spawn lines are enough to tell which branch of a macro spawned.

What it logs:
- "TRACE ctx=<context> op=<op> <label> | <macro name>": ops whose label starts with one of LABELS (a macro call
  only when the called macro's name starts with one of MACROS).
- "TRIGGER <n> op=<op> ctx=<context>" when trigger n's op runs, then "W ctx=<context> op=<op> <label> 1c=<+0x1C>"
  for each of the next WINDOW ops (every trigger restarts the count).
A trigger names an op by its place in a file (archive, op list, index). The hook recognizes it by the distances
from the op to the objects its pointer fields (FIELDS) point to: a file's objects load together, so the distances
hold wherever the file loads. Absolute addresses do not: where a character file loads depends on what was loaded
before it. Building checks that no other op of the files given has the same distances.

usage: python tools/script_trace.py [<archive.bld> <op list>:<index> ...]   (prints the memory patch lines;
       build_tests.py adds them to trace tests)
"""
import collections
import os
import re
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macro_dump as md  # noqa: E402
from toy_table import Level  # noqa: E402

CAVE, CAVE_END = 0x80001800, 0x80003000
OS_REPORT = 0x8000B398
SITES = {  # call site -> (register holding the op, the original instruction)
    0x80057160: (27, 0x837B000C),  # lwz r27, 0xc(r27)
    0x80057224: (26, 0x835A000C),  # lwz r26, 0xc(r26)
}
LABELS = ("use ", "clon", "disp")  # macro calls, spawns ("clone||at|facing||cloned"), displacements
MACROS = ("Combat - Fire", "Combat - Define Proj", "Combat - Projectile")  # macro calls logged: name prefixes
WINDOW = 3000
FIELDS = (0x1C, 0x20, 0x24)  # pointer fields a trigger signature uses; the first must be one of the op's
DEVKIT = next((p for p in (os.environ.get("DEVKITPPC", ""), r"C:\devkitPro\devkitPPC") if p and os.path.isdir(p)),
              r"C:\devkitPro\devkitPPC")  # the variable may hold an MSYS path (/opt/devkitpro/devkitPPC)
EXE = ".exe" if os.name == "nt" else ""


def _word(text):
    b = text.encode()[:4].ljust(4, b"\0")
    return struct.unpack(">I", b)[0]


def op_checks(lv, op):
    """[(field, distance)]: for each of the op's FIELDS that points into the op's own section, the distance from the
    op to the object it points to (mod 2**32)."""
    d = lv.doc
    out = []
    for off in FIELDS:
        v = d.u32(op + off)
        if op + off in lv.ptrs and v and v >> 24 == op >> 24:
            out.append((off, ((v & 0xFFFFFF) - (op & 0xFFFFFF)) & 0xFFFFFFFF))
    return out


def triggers(specs, others=()):
    """[(name, checks)] for specs [(archive, op list, index)]. Raises when an op has no +0x1C pointer, or when
    another op of the spec archives or of `others` (archives whose scripts run too) has the same distances."""
    levels = {}
    out = []
    for path, lst, i in specs:
        lv = levels.setdefault(path, Level(path))
        op = list(md.op_lists(lv))[lst][1][i]
        checks = op_checks(lv, op)
        if not checks or checks[0][0] != FIELDS[0]:
            raise ValueError(f"{path} {lst}:{i} ({lv.type(op)}): no {FIELDS[0]:#x} pointer")
        out.append((f"{os.path.basename(path)} {lst}:{i}", checks))
    for path in others:
        levels.setdefault(path, Level(path))
    by_first = collections.defaultdict(list)
    for lv in levels.values():
        for op in {op for _, ops in md.op_lists(lv) for op in ops}:
            fields = dict(op_checks(lv, op))
            if FIELDS[0] in fields:
                by_first[fields[FIELDS[0]]].append(fields)
    for name, checks in out:
        same = [f for f in by_first[checks[0][1]] if all(f.get(off) == dist for off, dist in checks)]
        if len(same) != 1:
            raise ValueError(f"trigger {name}: {len(same)} ops have its distances {checks}")
    return out


def assembly(trigs=(), window=WINDOW):
    """GNU as source of the hook (linked at CAVE)."""
    lines = [".section .text", ".globl _start", "_start:"]
    for site, (reg, _) in SITES.items():
        lines += [f"entry_{site:x}:",
                  "  stwu 1, -0xA0(1)", "  stw 0, 0x08(1)", "  mflr 0", "  stw 0, 0xA4(1)", "  mfcr 0",
                  "  stw 0, 0x0C(1)", "  stmw 3, 0x10(1)",
                  f"  mr 29, {reg}", "  bl body",
                  "  lmw 3, 0x10(1)", "  lwz 0, 0x0C(1)", "  mtcrf 0xFF, 0", "  lwz 0, 0xA4(1)", "  mtlr 0",
                  "  lwz 0, 0x08(1)", "  addi 1, 1, 0xA0",
                  f"  lwz {reg}, 0xC({reg})", "  blr"]
    # body: r29 = op, r3 = context (from the saved registers). Uses r3-r12 and r24-r31 freely (all restored).
    lines += ["body:",
              "  mflr 28",
              "  mr 30, 3",                       # context
              "  lis 25, counter@ha", "  addi 25, 25, counter@l"]
    if trigs:
        # the distance from the op to its first field's object, compared with each trigger's; candidates then
        # check their other fields, and go on scanning when one differs
        lines += [f"  lwz 9, {FIELDS[0]:#x}(29)", "  subf 9, 29, 9"]
        for k, (_, checks) in enumerate(trigs):
            dist = checks[0][1]
            lines += [f"scan_{k}:", f"  lis 10, {dist >> 16:#x}", f"  ori 10, 10, {dist & 0xFFFF:#x}",
                      "  cmpw 9, 10", f"  beq cand_{k}"]
        lines += [f"scan_{len(trigs)}:", "  b window"]
        for k, (_, checks) in enumerate(trigs):
            lines += [f"cand_{k}:"]
            for off, dist in checks[1:]:
                lines += [f"  lwz 11, {off:#x}(29)", "  subf 11, 29, 11", f"  lis 10, {dist >> 16:#x}",
                          f"  ori 10, 10, {dist & 0xFFFF:#x}", "  cmpw 11, 10", f"  bne scan_{k + 1}"]
            lines += [f"  li 24, {k}", "  b trigger"]
        lines += ["trigger:", f"  li 12, {window}", "  stw 12, 0(25)",
                  "  lis 3, tfmt@ha", "  addi 3, 3, tfmt@l", "  mr 4, 24", "  mr 5, 29", "  mr 6, 30", "  crclr 6",
                  "  bl OSReport"]
    # inside a window: log every op (label, and the raw word at +0x1C)
    lines += ["window:", "  lwz 12, 0(25)", "  cmpwi 12, 0", "  ble filters", "  subi 12, 12, 1", "  stw 12, 0(25)",
              "  lwz 6, 0x08(29)", "  cmpwi 6, 0", "  beq window_empty",
              "  oris 6, 6, 0x8000", "  mr 11, 6", "  bl mapped", "  bne window_log",
              "window_empty:", "  lis 6, empty@ha", "  addi 6, 6, empty@l",
              "window_log:", "  lis 3, wfmt@ha", "  addi 3, 3, wfmt@l", "  mr 4, 30", "  mr 5, 29",
              "  lwz 7, 0x1C(29)", "  crclr 6", "  bl OSReport", "  b out",
              "filters:",
              "  lwz 6, 0x08(29)",                # label (stored with the top bit cleared, like names)
              "  cmpwi 6, 0", "  beq out",
              "  oris 6, 6, 0x8000",
              "  mr 11, 6", "  bl mapped", "  beq out",
              # the label's first four characters, a byte at a time (strings need not be aligned)
              "  lbz 8, 0(6)", "  lbz 9, 1(6)", "  lbz 10, 2(6)", "  lbz 11, 3(6)",
              "  slwi 8, 8, 24", "  slwi 9, 9, 16", "  or 8, 8, 9", "  slwi 10, 10, 8", "  or 8, 8, 10",
              "  or 8, 8, 11"]
    for k, label in enumerate(LABELS):
        w = _word(label)
        lines += [f"  lis 10, {w >> 16:#x}", f"  ori 10, 10, {w & 0xFFFF:#x}", "  cmpw 8, 10",
                  f"  beq label_{k}"]
    lines += ["  b out"]
    for k, label in enumerate(LABELS):
        lines += [f"label_{k}:"]
        if label == "use ":
            lines += ["  li 7, 0",
                      "  lwz 11, 0x1C(29)", "  bl valid", "  beq out",       # ScriptGroupStack
                      "  lwz 11, 0x18(11)", "  bl valid", "  beq out",       # OpDefineMacro
                      "  lwz 7, 0x08(11)", "  cmpwi 7, 0", "  beq out", "  oris 7, 7, 0x8000",
                      "  mr 11, 7", "  bl mapped", "  beq out"]
            for m, prefix in enumerate(MACROS):
                lines += ["  mr 4, 7", f"  lis 5, prefix_{m}@ha", f"  addi 5, 5, prefix_{m}@l", "  bl starts",
                          "  bne log"]
            lines += ["  b out"]
        else:
            lines += ["  lis 7, empty@ha", "  addi 7, 7, empty@l", "  b log"]
    lines += ["log:",
              "  lis 3, fmt@ha", "  addi 3, 3, fmt@l", "  mr 4, 30", "  mr 5, 29",
              "  crclr 6", "  bl OSReport",
              "out:", "  mtlr 28", "  blr",
              # mapped: is r11 in MEM1 (0x80000000-0x81FFFFFF) or MEM2 (0x90000000-0x97FFFFFF)? cr0 eq = no
              "mapped:", "  srwi 12, 11, 24", "  cmplwi 12, 0x80", "  blt invalid", "  cmplwi 12, 0x81",
              "  ble yes", "  cmplwi 12, 0x90", "  blt invalid", "  cmplwi 12, 0x97", "  bgt invalid",
              "yes:", "  li 12, 1", "  cmpwi 12, 0", "  blr",
              # valid: r11 a mapped, word-aligned pointer (an object)? cr0 eq = no
              "valid:", "  andi. 12, 11, 3", "  bne invalid", "  b mapped",
              "invalid:", "  li 12, 0", "  cmpwi 12, 0", "  blr",
              # starts: does the string at r4 start with the string at r5? cr0 ne = yes
              "starts:", "  lbz 12, 0(5)", "  cmpwi 12, 0", "  beq starts_yes", "  lbz 10, 0(4)", "  cmpw 10, 12",
              "  bne starts_no", "  addi 4, 4, 1", "  addi 5, 5, 1", "  b starts",
              "starts_yes:", "  li 12, 1", "  cmpwi 12, 0", "  blr",
              "starts_no:", "  li 12, 0", "  cmpwi 12, 0", "  blr",
              '  .balign 4', 'counter:', '  .long 0',
              'fmt:', '  .asciz "TRACE ctx=%08x op=%08x %s | %s\\n"',
              'tfmt:', '  .asciz "TRIGGER %d op=%08x ctx=%08x\\n"',
              'wfmt:', '  .asciz "W ctx=%08x op=%08x %s 1c=%08x\\n"',
              'empty:', '  .asciz ""']
    for m, prefix in enumerate(MACROS):
        lines += [f"prefix_{m}:", f'  .asciz "{prefix}"']
    return "\n".join(lines) + "\n"


def build(trigs=()):
    """(hook blob, {entry name: address}) assembled and linked at CAVE with devkitPPC's binutils."""
    tools = os.path.join(DEVKIT, "bin")
    with tempfile.TemporaryDirectory() as tmp:
        src, obj, elf, raw = (os.path.join(tmp, n) for n in ("hook.s", "hook.o", "hook.elf", "hook.bin"))
        open(src, "w").write(assembly(trigs))
        subprocess.run([os.path.join(tools, "powerpc-eabi-as" + EXE), "-mgekko", "-o", obj, src], check=True)
        subprocess.run([os.path.join(tools, "powerpc-eabi-ld" + EXE), "-Ttext", f"{CAVE:#x}", "-e", "_start",
                        "--defsym", f"OSReport={OS_REPORT:#x}", "-o", elf, obj], check=True)
        subprocess.run([os.path.join(tools, "powerpc-eabi-objcopy" + EXE), "-O", "binary", elf, raw], check=True)
        syms = subprocess.run([os.path.join(tools, "powerpc-eabi-nm" + EXE), elf], check=True, capture_output=True,
                              text=True).stdout
        blob = open(raw, "rb").read()
    if CAVE + len(blob) > CAVE_END:
        raise ValueError(f"hook is {len(blob):#x} bytes, more than the {CAVE_END - CAVE:#x} free at {CAVE:#x}")
    entries = {m.group(2): int(m.group(1), 16) for m in re.finditer(r"([0-9a-f]{8}) \w (entry_\w+)", syms)}
    return blob, entries


def patches(trigs=()):
    """[(address, value bytes, original bytes or None)] for Riivolution <memory> lines."""
    blob, entries = build(trigs)
    out = [(CAVE, blob, None)]
    for site, (_, original) in SITES.items():
        target = entries[f"entry_{site:x}"]
        out.append((site, struct.pack(">I", 0x48000001 | ((target - site) & 0x03FFFFFC)),
                    struct.pack(">I", original)))
    return out


def memory_lines(trigs=()):
    lines = []
    for address, value, original in patches(trigs):
        extra = f' original="{original.hex()}"' if original else ""
        lines.append(f'    <memory offset="{address:#010x}" value="{value.hex()}"{extra} />')
    return lines


if __name__ == "__main__":
    args = sys.argv[1:]
    specs = [(args[k], *(int(x) for x in args[k + 1].split(":"))) for k in range(0, len(args), 2)]
    for line in memory_lines(triggers(specs) if specs else ()):
        print(line)
