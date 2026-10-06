"""Convert a Giants IGZ (version 6) into a Spyro's Adventure IGZ (version 5).

Per section that holds objects or Havok packfiles, the converter lays the content out again: objects of a changed
type get the Spyro's Adventure layout (TYPE_MAPS, each mapping derived from objects present in both games, see
docs/FORMATS.md), Havok packfiles are converted (tools/hkconvert.py), other bytes are copied. Every fixup moves with
its field, every pointer is relocated, and memory-size words next to pointers to converted packfiles get the new
size. Import indices into global.bld are remapped by the caller's import_map.
"""
import bisect
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hkconvert  # noqa: E402
import hkpack  # noqa: E402
from igzdoc import IgzDoc, OBJECTS, POINTERS  # noqa: E402

MEM_SIZES, MEM_BLOCKS = 0x0F, 0x0A


def ident(size, start=0):
    return {k: k for k in range(start, size, 4)}


def bit(v, n):
    return (v >> n) & 1


def as_float(w):
    return struct.unpack(">f", struct.pack(">I", w))[0]


def as_word(f):
    return struct.unpack(">I", struct.pack(">f", f))[0]


def physics_flags(w):
    """Giants' physics-animation bitfield (+0x20) as Spyro's Adventure's flag bytes (+0x28): bits 4, 9, 5."""
    return bit(w, 4) << 24 | bit(w, 9) << 16 | bit(w, 5) << 8


def full_colour(w):
    """Giants stores particle colours (RGBA) with R, G and B halved (rounded down); alpha is unchanged. 2g+1 (0 stays
    0) restores 26549 of the 31087 channels of the shared characters exactly, the rest are off by one."""
    out = w & 0xFF
    for shift in (24, 16, 8):
        g = (w >> shift) & 0xFF
        out |= (min(255, 2 * g + 1) if g else 0) << shift
    return out


APPEARANCE_COLOURS = (0x18, 0x1C, 0x20, 0x24, 0x70)
ONE = 0x3F800000  # 1.0f


def plain_spin(w):
    """(pivot U, pivot V, speed) words of a Giants tfbTransformUVAnimData that only spins: +0x08/+0x0C pivot, +0x10
    speed, scale 1 to 1 (+0x28-+0x34) with no scale speed (+0x20/+0x24), nothing else (every one on the converted
    Giants is like that; Chill's pulses its scale and Fright Rider's has a value at +0x18, and they would need more
    of Spyro's Adventure's fields worked out)."""
    if any(w(k) for k in (0x14, 0x18, 0x1C, 0x20, 0x24, 0x38, 0x3C)) or any(w(k) != ONE for k in range(0x28, 0x38, 4)):
        raise ValueError("tfbTransformUVAnimData does more than spin: "
                         + " ".join(f"{w(k):08x}" for k in range(0x08, 0x40, 4)))
    return w(0x08), w(0x0C), w(0x10)


# Giants type: (Spyro's Adventure type, size, moves {new offset: old offset}, computed {new offset: fn(word)})
TYPE_MAPS = {
    "igTextureAttr2": ("igTextureAttr2", 0x3C, ident(0x3C), {}),
    "igImage2": ("igImage2", 0x34, {**ident(0x0C), **{0x0C + 4 * k: 0x30 + 4 * k for k in range(10)}}, {}),
    "igVertexBuffer": ("igVertexBuffer", 0x28, ident(0x20), {}),
    "igVertexFormat": ("igVertexFormat", 0x40, ident(0x40), {}),
    "tfbAlphaTextureUnitIDAttr": ("tfbAlphaTextureUnitIDAttr", 0x1C,
                                  {0x00: 0x00, 0x04: 0x04, 0x08: 0x08, 0x0C: 0x0C, 0x10: 0x1C, 0x14: 0x10, 0x18: 0x18}, {}),
    "tfbPhysicsAnimation": ("tfbPhysicsAnimation", 0x30, ident(0x20), {0x28: lambda w: physics_flags(w(0x20))}),
    # same flag packing as tfbPhysicsAnimation; the fields after it move up by 4 (39 pairs)
    "physicsRandomAnimationNetwork": ("physicsRandomAnimationNetwork", 0x40,
                                      {**ident(0x20), 0x24: 0x24, **{0x2C + 4 * k: 0x28 + 4 * k for k in range(5)}},
                                      {0x28: lambda w: physics_flags(w(0x20))}),
    "AnimationInfo": ("AnimationInfo", 0x48, {**ident(0x30), 0x30: 0x34, 0x3C: 0x38, 0x40: 0x3C, 0x44: 0x40},
                      {0x38: lambda w: bit(w(0x30), 4) << 24 | bit(w(0x30), 5) << 16 | bit(w(0x30), 6) << 8}),
    "GeneratorMovementFields": ("GeneratorMovementFields", 0x58,
                                {**ident(0x18), **{0x20 + 4 * k: 0x1C + 4 * k for k in range(5)}, 0x38: 0x30,
                                 **{0x3C + 4 * k: 0x34 + 4 * k for k in range(6)}},
                                {0x18: lambda w: (w(0x18) >> 2) & 3, 0x1C: lambda w: (w(0x18) & 1) << 24,
                                 0x34: lambda w: (w(0x18) >> 4) & 3, 0x54: lambda w: ((w(0x18) >> 1) & 1) << 24}),
    "LightningGenerator": ("LightningGenerator", 0x6C,
                           {**ident(0x44), 0x48: 0x48, 0x4C: 0x4C, 0x50: 0x50, 0x58: 0x54, 0x5C: 0x58, 0x60: 0x5C,
                            0x64: 0x60, 0x68: 0x64},
                           {0x44: lambda w: w(0x44) & 7, 0x54: lambda w: w(0x44) >> 3}),
    # the same packing as LightningGenerator; Giants appended a float (+0x5C, mostly 100.0): dropped (163 of 191
    # pairs exact, the rest are counts Giants retuned)
    "RibbonGenerator": ("RibbonGenerator", 0x60, {**ident(0x44), 0x48: 0x48, 0x4C: 0x4C, 0x50: 0x50, 0x58: 0x54,
                                                  0x5C: 0x58},
                        {0x44: lambda w: w(0x44) & 7, 0x54: lambda w: w(0x44) >> 3}),
    # same size, changed fields (tools/converted_diff.py, 2099 pairs over the 37 shared characters): the count at
    # +0x1C became a half-word in Giants (upper half; the lower half takes +0x20's place), the next four fields
    # move up by 4, Giants added a float at +0x30 (always 1.0): dropped
    "GeneratorGenerationFields": ("GeneratorGenerationFields", 0x34,
                                  {**ident(0x1C), 0x24: 0x20, 0x28: 0x24, 0x2C: 0x28, 0x30: 0x2C},
                                  {0x1C: lambda w: w(0x1C) >> 16, 0x20: lambda w: w(0x1C) & 0xFFFF}),
    # Giants halves the RGB of the five colours and marks it with +0x98 bit 3 (2039 of 2099 pairs exact)
    "GeneratorAppearanceFields": ("GeneratorAppearanceFields", 0x9C, ident(0x9C),
                                  {**{off: (lambda o: lambda w: full_colour(w(o)))(off) for off in APPEARANCE_COLOURS},
                                   0x98: lambda w: w(0x98) & ~0x8}),
    # Giants sets bit 20 of the material flags on every material (343 of 343 pairs); no Spyro's Adventure one has it.
    # Bit 18 is Giants-only too (no shared character has it): Giants sets it on glowing effects (Hot Head's flame jet,
    # Tree Rex's glow, beams, light rays) that also have bit 30, which in Spyro's Adventure marks dynamically lit
    # materials (character bodies; its levels, skies and flames have it clear). Read as "self-illuminated", it
    # becomes bit 30 cleared (test 39: Hot Head's flame looked dim and brownish, lit like his body).
    "tfbMulti2BasicFlagsAttr": ("tfbMulti2BasicFlagsAttr", 0x14, ident(0x14),
                                {0x10: lambda w: w(0x10) & ~0x100000 & ~(0x40040000 if w(0x10) & 0x40000 else 0)}),
    # same size; +0x30 is _visemeSet (field names in main.dol: _node, _combinerPrototype, _boneMappingTable,
    # _visemeSet, _eyeBlink, _footprintData). Giants gives every character's main body its lip-sync mouth poses
    # there (31 of 31 shared characters, Tree Rex too); no Spyro's Adventure character has one, and the voice lines'
    # lip-sync data is dropped. Left empty (test 17: in game Tree Rex's skinned body vanished, menus were fine).
    "tfbPhysicsBody": ("tfbPhysicsBody", 0x40, {k: k for k in range(0, 0x40, 4) if k != 0x30}, {}),
    # mipmap LOD bias: Giants stores 2.5 times the value (5 of 5 pairs: -1 -> -2.5, -4 -> -10)
    "tfbMipmapBiasAttr": ("tfbMipmapBiasAttr", 0x14, ident(0x14), {0x10: lambda w: as_word(as_float(w(0x10)) / 2.5)}),
    "tfbSoundDataInfo": ("tfbSoundDataInfo", 0x2C, ident(0x24), {}),  # +0x24 (lip-sync animation) dropped
    "tfbLightInfo": ("tfbLightInfo", 0x108, {**ident(0xDC), **{0xDC + 4 * k: 0xE0 + 4 * k for k in range(11)}}, {}),
    "tfbMaterialTintAttr": ("tfbMulti2MaterialTintAttr", 0x14, ident(0x14), {}),
    "tfbDestinationAlphaAttr": ("igDestinationAlphaAttr", 0x14, ident(0x0C),
                                {0x0C: lambda w: bit(w(0x14), 24) << 16 | (w(0x10) & 0xFF) << 8,
                                 0x10: lambda w: bit(w(0x14), 24) << 24 | (w(0x10) & 0xFF) << 16}),
    # UV animations. Spyro's Adventure has one procedural kind; its data (fn_80090760 computes the texture matrix,
    # angles in radians): +0x08/+0x0C scale U/V, +0x10/+0x14 scroll speed, +0x18/+0x1C wobble amplitude, +0x20/+0x24
    # wobble frequency, +0x28/+0x2C wobble phase, +0x30/+0x34 rotation pivot, +0x38 rotation speed, +0x3C rotation
    # phase, +0x40/+0x44 rotation swing limits (back and forth when they differ). Giants splits it in two classes:
    # scroll data is the same up to +0x2C (shared characters: Sunburn, Camo identical), and transform data (a class
    # Spyro's Adventure's engine does not have: such tracks loaded without their update function and crashed the
    # renderer, test 36: Swarm's charged A attack) spins around +0x08/+0x0C at +0x10.
    "tfbScrollUVAnimTrack": ("tfbProceduralUVAnimTrack", 0x28, ident(0x28), {}),
    "tfbScrollUVAnimData": ("tfbProceduralUVAnimData", 0x48, ident(0x30), {}),
    "tfbTransformUVAnimTrack": ("tfbProceduralUVAnimTrack", 0x28, ident(0x28), {}),
    "tfbTransformUVAnimData": ("tfbProceduralUVAnimData", 0x48, ident(0x08),
                               {0x08: lambda w: ONE, 0x0C: lambda w: ONE, 0x30: lambda w: plain_spin(w)[0],
                                0x34: lambda w: plain_spin(w)[1], 0x38: lambda w: plain_spin(w)[2]}),
    # same size, moved field (tools/field_check.py): the bone index list (igIntList) is at +0xB4 in Giants and
    # +0xB0 in Spyro's Adventure, whose skinning code crashed reading the empty +0xB0 (test 14)
    "igBlendMatrixSelect": ("igBlendMatrixSelect", 0xC0, {**ident(0xB0), 0xB0: 0xB4, 0xB8: 0xB8, 0xBC: 0xBC}, {}),
    # same size, re-encoded material flags at +0x20 (tools/value_check.py): see technique_flags
    "tfbRuntimeTechniqueInstance": ("tfbRuntimeTechniqueInstance", 0x38, ident(0x38),
                                    {0x20: lambda w: technique_flags(w(0x20))}),
}

# tfbRuntimeTechniqueInstance +0x20 (material/shader flags), Giants value -> Spyro's Adventure value, the most
# common pairing among same-named materials of the 37 characters on both discs (320 pairs).
TECHNIQUE_FLAGS = {
    0x08000000: 0x08000100, 0x08001000: 0x08001100, 0x08001800: 0x08001902, 0x08001810: 0x08001910,
    0x08004000: 0x08004100, 0x08004010: 0x08004110, 0x08005004: 0x08005105, 0x08005800: 0x08005903,
    0x08040000: 0x08000140, 0x08040010: 0x08000150, 0x08040800: 0x08000940, 0x08040810: 0x08000950,
    0x08040C00: 0x08001D41, 0x08041000: 0x08001142, 0x08041010: 0x08001152, 0x08041800: 0x08001942,
    0x08041810: 0x08001950, 0x08044000: 0x08004140, 0x08044010: 0x08004150, 0x08044800: 0x08004940,
    0x08044810: 0x08004950, 0x08044A10: 0x08004B50, 0x08045000: 0x08005140, 0x08045004: 0x08005144,
    0x08045010: 0x08005150, 0x08045200: 0x08005340, 0x08045800: 0x08005940, 0x08045810: 0x08005950,
    0x08045A00: 0x08005B40, 0x08080000: 0x08000180, 0x08081800: 0x08001982, 0x08084000: 0x08004180,
    0x08084010: 0x08004190, 0x08084210: 0x08004390, 0x08084810: 0x08004990, 0x08085000: 0x08005180,
    0x08085004: 0x08005185, 0x080C0000: 0x080001C0, 0x080C0010: 0x080001D0, 0x080C0800: 0x080009C0,
    0x080C1010: 0x080011D2, 0x080C4000: 0x080001C0, 0x080C4010: 0x080041D0, 0x080C5000: 0x080051C0,
    0x080C5004: 0x080051C5, 0x08104000: 0x080041C0, 0x10040100: 0x10000140,
}


def technique_flags(g):
    """Material flags for values not seen on shared characters, by the rule that reproduces 312 of the 320
    pairs (all but bits 0-1, which hold per-material data Giants does not store): Giants bits 18-20, a value 0-4,
    become bits 6-7 (4 clamped to 3), bit 8 is always set, bit 2 brings bit 0, other bits are kept."""
    if g in TECHNIQUE_FLAGS:
        return TECHNIQUE_FLAGS[g]
    s = g & ~(7 << 18) & ~3
    s |= min((g >> 18) & 7, 3) << 6
    s |= 0x100
    if g & 0x4:
        s |= 1
    return s

# Memory-size words (record 0x0F) that the two games register differently for the same field and value:
# Spyro's Adventure lists RHSReferenceStack +0x10 and not PositionStack +0x10; Giants the other way round.
# The converted file follows Spyro's Adventure: {type: (offsets to add, offsets to remove)}.
MEM_SIZE_CONVENTIONS = {"RHSReferenceStack": ({0x10}, set()), "PositionStack": (set(), {0x10})}

# Vertex element (igVertexFormat +0x10 list, 12 bytes each): byte 0 type (0x2C ends the list), byte 6 pack-data
# offset, byte 7 pack type (0: not quantized)
ELEMENT_SIZE, ELEMENT_END = 12, 0x2C


def pack_data_length(elements):
    """Bytes of pack data (one word per quantized element: its fixed-point shift) a vertex buffer needs."""
    return max((e[6] + 4 for e in elements if e[0] != ELEMENT_END and e[7]), default=0)


def rewrite_blocks(doc: IgzDoc, new_data):
    """Replace data blocks ({block index: bytes}) of an IGZ and lay out each section involved again: anything before
    its first block kept, then its blocks in order, 32-byte aligned like the originals. Only for sections that hold
    nothing but data blocks (no objects, no pointer targets): the block records are their only references."""
    rec = doc.record(MEM_BLOCKS)
    blocks = [struct.unpack_from(">II", rec.body, 8 * k) for k in range(rec.count)]
    targets = {doc.u32(p) >> 24 for p in doc.lists.get(POINTERS, ()) if doc.u32(p)}
    body = bytearray(rec.body)
    for sec in sorted({blocks[b][1] >> 24 for b in new_data}):
        if sec in targets or any(o >> 24 == sec for o in doc.lists[OBJECTS]):
            raise ValueError(f"section {sec} holds more than data blocks")
        order = sorted((k for k, (_, enc) in enumerate(blocks) if enc >> 24 == sec), key=lambda k: blocks[k][1])
        old = bytes(doc.blobs[sec])
        out = bytearray(old[:blocks[order[0]][1] & 0xFFFFFF])
        for k in order:
            size, enc = blocks[k]
            off, n = enc & 0xFFFFFF, size & 0xFFFFFF
            data = new_data.get(k, old[off:off + n])
            out += bytes(-len(out) % 32)
            struct.pack_into(">II", body, 8 * k, (size & 0xFF000000) | len(data), (sec << 24) | len(out))
            out += data
        out += bytes(-len(out) % 32)
        doc.blobs[sec][:] = out
    rec.body = bytes(body)


class Item:
    __slots__ = ("old", "old_len", "kind", "new", "new_len", "data", "moves", "inverse", "type")

    def __init__(self, old, old_len, kind):
        self.old, self.old_len, self.kind = old, old_len, kind
        self.new = self.new_len = None
        self.data = b""
        self.moves = self.inverse = None
        self.type = None


FSB5_HEADER = 0x3C


def fsb5_length(blob, off):
    shdr, names, data = struct.unpack_from("<III", blob, off + 0x0C)
    return FSB5_HEADER + shdr + names + data


class Converter:
    """havok_templates: {"skeleton": Packfile, "animation": Packfile} from Spyro's Adventure, to convert Havok
    packfiles; sound_templates: tools/fsb.templates(), to re-wrap FSB5 sound banks. Data blocks are found as the
    targets of pointers (tfbPhysicsAnimation/tfbPhysicsBody +0x18, tfbSoundDataInfo +0x18) and recognised by their
    magic; each pointer's preceding word, when it holds the block's old length in its low 24 bits (0x90000000 |
    size), gets the new length."""

    def __init__(self, doc: IgzDoc, havok_templates=None, import_map=None, drop_objects=(), drop_ranges=(),
                 sound_templates=None):
        self.d = doc
        self.templates = havok_templates or {}
        self.sound_templates = sound_templates
        self.import_map = import_map or {}
        self.drop_objects = set(drop_objects)
        self.drop_ranges = sorted(drop_ranges)  # [(encoded start, length)] of raw bytes to leave out
        self.problems = []

    def _blob_kinds(self):
        kinds = {}
        if self.templates:
            kinds[hkpack.MAGIC] = (hkpack.length, self._convert_havok)
        if self.sound_templates:
            import fsb
            convert_sound = getattr(self, "sound_converter", None) or (lambda raw: fsb.convert(raw, self.sound_templates))
            kinds[b"FSB5"] = (fsb5_length, convert_sound)
        return kinds

    def _convert_havok(self, raw):
        pf = hkpack.parse(raw)
        kind = "skeleton" if any(c == "hkaSkeleton" for _, c in pf.objects()) else "animation"
        return hkconvert.convert(raw, self.templates[kind])

    def _find_blobs(self):
        """{(section, offset): (length, convert)} for data blocks that pointers reference."""
        d = self.d
        kinds = self._blob_kinds()
        found = {}
        if not kinds:
            return found
        for enc in d.lists.get(POINTERS, ()):
            v = d.u32(enc)
            sec, off = v >> 24, v & 0xFFFFFF
            if not v or sec >= len(d.blobs) or (sec, off) in found:
                continue
            blob = d.blobs[sec]
            for magic, (length, conv) in kinds.items():
                if bytes(blob[off:off + len(magic)]) == magic:
                    found[(sec, off)] = (length(bytes(blob), off), conv)
        return found

    # ---- types ----
    def _types(self):
        d = self.d
        names, sizes, tmap = [], [], {}
        for i, (t, s) in enumerate(zip(d.types, d.type_sizes)):
            name, size = (TYPE_MAPS[t][0], TYPE_MAPS[t][1]) if t in TYPE_MAPS else (t, s)
            if name not in names:
                names.append(name)
                sizes.append(size)
            tmap[i] = names.index(name)
        self.type_names, self.type_sizes, self.tmap = names, sizes, tmap

    # ---- layout ----
    def _items(self, sec):
        """Objects, packfiles and raw byte runs of one section, in order."""
        d = self.d
        blob = bytes(d.blobs[sec])
        objs = sorted((o & 0xFFFFFF) for o in d.lists[OBJECTS] if o >> 24 == sec)
        drops = [(s & 0xFFFFFF, n) for s, n in self.drop_ranges if s >> 24 == sec]
        cuts = []  # (start, length, kind, converter)
        for o in objs:
            size = d.type_sizes[d.u32((sec << 24) | o)]
            cuts.append((o, size, "drop" if ((sec << 24) | o) in self.drop_objects else "obj", None))
        for (bsec, off), (n, conv) in self.blobs.items():
            if bsec == sec:
                cuts.append((off, n, "pack", conv))
        for s, n in drops:
            cuts.append((s, n, "dropraw", None))
        cuts.sort(key=lambda c: c[0])
        items, pos = [], 0
        for start, n, kind, conv in cuts:
            if start < pos:
                raise ValueError(f"section {sec}: overlapping content at {start:#x}")
            if start > pos:
                items.append(Item(pos, start - pos, "raw"))
            it = Item(start, n, kind)
            it.type = conv
            items.append(it)
            pos = start + n
        if pos < len(blob):
            items.append(Item(pos, len(blob) - pos, "raw"))
        return items

    def _layout(self, sec, items):
        d = self.d
        blob = bytes(d.blobs[sec])
        cur = 0
        for it in items:
            if it.kind in ("drop", "dropraw"):
                it.new, it.new_len = None, 0
                continue
            if it.kind == "obj":
                enc = (sec << 24) | it.old
                tidx = d.u32(enc)
                tname = d.types[tidx]
                it.type = tname
                if tname in TYPE_MAPS:
                    _, size, moves, computed = TYPE_MAPS[tname]
                    words = {}
                    for new, old in moves.items():
                        words[new] = struct.unpack_from(">I", blob, it.old + old)[0]
                    for new, fn in computed.items():
                        words[new] = fn(lambda off: struct.unpack_from(">I", blob, it.old + off)[0])
                    data = bytearray(size)
                    for k, v in words.items():
                        struct.pack_into(">I", data, k, v)
                    it.moves = dict(moves)
                else:
                    size = it.old_len
                    data = bytearray(blob[it.old:it.old + size])
                    it.moves = ident(size)
                struct.pack_into(">I", data, 0, self.tmap[tidx])
                it.data, it.new_len = data, size
                it.inverse = {old: new for new, old in it.moves.items()}
            elif it.kind == "pack":
                it.data = it.type(blob[it.old:it.old + it.old_len])
                it.new_len = len(it.data)
            else:
                it.data = blob[it.old:it.old + it.old_len]
                it.new_len = it.old_len
            # objects and byte runs keep their position modulo 16 (buffers keep their alignment); packfiles,
            # which Havok reads in place, start on 16 bytes
            want = 0 if it.kind == "pack" else it.old % 16
            cur += (want - cur) % 16
            it.new = cur
            cur += it.new_len
        return cur

    def _build_maps(self):
        self._types()
        d = self.d
        self.sections = {}
        self.blobs = self._find_blobs()
        for sec in range(len(d.blobs)):
            has_objects = any(o >> 24 == sec for o in d.lists[OBJECTS])
            has_packs = any(bsec == sec for bsec, _ in self.blobs)
            has_drops = any(s >> 24 == sec for s, _ in self.drop_ranges)
            if not (has_objects or has_packs or has_drops):
                continue
            items = self._items(sec)
            total = self._layout(sec, items)
            self.sections[sec] = (items, [it.old for it in items], total)

    def addr(self, enc, field=False):
        """New encoded address of an old one, or None if it was dropped. field=True: a fixup's field location."""
        sec, off = enc >> 24, enc & 0xFFFFFF
        if sec not in self.sections:
            return enc
        items, starts, total = self.sections[sec]
        i = bisect.bisect_right(starts, off) - 1
        if i < 0:
            return enc
        it = items[i]
        rel = off - it.old
        if rel >= it.old_len:  # end of the section
            return (sec << 24) | total
        if it.kind in ("drop", "dropraw"):
            return None
        if it.kind == "obj":
            new = it.inverse.get(rel - rel % 4)
            if new is None:
                return None
            return (sec << 24) | (it.new + new + rel % 4)
        if it.kind == "pack":
            if rel != 0:
                self.problems.append(f"pointer into the middle of a packfile at {enc:#x}")
                return None
            return (sec << 24) | it.new
        return (sec << 24) | (it.new + rel)

    # ---- vertex pack data ----
    def _vertex_pack_data(self):
        """{block index: pack data} of the Giants vertex buffers. Spyro's Adventure stores a vertex buffer's pack
        data (the fixed-point shift of each quantized element: positions, normals, texture coordinates) right after
        the vertex data, in the same block; Giants keeps it in a separate buffer (igVertexBuffer +0x20 size word,
        +0x24 pointer). Without it the game takes the shifts from whatever follows the block (test 16: Tree Rex
        drawn huge and torn)."""
        d = self.d
        if "igVertexBuffer" not in d.types:
            return {}
        tidx = d.type_index("igVertexBuffer")
        if d.type_sizes[tidx] != 0x30:
            return {}
        out = {}
        for o in d.lists[OBJECTS]:
            if d.u32(o) != tidx or not d.u32(o + 0x24):
                continue
            fmt = d.u32(o + 0x18)
            count = (d.u32(fmt + 0x0C) & 0xFFFFFF) // ELEMENT_SIZE
            elements = [d.read(d.u32(fmt + 0x10) + ELEMENT_SIZE * k, ELEMENT_SIZE) for k in range(count)]
            pack = d.read(d.u32(o + 0x24), d.u32(o + 0x20) & 0xFFFFFF)
            need = pack_data_length(elements)
            block = d.u32(o + 0x14)
            if need != len(pack):
                self.problems.append(f"vertex buffer at {o:#x}: {len(pack)} bytes of pack data, its format needs {need}")
            if block in out:
                self.problems.append(f"vertex data block {block} is shared by two vertex buffers")
            out[block] = pack[:need]
        return out

    def _append_to_blocks(self, extra):
        """Append bytes to data blocks ({block index: bytes}) and lay out each section involved again: its blocks in
        order, 32-byte aligned like the originals (only the block records refer to them). Returns {block index:
        (size word, encoded offset)} for the block records."""
        d = self.d
        if not extra:
            return {}
        rec = d.record(MEM_BLOCKS)
        blocks = [struct.unpack_from(">II", rec.body, 8 * k) for k in range(rec.count)]
        targets = {self.old_values[p] >> 24 for p in self.old_lists.get(POINTERS, ()) if self.old_values[p]}
        moved = {}
        for sec in sorted({blocks[b][1] >> 24 for b in extra}):
            if sec in targets or sec in self.sections or any(o >> 24 == sec for o in self.old_lists[OBJECTS]):
                self.problems.append(f"section {sec} holds more than data blocks: vertex pack data not added")
                continue
            order = sorted((k for k, (_, enc) in enumerate(blocks) if enc >> 24 == sec), key=lambda k: blocks[k][1])
            old = bytes(d.blobs[sec])
            covered = bytearray(len(old))
            out = bytearray()
            for k in order:
                size, enc = blocks[k]
                off, n = enc & 0xFFFFFF, size & 0xFFFFFF
                if off % 32:
                    self.problems.append(f"data block {k} is not 32-byte aligned")
                covered[off:off + n] = b"\1" * n
                out += bytes(-len(out) % 32)
                data = old[off:off + n] + extra.get(k, b"")
                moved[k] = ((size & 0xFF000000) | len(data), (sec << 24) | len(out))
                out += data
            out += bytes(-len(out) % 32)
            if any(b and not c for b, c in zip(old, covered)):
                self.problems.append(f"section {sec} has data outside its blocks")
            d.blobs[sec][:] = out
        return moved

    # ---- output ----
    def run(self) -> IgzDoc:
        d = self.d
        # snapshot for convert_check
        self.old_lists = {t: list(lst) for t, lst in d.lists.items()}
        self.old_values = {enc: d.u32(enc) for t, lst in d.lists.items() if t != OBJECTS for enc in lst}
        self.old_types = list(d.types)
        self.old_type_of = {o: d.u32(o) for o in d.lists[OBJECTS]}
        self.pack_data = self._vertex_pack_data()
        self._build_maps()
        new_blobs = {}
        for sec, (items, _, total) in self.sections.items():
            out = bytearray(total)
            for it in items:
                if it.new is not None:
                    out[it.new:it.new + it.new_len] = it.data
            new_blobs[sec] = out
        new_lists = {}
        pointer_targets = {}
        for tag, lst in d.lists.items():
            mapped = []
            for enc in lst:
                if tag == OBJECTS:
                    if enc in self.drop_objects:
                        continue
                    n = self.addr(enc)
                else:
                    n = self.addr(enc, field=True)
                if n is None:
                    continue
                mapped.append(n)
                if tag == POINTERS:
                    pointer_targets[n] = d.u32(enc)
            new_lists[tag] = sorted(set(mapped))
        # relocate pointer values, fix memory sizes of converted packfiles
        def put(enc, value):
            blob = new_blobs.get(enc >> 24)
            if blob is None:
                d.set_u32(enc, value)
            else:
                struct.pack_into(">I", blob, enc & 0xFFFFFF, value)

        def get(enc):
            blob = new_blobs.get(enc >> 24)
            if blob is None:
                return d.u32(enc)
            return struct.unpack_from(">I", blob, enc & 0xFFFFFF)[0]
        self.resized = []  # (size field, old length, new length) for convert_check
        for field, old_value in pointer_targets.items():
            new_value = self.addr(old_value) if old_value else 0
            if new_value is None:
                self.problems.append(f"pointer at {field:#x} to dropped {old_value:#x}")
                new_value = 0
            put(field, new_value)
            key = (old_value >> 24, old_value & 0xFFFFFF)
            if old_value and key in self.blobs:
                items, starts, _ = self.sections[key[0]]
                it = items[bisect.bisect_right(starts, key[1]) - 1]
                size_word = get(field - 4)
                if size_word & 0xFFFFFF == it.old_len:
                    put(field - 4, (size_word & 0xFF000000) | it.new_len)
                    self.resized.append((field - 4, it.old_len, it.new_len))
                else:
                    self.problems.append(f"pointer at {field:#x} to a converted block has no size word before it")
        for sec, blob in new_blobs.items():
            d.blobs[sec][:] = blob
        self.blocks_moved = self._append_to_blocks(self.pack_data)
        # records
        for r in d.records:
            if r.tag == MEM_BLOCKS:
                body = bytearray(r.body)
                for k in range(r.count):
                    size, enc = struct.unpack_from(">II", body, 8 * k)
                    if k in self.blocks_moved:
                        size, n = self.blocks_moved[k]
                    else:
                        n = self.addr(enc)
                    struct.pack_into(">II", body, 8 * k, size, n if n is not None else 0)
                r.body = bytes(body)
            elif r.tag == 0x02 and self.import_map:
                body = bytearray(r.body)
                for k in range(r.count):
                    idx, h = struct.unpack_from(">II", body, 8 * k)
                    if (idx, h) in self.import_map:
                        struct.pack_into(">II", body, 8 * k, *self.import_map[(idx, h)])
                r.body = bytes(body)
            elif r.tag == 0x08:
                (root,) = struct.unpack_from(">I", r.body, 0)
                r.body = struct.pack(">I", self.addr(root)) + r.body[4:]
        # memory-size registrations as Spyro's Adventure writes them
        sizes = set(new_lists.get(MEM_SIZES, ()))
        self.mem_removed = set()
        for tname, (add, remove) in MEM_SIZE_CONVENTIONS.items():
            if tname not in self.type_names:
                continue
            tidx = self.type_names.index(tname)
            for o in new_lists.get(OBJECTS, ()):
                if get(o) != tidx:
                    continue
                for off in add:
                    if get(o + off) & 0x80000000:
                        sizes.add(o + off)
                for off in remove:
                    if o + off in sizes:
                        sizes.discard(o + off)
                        self.mem_removed.add(o + off)
        if MEM_SIZES in new_lists:
            new_lists[MEM_SIZES] = sorted(sizes)
        d.lists = new_lists
        d._packed_dirty = set(new_lists)
        d.types, d.type_sizes, d._types_dirty = self.type_names, self.type_sizes, True
        struct.pack_into(">II", d.header, 4, 5, 0)  # version 5, user version 0 (checked by Spyro's Adventure)
        d.meta_header = d.meta_header[:4] + struct.pack(">I", 5) + d.meta_header[8:]
        return d
