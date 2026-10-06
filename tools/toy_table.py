"""Print the supported-toy table: every call of 'Portal - Define Object Level Load' in Init_Setup.bld
(level load, item code, element, name), and the 'Portal - Define Alt Character' calls.

OpMacroParameter layout (verified): +0x1c parameter name, +0x20 kind (8 = reference, 9 = value),
+0x30 value: ValueRHSVariant (+0x08 -> RHSValueStack whose +0x20 is the literal) or RHSReferenceStack,
+0x38 -> the OpDefineMacro it belongs to.
"""
import bisect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iga  # noqa: E402
import paths  # noqa: E402
from igzdoc import IgzDoc  # noqa: E402


class Level:
    def __init__(self, archive_path):
        a = iga.read(archive_path)
        self._index(IgzDoc(max(a.entries, key=lambda e: len(e.data)).data))

    @classmethod
    def from_doc(cls, doc: IgzDoc):
        lv = cls.__new__(cls)
        lv._index(doc)
        return lv

    def _index(self, doc):
        self.doc = d = doc
        self.strf, self.ptrs = set(d.lists[0x0E]), set(d.lists[0x06])
        self.objs = sorted(d.lists[0x05])

    def type(self, o):
        return self.doc.types[self.doc.u32(o)]

    def obj_at(self, p):
        i = bisect.bisect_right(self.objs, p) - 1
        if i >= 0 and self.objs[i] <= p < self.objs[i] + self.doc.type_sizes[self.doc.u32(self.objs[i])]:
            return self.objs[i]
        return None

    def name_of(self, o):
        """First meaningful string field of an object."""
        d = self.doc
        for k in range(2, d.type_sizes[d.u32(o)] // 4):
            if o + 4 * k in self.strf:
                s = d.cstr(d.u32(o + 4 * k))
                if s not in ("parameter", "create variable||with|members", "use macro"):
                    return s
        return None

    def value(self, param):
        """Literal or referenced object of an OpMacroParameter, as text."""
        d = self.doc
        v = d.u32(param + 0x30)
        o = self.obj_at(v)
        if o is None:
            return None
        t = self.type(o)
        if t == "ValueRHSVariant":
            inner = self.obj_at(d.u32(o + 8))
            if inner is not None and self.type(inner) == "RHSValueStack":
                if d.u32(inner + 8) == 0:  # no reference path: a literal
                    return d.u32(inner + 0x20)
                return self.ref_path(inner)
            return t
        if t in ("RHSReferenceStack", "RHSValueStack"):
            return self.ref_path(o)
        return f"{t}('{self.name_of(o)}')"

    def ref_path(self, stack):
        """The chain of named objects a reference stack points through (its element buffer)."""
        d = self.doc
        n, buf = d.u32(stack + 8), d.u32(stack + 0x14)
        names = []
        for k in range(n):
            e = d.u32(buf + 4 * k)
            o = self.obj_at(e)
            if o is None:
                names.append(hex(e))
            elif self.type(o) == "StringInfo":
                names.append(f"'{d.cstr(d.u32(o + 8))}'")
            else:
                names.append(self.name_of(o) or self.type(o))
        return " . ".join(names)

    def calls(self, macro_name):
        """Group the OpMacroParameters of a macro into calls, in file order."""
        d = self.doc
        t_param = d.type_index("OpMacroParameter")
        rows, cur = [], {}
        for o in self.objs:
            if d.u32(o) != t_param:
                continue
            m = self.obj_at(d.u32(o + 0x38))
            if m is None or self.name_of(m) != macro_name:
                continue
            pname = d.cstr(d.u32(o + 0x1c))
            if pname in cur:
                rows.append(cur)
                cur = {}
            cur[pname] = (o, self.value(o))
        if cur:
            rows.append(cur)
        return rows


if __name__ == "__main__":
    lv = Level(sys.argv[1] if len(sys.argv) > 1 else paths.ssa("misc", "Init_Setup.bld"))
    for macro in ("Portal - Define Object Level Load", "Portal - Define Alt Character"):
        rows = lv.calls(macro)
        print(f"== {macro}: {len(rows)} calls")
        for r in rows:
            print("   " + "  ".join(f"{k}={v[1]}" for k, v in r.items()))
