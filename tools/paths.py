"""Where the game files and Dolphin live.

Each value comes from an environment variable of the same name, else from paths.local.json in the repository root
(not tracked by git; see README.md), for example:

    {
      "SSA_ROOT": "D:/extracted/SSPP52/DATA",
      "GIANTS_ROOT": "D:/extracted/SKYZ52/DATA",
      "GIANTS_EN_ROOT": "D:/extracted/SKYP52/DATA"
    }

SSA_ROOT, GIANTS_ROOT and GIANTS_EN_ROOT are extracted disc partitions: the folder that holds sys/ and files/
(Dolphin: right-click the game > Properties > Filesystem > right-click the disc > Extract Entire Disc..., then use
its DATA folder). The two PAL Giants discs each carry three of Spyro's Adventure's six languages (text and voices):
Spanish, German and Italian come from the DE/ES/IT edition (SKYZ52, GIANTS_ROOT), English, French and Dutch from the
EN/FR/NL edition (SKYP52, GIANTS_EN_ROOT). Everything else (level data, textures, sounds) is taken from GIANTS_ROOT.

Optional: DOLPHIN_USER (Dolphin's user folder, default %APPDATA%/Dolphin Emulator) and SSA_DECOMP (a checkout of the
Spyro's Adventure decompilation project, used only by the research helpers that read its generated assembly).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = os.path.join(ROOT, "paths.local.json")
_local = {}
if os.path.exists(LOCAL):
    with open(LOCAL, encoding="utf-8") as _f:
        _local = json.load(_f)


def _setting(name, default=None):
    return os.environ.get(name) or _local.get(name) or default


SSA_ROOT = _setting("SSA_ROOT")
GIANTS_ROOT = _setting("GIANTS_ROOT")
GIANTS_EN_ROOT = _setting("GIANTS_EN_ROOT")
DOLPHIN_USER = _setting("DOLPHIN_USER", os.path.join(os.environ.get("APPDATA", ""), "Dolphin Emulator"))
SSA_DECOMP = _setting("SSA_DECOMP")


def _under(root, name, parts):
    if not root:
        raise SystemExit(f"{name} is not set: put it in {LOCAL} or the environment (see README.md)")
    return os.path.join(root, *parts)


def ssa_disc(*parts):
    """A path in Spyro's Adventure's extracted partition (sys/main.dol, files/, ticket.bin, ...)."""
    return _under(SSA_ROOT, "SSA_ROOT", parts)


def ssa(*parts):
    return ssa_disc("files", *parts)


def giants(*parts):
    return _under(GIANTS_ROOT, "GIANTS_ROOT", ("files",) + parts)


def giants_en(*parts):
    return _under(GIANTS_EN_ROOT, "GIANTS_EN_ROOT", ("files",) + parts)


def giants_discs(*parts):
    """The same file on both Giants discs, DE/ES/IT edition first."""
    return [giants(*parts), giants_en(*parts)]


def decomp(*parts):
    """A path in the decompilation project (SSA_DECOMP), for the research helpers."""
    if not SSA_DECOMP:
        raise SystemExit(f"SSA_DECOMP is not set: this helper reads the decompilation project's files (see {LOCAL})")
    return os.path.join(SSA_DECOMP, *parts)
