"""Field names of a Spyro's Adventure engine class, from main.dol's metadata tables.

Each class registers its fields from two parallel arrays in .data: field-type constructors (code addresses) and
field names (string addresses). Given one field name, this prints the whole name array it belongs to, in
declaration order (the order of the fields in the object), and the classes whose name tables contain it.

usage: python tools/dol_fields.py FIELD_NAME [FIELD_NAME ...]
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

DOL = paths.ssa_disc("sys", "main.dol")


class Dol:
    def __init__(self, path=DOL):
        self.d = open(path, "rb").read()
        self.offs = struct.unpack_from(">18I", self.d, 0)
        self.addrs = struct.unpack_from(">18I", self.d, 0x48)
        self.sizes = struct.unpack_from(">18I", self.d, 0x90)

    def a2f(self, a):
        for o, ad, s in zip(self.offs, self.addrs, self.sizes):
            if s and ad <= a < ad + s:
                return o + (a - ad)
        return None

    def f2a(self, f):
        for o, ad, s in zip(self.offs, self.addrs, self.sizes):
            if s and o <= f < o + s:
                return ad + (f - o)
        return None

    def u32(self, a):
        return struct.unpack_from(">I", self.d, self.a2f(a))[0]

    def cstr(self, a):
        f = self.a2f(a)
        if f is None:
            return None
        e = self.d.find(b"\0", f, f + 80)
        s = self.d[f:e] if e >= 0 else b""
        if len(s) < 2 or any(c < 32 or c > 126 for c in s):
            return None
        return s.decode()

    def string_address(self, text):
        out = []
        i = self.d.find(text.encode() + b"\0")
        while i >= 0:
            if i == 0 or self.d[i - 1] == 0:
                out.append(self.f2a(i))
            i = self.d.find(text.encode() + b"\0", i + 1)
        return out

    def name_table(self, ref):
        """The run of string pointers around the data word at ref."""
        a = ref
        while self.cstr(self.u32(a - 4)) is not None:
            a -= 4
        names = []
        while self.cstr(self.u32(a)) is not None:
            names.append(self.cstr(self.u32(a)))
            a += 4
        return names


def main():
    dol = Dol()
    for name in sys.argv[1:]:
        for sa in dol.string_address(name):
            pat = struct.pack(">I", sa)
            i = dol.d.find(pat)
            while i >= 0:
                ref = dol.f2a(i)
                print(f"{name} (string {sa:#x}) listed at {ref:#x}: {dol.name_table(ref)}")
                i = dol.d.find(pat, i + 1)


if __name__ == "__main__":
    main()
