"""Edit the supported-toy table in misc/Init_Setup.bld ('Portal - Define Object Level Load' calls).

Each call has 'level load' (handle to the load name), 'item code' (figure ID), optional 'element' and 'name'.
The item code literal lives in RHSValueStack +0x20, reached from the parameter via +0x30 -> ValueRHSVariant
-> +0x08 -> RHSValueStack.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from toy_table import Level  # noqa: E402

MACRO = "Portal - Define Object Level Load"


def literal_slot(lv: Level, param: int) -> int:
    """Encoded address of the u32 holding a value parameter's literal."""
    d = lv.doc
    variant = d.u32(param + 0x30)
    stack = d.u32(variant + 0x08)
    if lv.type(variant) != "ValueRHSVariant" or lv.type(stack) != "RHSValueStack" or d.u32(stack + 8) != 0:
        raise ValueError("parameter is not a plain literal")
    return stack + 0x20


def set_item_code(lv: Level, old: int, new: int) -> None:
    rows = [r for r in lv.calls(MACRO) if r.get("item code", (None, None))[1] == old]
    if len(rows) != 1:
        raise ValueError(f"expected one entry with item code {old}, found {len(rows)}")
    slot = literal_slot(lv, rows[0]["item code"][0])
    lv.doc.set_u32(slot, new)


def item_codes(lv: Level) -> list:
    return [r["item code"][1] for r in lv.calls(MACRO) if "item code" in r]
