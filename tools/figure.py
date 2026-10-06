"""Read Skylanders figure dumps (1 KB MIFARE images): decrypt and show the save fields.

Crypto and layout follow Dolphin's SkylanderFigure.cpp: block key = MD5(block0 + block1 + block index +
" Copyright (C) 2010 Activision. All Rights Reserved. "), AES-128-ECB; blocks 0-7 and sector trailers are
plain. Two save areas at 0x80 and 0x240; the newer one has area counter (area + 0x09) one higher.
"""
import hashlib
import struct
import sys

from Crypto.Cipher import AES

CONST = b" Copyright (C) 2010 Activision. All Rights Reserved. "


def decrypt(data: bytes) -> bytes:
    out = bytearray(data)
    for i in range(64):
        if i < 8 or (i + 1) % 4 == 0:
            continue
        key = hashlib.md5(data[0:16] + data[16:32] + bytes([i]) + CONST).digest()
        out[i * 16:(i + 1) * 16] = AES.new(key, AES.MODE_ECB).decrypt(data[i * 16:(i + 1) * 16])
    return bytes(out)


def areas(dec: bytes):
    a, b = dec[0x89], dec[0x249]
    newer = 0x80 if (a + 1) & 0xFF != b else 0x240
    return newer, (a, b)


def summary(path: str) -> dict:
    raw = open(path, "rb").read()
    dec = decrypt(raw)
    area, counters = areas(dec)
    nick = (dec[area + 0x20:area + 0x30] + dec[area + 0x40:area + 0x50]).decode("utf-16-le", errors="replace")
    return {
        "figure_id": struct.unpack_from("<H", dec, 0x10)[0],
        "variant": hex(struct.unpack_from("<H", dec, 0x1C)[0]),
        "area": hex(area), "counters": counters,
        "xp": int.from_bytes(dec[area:area + 3], "little"),
        "money": struct.unpack_from("<H", dec, area + 3)[0],
        "hero_level": struct.unpack_from("<H", dec, area + 0x5A)[0],
        "nickname": nick.split("\0")[0],
        "area_head": dec[area:area + 0x10].hex(" "),
    }


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p.replace("\\", "/").split("/")[-1], ascii(summary(p)))
