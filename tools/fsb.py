"""Re-wrap FMOD sound banks: Giants FSB5 (GCADPCM, one sample) -> Spyro's Adventure FSB4.

Both carry Nintendo DSP ADPCM ("GCADPCM": 8-byte frames of 14 samples, big-endian coefficients), so the audio
data is copied; only the container changes. Stereo data is interleaved every 2 bytes in both (checked: each
channel's first frame header, stored with its coefficients, sits at data offset 0 and 2).

FSB5 (little-endian header, 0x3C bytes for version 1): "FSB5", version, numSamples, sampleHeadersSize,
nameTableSize, dataSize, mode (6 = GCADPCM), 8 bytes, 16-byte hash, 8 bytes. Each sample header is a u64:
bit 0 extra chunks follow, bits 1-4 frequency index, bits 5-6 channels - 1, bits 7-33 data offset / 32,
bits 34-63 sample count; then chunks (u32: bit 0 more follow, bits 1-24 size, bits 25-31 type; 2 frequency,
7 DSP coefficients, 0x2E bytes per channel). Name table: one u32 offset per sample, then the names.

FSB4 (as in Spyro's Adventure's own files): "FSB4", numSamples, sampleHeadersSize, dataSize, version 0x40000,
mode 0x22, 8 zero bytes, 16-byte hash; sample header: u16 size, name[30], lengthSamples, compressedBytes,
loopStart, loopEnd, mode, defaultFrequency, then volume/pan/priority/channels/distances/variation copied from a
Spyro's Adventure file, then the DSP coefficients; data aligned to 32 bytes.
"""
import struct

FSB5_FREQUENCIES = [4000, 8000, 11000, 11025, 16000, 22050, 24000, 32000, 44100, 48000]
GCADPCM_FSB5 = 6


def parse_fsb5(blob: bytes) -> dict:
    if blob[:4] != b"FSB5":
        raise ValueError("not FSB5")
    version, n, shdr, names, data_size, mode = struct.unpack_from("<6I", blob, 4)
    if version != 1 or n != 1 or mode != GCADPCM_FSB5:
        raise ValueError(f"unsupported FSB5: version {version}, samples {n}, mode {mode}")
    base = 0x3C
    (bits,) = struct.unpack_from("<Q", blob, base)
    more = bits & 1
    freq = FSB5_FREQUENCIES[(bits >> 1) & 0xF]
    channels = ((bits >> 5) & 3) + 1
    data_off = ((bits >> 7) & ((1 << 27) - 1)) * 32
    samples = bits >> 34
    pos = base + 8
    coefs = None
    while more:
        (chunk,) = struct.unpack_from("<I", blob, pos)
        more, size, ctype = chunk & 1, (chunk >> 1) & 0xFFFFFF, chunk >> 25
        body = blob[pos + 4:pos + 4 + size]
        if ctype == 2:
            (freq,) = struct.unpack("<I", body)
        elif ctype == 7:
            coefs = body
        pos += 4 + size
    if coefs is None or len(coefs) != 0x2E * channels:
        raise ValueError("missing DSP coefficients")
    if channels not in (1, 2):
        raise ValueError(f"{channels} channels")
    name_base = base + shdr
    (name_off,) = struct.unpack_from("<I", blob, name_base)
    name = blob[name_base + name_off:blob.index(b"\0", name_base + name_off)]
    data_start = base + shdr + names
    data = blob[data_start + data_off:data_start + data_size]
    return {"frequency": freq, "channels": channels, "samples": samples, "coefs": coefs, "name": name,
            "data": data, "hash": blob[0x24:0x34]}


def build_fsb4(s: dict, templates: dict) -> bytes:
    """An FSB4 with sample s, laid out like the Spyro's Adventure file templates[channels] (one GCADPCM sample
    with that many channels)."""
    template = templates[s["channels"]]
    if template[:4] != b"FSB4":
        raise ValueError("template is not FSB4")
    t_size = struct.unpack_from("<H", template, 0x30)[0]
    if t_size != 0x50 + 0x2E * s["channels"]:
        raise ValueError("template does not match the channel count")
    head = bytearray(template[0x30:0x30 + t_size])
    name = s["name"][:29]
    head[2:0x20] = name + bytes(30 - len(name))
    # bytes actually holding samples: 8 per 14 samples per channel
    compressed = -(-s["samples"] // 14) * 8 * s["channels"]
    data = s["data"][:compressed]
    struct.pack_into("<IIII", head, 0x20, s["samples"], len(data), 0, s["samples"] - 1)
    struct.pack_into("<I", head, 0x34, s["frequency"])
    head[0x50:0x50 + 0x2E * s["channels"]] = s["coefs"]
    shdr = (-(0x30 + len(head)) % 32) + len(head)
    header = bytearray(template[:0x30])
    struct.pack_into("<III", header, 4, 1, shdr, len(data))
    header[0x20:0x30] = s["hash"]
    return bytes(header) + bytes(head) + bytes(shdr - len(head)) + data


def templates():
    """Spyro's Adventure FSB4 headers to copy: a mono voice line (Stump Smash) and a stereo sample (global.arc)."""
    import iga
    import paths
    mono = next(e.data for e in iga.read(paths.ssa("character", "027_Ent.arc")).entries if e.data[:4] == b"FSB4")
    stereo = next(e.data for e in iga.read(paths.ssa("permanent", "global.arc")).entries
                  if e.data[:4] == b"FSB4" and struct.unpack_from("<H", e.data, 0x6E)[0] == 2)
    return {1: mono, 2: stereo}


def convert(blob: bytes, tmpl: dict) -> bytes:
    return build_fsb4(parse_fsb5(blob), tmpl)
