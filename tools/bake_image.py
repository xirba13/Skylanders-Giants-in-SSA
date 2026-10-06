"""Bake a built Riivolution test into a copy of Spyro's Adventure's disc, for loaders without Riivolution
(USB Loader GX, WiiFlow, Dolphin without the patch).

usage: python tools/bake_image.py [test, default test41] [--wit PATH] [--iso] [--split]
       python tools/bake_image.py [test] --patch-dol IN.dol OUT.dol

Reads the test's <patch> from build/riivolution/riivolution/GiantsPortTests.xml (python tools/build_tests.py
builds it) and applies it to a copy of the extracted disc at paths.SSA_ROOT (DISC_PARTS: the layout of a full-disc
extraction by Dolphin or wit):

  <file disc=... external=...>     the file is replaced, or added (create="true")
  <memory offset=... value=... original=...>
                                   written into sys/main.dol at the file offset of that address, after checking
                                   the original value: the same bytes Riivolution patches in memory after loading
                                   the DOL

The copy is build/image/<game ID>/; files are only copied again when their size or time differ. Dolphin runs it
as it is (open its sys/main.dol). With Wiimms ISO Tools (wit, https://wit.wiimm.de) it also builds
build/image/<game ID>.wbfs, or .iso with --iso: wit re-encrypts the partition, rebuilds its hashes and fakesigns
it, which loaders running on a cIOS accept. The image keeps the disc's game ID, so it uses the same save.

A loader set to boot an alternate DOL ignores the image's main.dol, and with it the memory patch (the Giants then
stay on the portal's loading screen: character pool B is too small, as in test 13). --patch-dol writes the memory
patch into that DOL instead; the Skylanders Virtual Portal's sd:/SSPP52.dol leaves the patched word untouched (it
adds a section at 0x80001800 and five hooks).
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_tests  # noqa: E402
import paths  # noqa: E402

IMAGE = os.path.join(build_tests.ROOT, "build", "image")
# what wit and Dolphin read from an extracted Wii disc (paths.SSA_ROOT also holds other files, such as a disc image)
DISC_PARTS = ["sys", "files", "disc", "ticket.bin", "tmd.bin", "cert.bin", "h3.bin"]
WIT_PLACES = [r"C:\Program Files\Wiimm\WIT\wit.exe", r"C:\Program Files (x86)\Wiimm\WIT\wit.exe"]


def patch_of(test):
    """A test's patch in the built XML: ([(disc path, source file, create)], [(address, value, original)])."""
    xml = os.path.join(build_tests.OUT, "riivolution", build_tests.XML)
    patch = next((p for p in ET.parse(xml).getroot().findall("patch") if p.get("id") == f"gp_{test}"), None)
    if patch is None:
        raise SystemExit(f"{test} is not in {xml}; run python tools/build_tests.py first")
    files, memory = [], []
    for el in patch:
        if el.tag == "file":
            src = os.path.join(build_tests.OUT, *el.get("external").strip("/").split("/"))
            files.append((el.get("disc"), src, el.get("create") == "true"))
        elif el.tag == "memory":
            memory.append((int(el.get("offset"), 16), bytes.fromhex(el.get("value")),
                           bytes.fromhex(el.get("original"))))
        else:
            raise SystemExit(f"{test}: cannot bake <{el.tag}>")
    return files, memory


def dol_offset(dol, address):
    """File offset of a loaded address in a DOL (7 text and 11 data sections: offsets, addresses, sizes)."""
    offsets = struct.unpack_from(">18I", dol, 0x00)
    addresses = struct.unpack_from(">18I", dol, 0x48)
    sizes = struct.unpack_from(">18I", dol, 0x90)
    for off, start, size in zip(offsets, addresses, sizes):
        if size and start <= address < start + size:
            return off + address - start
    raise ValueError(f"{address:#010x} is in no section of main.dol")


def copy_disc(src, dst):
    """Make dst a copy of the extracted disc's DISC_PARTS (unchanged files are not copied again)."""
    os.makedirs(dst, exist_ok=True)
    for part in DISC_PARTS:
        a, b = os.path.join(src, part), os.path.join(dst, part)
        if os.path.isdir(a):
            build_tests.sync_tree(a, b)
        else:
            sa = os.stat(a)
            if not (os.path.exists(b) and os.path.getsize(b) == sa.st_size and int(os.path.getmtime(b)) ==
                    int(sa.st_mtime)):
                shutil.copy2(a, b)


def bake(test):
    """build/image/<game ID>/: the extracted disc with the test's patch applied. Returns (folder, report)."""
    src = paths.ssa_disc()
    with open(os.path.join(src, "sys", "boot.bin"), "rb") as f:
        game_id = f.read(6).decode("ascii")
    files, memory = patch_of(test)
    dst = os.path.join(IMAGE, game_id)
    copy_disc(src, dst)
    report = {"replaced": 0, "added": 0, "memory": []}
    for disc, source, create in files:
        target = os.path.join(dst, "files", *disc.strip("/").split("/"))
        if os.path.exists(target):
            report["replaced"] += 1
        elif create:
            report["added"] += 1
        else:
            raise SystemExit(f"{test}: {disc} is not on the disc and the patch does not create it")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
    dol_path = os.path.join(dst, "sys", "main.dol")
    dol, report["memory"] = patch_dol(open(dol_path, "rb").read(), memory)
    with open(dol_path, "wb") as f:
        f.write(dol)
    return dst, report


def patch_dol(dol, memory):
    """A DOL with the patch's <memory> writes applied at their file offsets, after checking each original value
    (a value already patched is left as it is). Returns (bytes, [what was done])."""
    dol, done = bytearray(dol), []
    for address, value, original in memory:
        at = dol_offset(dol, address)
        found = bytes(dol[at:at + len(original)])
        if found == value:
            done.append(f"{address:#010x}: already {value.hex()}")
            continue
        if found != original:
            raise SystemExit(f"DOL {address:#010x}: found {found.hex()}, the patch expects {original.hex()} "
                             "(another disc revision?)")
        dol[at:at + len(value)] = value
        done.append(f"{address:#010x} (file offset {at:#x}): {original.hex()} -> {value.hex()}")
    return bytes(dol), done


def find_wit(given=None):
    for p in [given, os.environ.get("WIT"), shutil.which("wit")] + WIT_PLACES:
        if p and os.path.isfile(p):
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("test", nargs="?", default="test41")
    ap.add_argument("--wit", help="path of wit.exe (default: WIT, PATH, the installer's folder)")
    ap.add_argument("--iso", action="store_true", help="build an .iso instead of a .wbfs")
    ap.add_argument("--split", action="store_true",
                    help="split the image into 4 GB parts, for copying it to a FAT32 drive by hand (Wii Backup "
                         "Manager splits on its own when it copies)")
    ap.add_argument("--patch-dol", nargs=2, metavar=("IN", "OUT"),
                    help="only write the patch's memory values into another DOL, such as an alternate DOL that "
                         "USB Loader GX boots instead of the image's main.dol (the Skylanders Virtual Portal's "
                         "sd:/SSPP52.dol), and save it as OUT")
    args = ap.parse_args()
    if args.patch_dol:
        source, target = args.patch_dol
        dol, done = patch_dol(open(source, "rb").read(), patch_of(args.test)[1])
        with open(target, "wb") as f:
            f.write(dol)
        print(f"{target}: {done}")
        return
    folder, report = bake(args.test)
    print(f"{folder}: {report['replaced']} files replaced, {report['added']} added; main.dol: {report['memory']}")
    wit = find_wit(args.wit)
    if not wit:
        print("wit not found: install Wiimms ISO Tools (https://wit.wiimm.de) or pass --wit, to build an image")
        return
    image = folder + (".iso" if args.iso else ".wbfs")
    command = [wit, "copy", folder, image, "--iso" if args.iso else "--wbfs", "--overwrite"]
    subprocess.run(command + (["--split"] if args.split else []), check=True)
    print(f"built {image}")


if __name__ == "__main__":
    main()
