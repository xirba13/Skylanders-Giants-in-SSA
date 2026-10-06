# File formats

Findings from Spyro's Adventure (SSPP52, PAL) and Giants (SKYZ52, the DE/ES/IT PAL edition; SKYP52, the EN/FR/NL
PAL edition, only for its text and voices). "Verified" means checked against the retail files by the tools in this
repository; anything else is marked as a hypothesis.

## Disc layout

| | Spyro's Adventure | Giants |
|---|---|---|
| Character files | `character/<figure ID>_<name>.arc` + `.bld` | same |
| Character registry | `permanent/global.bld`: 38 objects named `MinionLoad_<id>_<name>` | same file: 68, including all 8 Giants |
| Language packs per character | EN, FR, ES, NL, DE, IT (inside the character `.bld`) | ES, DE, IT on SKYZ52; EN, FR, NL on SKYP52 |

Neither executable contains character file names: the figure ID to character mapping is data (verified by
string search of both `main.dol` files).

The character list is a script data set in `permanent/global.bld` (the large `level.bld` entry):

- `ScriptSet 'Minion_Loads'`: a `ScriptSetList` of 38 `StringInfo` values, `MinionLoad_000_AirDragon` ...
  `MinionLoad_032_Cynder`, `MinionLoad_099_DebugMinion`, then the 5 variants. ID 028 is absent, so list
  position is not the figure ID.
- `ScriptSet 'Minion_Loads_Legendary'`: the 5 variants again.
- The list names are keys, not file names: each one is translated through the language packs (next section),
  and the translation is the file name (`MinionLoad_004_RockDragon` -> `004_Rock_Dragon`).

The 8 Giants on the Giants disc:

| Giant | Figure ID | Files | Registry entry |
|---|---|---|---|
| Swarm | 101 | `101_BugmanGiant` | `MinionLoad_101_BugmanGiant` |
| Crusher | 102 | `102_Titan_Earth` (+ `_Alt`) | `MinionLoad_102_EarthTitan` (+ Legendary) |
| Hot Head | 104 | `104_OilBlazer` | `MinionLoad_104_OilBlazer` |
| Thumpback | 107 | `107_Whale` | `MinionLoad_107_Whale` |
| Ninjini | 109 | `109_Djini` (+ `_Alt`) | `MinionLoad_109_Djini` (+ Legendary) |
| Bouncer | 110 | `110_RobotGiant` (+ `_Legendary`) | `MinionLoad_110_RobotGiant` (+ Legendary) |
| Tree Rex | 112 | `112_TitanLife` (+ `_Alt`) | `MinionLoad_112_TitanLife` (+ Legendary) |
| Eye-Brawl | 114 | `114_Mummy` | `MinionLoad_114_Mummy` |

## Supported-toy table (the "toy can't be used" gate)

Verified by tests 5 and 6: adding `MinionLoad_112_TitanLife` to `Minion_Loads` (and even adding
`character/112_TitanLife.*` files) does not make a Tree Rex figure usable; the game shows "Un juguete del Portal
of Power no se puede usar con este juego" and Dolphin's file log shows no file access at all. `Minion_Loads` is
only used by `SaveGame_Init.ai`.

The gate is script logic, readable because ops carry their labels:

- `PortalManager.ai`: "Portal Control - Portal - Logic - 235 - Condition - Toy Can't Be Used". For each toy on
  the portal it calls the macro "Portal - Get Object Level Info" with `prodid` = the toy's `toy id`, and the toy
  is refused when no level info comes back.
- That macro (defined in `PortalControl.ai`) searches the "object level loads" set of
  "Portal - RFID Level Load Hint" records.
- The records are created at boot by `misc/Init_Setup.bld` (`Init_Setup.lvl`): macro
  "Portal - Set Up Object Level Loads" calls "Portal - Define Object Level Load" once per toy with parameters
  `level load`, `item code` (the figure ID), `element` (0 Magic, 1 Water, 2 Air, 3 Undead, 4 Tech, 5 Fire,
  6 Earth, 7 Life) and `name`. "Portal - Define Alt Character" maps base loads to Dark/Legendary loads.
- 56 entries: 0-32, 999, 404, 416, 419, 430, 200-207, 300-304, 505, 514, 519, 526, and a terminator (-1).
  Figure IDs 100-115 are absent, which is why every Giant is refused. `tools/toy_table.py` prints the table.
- The `item code` literal is in an RHSValueStack (+0x20), reached through the parameter (+0x30) and a
  ValueRHSVariant (+0x08). `tools/toys.py` patches it (test 7 moves Spyro's entry from 16 to 112).
- `level load` and `name` are handles `0x80000000 | n` into `global.bld` (below).

Handle resolution (verified on all 56 entries): a handle `0x80000000 | n` is entry n of the referencing file's
record 2, `(index, FNV-1a(file name))`; `0x2694be8e` = FNV-1a("global.bld"). For `global.bld`, index = position
in its root igObjectList + 0x29 (Giants' `global.bld`: + 0x27, although both have 38 strings in record 1 and 36 named references in record 3,
so the offset is not the class count). Indices below the offset do occur: `global.bld` imports its own index 5. Ordinary characters: `level load`
-> `MinionLoad_NNN_*`, `name` -> the whole `Minion_Names` set, which the game indexes by figure ID (the source
of test 7's wrong name). Legendary/Dark entries: `name` -> one `StringInfo` (`016_Toy_Name_Legendary`, "L-Spyro").

Exporting new objects: append them to the root list (`minions.export`); their import index is the new position
+ 0x29. List buffers can mix pointers and import handles: element 2369 of `global.bld`'s root list is a handle
(`0x800001e4`, record 2 entry 0x1e4 = index 1 of the file with hash 0xba91d879). A buffer that is moved must keep
each element's own fixup type (`IgzDoc.copy_words`); marking the handle as a pointer hangs the game at boot
(first test 9 and first test 10). `IgzDoc.check` validates pointers, handles and string references offline.

Toy table call layout: 9 consecutive ops in the OpCodeList (use macro, INTERFACE, level load, item code, info,
element, name, flow macro, flow continue). Only the parameter ops and their value objects are per entry.
`script_edit.add_toy_entry` clones an entry and inserts it, growing the counts of the 4 enclosing ops
(OpPreScript, the MACROS section, the macro definition, the 38-call block).

## Language packs and load names

Verified on every `.bld` checked (`global.bld`, `016_Spyro.bld`, the `misc/` archives): a `.bld` with
`StringInfo` objects carries one pack per language next to `level.bld` (`ENGLISH.pak`, `FRENCH.pak`, `SPANISH.pak`,
`DUTCH.pak`, `GERMAN.pak`, `ITALIAN.pak`), and every pack holds exactly as many strings as the level has
`StringInfo` objects. The n-th `StringInfo` in address order takes the n-th string. `global.bld`: 588 and 588.

- Pack: IGZ v5 with `LanguagePackInfo` (+0x08 language name, +0x14 language ID: 5 Dutch, 6 English, 8 French,
  9 German, 0xE Italian, 0x15 Spanish; +0x18 `0x80000000 | text bytes`; +0x1C -> Text section + 4) and
  `tfbSoundDataInfo` objects for voice lines. The Text section is 4 zero bytes, then NUL-terminated UTF-16BE
  strings back to back, with no index. `tools/langpack.py` reads and rewrites it (round-trips byte for byte).
- A `StringInfo`'s own text is only its key. Display names: `016_Toy_Name` -> "Spyro",
  `016_Toy_Name_Legendary` -> "L-Spyro". Load names: the translation is the file name, without folder or
  extension: `MinionLoad_004_RockDragon` -> `004_Rock_Dragon`, `ItemLoad_Anvil` -> `item_anvil`
  (`item/Item_Anvil`, so case does not matter), `MiscLoad_CollectionScreen` -> `ui_collection_champions`,
  `MiscLoad_ChallengeVO` -> `ChallengeVO` (which is in `character/`, so the folder comes from the kind of
  load, not from the key prefix). This is why no file name appears in any script or in `main.dol`.
- Adding a `StringInfo` means adding its string to all 6 packs at the same position. New objects are appended
  at the end of section 0, so they come last in address order and their strings are appended last.
- Scripts can also reference a private `StringInfo` stored right after a reference stack's buffer
  (`global.bld` passes "MiscLoad_InitSetup" to "Game - Load Streaming Level" this way). `Init_Setup.bld` has no
  `StringInfo` objects and no packs.

## What the scripts need for a new character

Traced through the scripts with `tools/macro_dump.py` (op-stream order, references resolved):

- Portal gate: "Portal Control - Portal - Logic - 235 - Condition - Toy Can't Be Used" looks the toy up with
  "Portal - Get Object Level Info" and refuses it unless the level load is a member of `Minion_Loads` or
  `Item_Loads`. Logics 70 ("Too Many Minions"), 80 and 90 also count `Minion_Loads` members as characters.
  The toy-table macros themselves ("Portal - Define Object Level Load", "... Finalize ...") only store and sort.
- Save collection ("Save - Check Collection Info", called when a toy is placed): a Legendary's owned bit is its
  position in `Minion_Loads_Legendary`, in word 1; anything else uses bit index = figure ID (Cynder, ID 32, is
  remapped to bit 28 to stay in word 0). "Save - Bit Field - Get/Set Bit Field" computes word = set index +
  bit / 32 and bit = bit % 32 into `Collection_Minions`, which has 2 words, so IDs 101-114 would select word 3,
  past the end of the set. `giants.extend_collection_words` appends word 1 twice: the Giants' bits become bits
  5-18 of the saved word 1 (Legendaries use 0-4), with no save format change.
- Sets indexed by `Minion_Loads` position ("Save - Get Minion Index"): `Collection_MinionIcons` (32 entries,
  separate copies in `UI_Collection_Champions`, `UI_HeroicChallengeSelect` and `UpgradeUI`, the info screen),
  `ChampionIntroVideos` (`global.bld`, 37), `RightFacing_MinionSprites` (`PvP_MainControl`, 38). Out-of-range
  indexing is not checked: test 7's "Sonic Boom" name was `Minion_Names` read past its end. Each is padded to
  the Giants' positions (38-45) with entries reused from a stand-in.
- Sets indexed by `Minion_Loads_Legendary` position: `Collection_MinionIcons_Legendary`, `ChampionIntroVideos_Leg`
  and three `LegendaryMinions` sets in `PvP_MainControl`. Untouched as long as the Giants stay out of that list.
- Not handled yet: the PvP loading screen picks the announcer line with "Get Minion Announce VO Index", a
  name-by-name chain that leaves -1 for unknown characters, then indexes "PvP Announcer VO" with it.
- Expression encoding (used to read the arithmetic above): a `ValueRHSVariant` is left operand (+0x08),
  operator (+0x0C: 0 add, 1 subtract, 2 multiply, 3 divide), right operand (+0x10).

Memory budget per load category (table at 0x8054208C in `main.dol`, rows of 0x3C bytes: folder name, four pool
sizes, nine counts, slots): `character` is 0xC0000 + 0x100000 + 0 + 0x10000 bytes with 2 slots, `item`
0x40000 + 0x80000 + 0 + 0x4000. Converted Giants files will have to fit the character budget.

Which budget pool an IGZ section uses (verified in the code): `fn_804D0D08` creates one heap per non-zero pool size
of a budget and the named memory pools inside them from the table at 0x804229C0 (name, heap index): `Default` 0,
and `Image`, `Vertex`, `AnimationData`, `Audio`, `Text`, `Collision`, `String`, `VertexObject`, `Video` 1. Across
the rows, pool A totals about 15 MB and pool B about 57 MB, so A is MEM1 and B MEM2. A character's `level.bld`
therefore needs its `Default` sections in A (0xC0000) and everything else in B (0x100000); the fullest retail
character is Gill Grunt (999,141 bytes in B). Converted Giants (section sizes plus alignment): A at most 511,088
(Crusher), B from 1,256,950 (Ninjini) to 1,485,390 (Hot Head), so pool B at 0x180000 (the Riivolution memory patch
since test 14a) holds every Giant with at least 87,474 bytes to spare, and pool A needs no change.

## Figure data (from Dolphin's SkylanderFigure.cpp and marijnkneppers.dev)

- Block 1: figure ID u16 at 0x10, web code u64 at 0x14, variant u16 at 0x1C (the year/generation is in the
  high nibble when read big-endian: 0 Spyro's Adventure, 1 Giants), CRC at 0x1E.
- Encryption: blocks 8-63 except sector trailers, AES-128-ECB with key MD5(blocks 0-1 + block index +
  " Copyright (C) 2010 Activision. All Rights Reserved. "). `tools/figure.py` decrypts.
- Areas 0/1 (0x80 and 0x240, newest has counter +0x09 one higher): XP u24 at +0 (capped 33000 = level 10),
  gold u16 at +3, playtime u32 at +5, nickname UTF-16LE at +0x20 and +0x40, hero level u16 at +0x5A.
- Areas 2/3 hold what later games added: Giants XP (levels 11-15, capped 63500), Swap Force XP. Spyro's
  Adventure predates them and does not write them: on the 16 figures Dolphin created for the tests and only
  Spyro's Adventure played (area counters up to 243), blocks 8-10, 12-14, 16 and 36-38, 40-42, 44 hold its saves
  and blocks 17-21 and 45-49 are still raw zeros (a block a game writes is encrypted, so practically never all zeros). Not yet
  tried: a figure Giants has written, through Spyro's Adventure and back into Giants.

## Material animations and ability pictures

- UV animations: a material instance (`tfbRuntimeTechniqueInstance`) points at +0x2C to a `tfbMaterialAnim`, whose
  track list (+0x08) the renderer's attribute pass (`fn_80018A94` -> `fn_8008FDBC`) asks every frame for texture
  matrices through each track's virtual function at +0x4C. Spyro's Adventure has one kind of UV animation,
  `tfbProceduralUVAnimTrack`/`Data`; its data (`fn_80090760`, angles in radians): +0x08/+0x0C scale, +0x10/+0x14 scroll
  speed, +0x18/+0x1C wobble amplitude, +0x20/+0x24 wobble frequency, +0x28/+0x2C wobble phase, +0x30/+0x34 rotation
  pivot, +0x38 rotation speed, +0x3C rotation phase, +0x40/+0x44 rotation swing limits. Giants splits it into
  `tfbScrollUVAnim*` (the same fields up to +0x2C: Sunburn's and Camo's shared materials are identical) and
  `tfbTransformUVAnim*` (+0x08/+0x0C pivot, +0x10 rotation speed, +0x20-+0x34 a scale animation), a class Spyro's
  Adventure's engine does not have: such a track loaded without its function and Swarm's charged A crashed the
  game (test 36). `convert.TYPE_MAPS` turns both into procedural ones; a transform that does more than spin stops
  the conversion (none of the converted Giants has one).
- Ability pictures: Spyro's Adventure's are two 512x512 CMPR images, the colour (`igImage2` +0x1C = 1) and a grey
  alpha mask (+0x1C = 0), which the file's `tfbAlphaTextureUnitIDAttr` (+0x10 = 1, +0x14/+0x18 the two texture
  attributes) binds to the alpha unit. Giants' are mostly one 256x180 CMPR image with 1-bit alpha (+0x1C = 3, alpha
  unit -1): in Spyro's Adventure's upgrade menu such a picture took its alpha from whatever the unit held, and some
  did not show (test 36). `convert_character.widen_picture` redraws each into a copy of one of Spyro's own picture
  files from the player's disc. The level's `AnimatableTextureDataInfo` (+0x1C the texture's ID, used with its
  source path, `fn_8008F000`: "%s/0x%.8x") needs no change.

## Variant figures (`tools/variants.py`)

Granite Crusher, Scarlet Ninjini, Legendary Bouncer and Gnarly Tree Rex carry their base Giant's figure ID. The
variant word of block 1 tells them apart; the user's normal Tree Rex, Swarm and Ninjini figures read 0x1206.

- Giants: the engine fills each toy's tag header (`Portal - Tag Data . save data header`: 8 words, blocks 0-1 of
  the figure as little-endian words; the figure ID is word 4). "Portal - Load Portal Object NEW" calls "Save - Get
  Tag Subtype Properties" on the toy: its 'toy subtype' (word 7 bits 0-11) gives 'is repose' (bit 11), 'is
  legendary' (bit 10), 'is lightforce' (bit 9, cleared for characters outside the set 'display as lightcore') and
  the deco id (bits 0-7). With 'is legendary', "Portal - Get Minion Legendary Load" looks the toy's entry and deco id
  up in 'subtype lookup - legendary', filled by `character/Init_Setup.bld`'s "Portal - Define Legendary Alt Level
  Load" calls, and the loader streams that load name instead of the base one.
- The table on this disc: deco 2 for `MinionLoad_102_EarthTitanLegendary` (`102_Titan_Earth_Alt`, "Granite"),
  `MinionLoad_109_DjiniLegendary` (`109_Djini_Alt`, "Scarlet"), `MinionLoad_112_TitanLifeLegendary`
  (`112_TitanLife_Alt`, "Gnarly"); deco 3 for `MinionLoad_110_RobotGiantLegendary` (`110_RobotGiant_Legendary`);
  and 11 entries for other characters. Each variant's `.arc` is byte for byte its base Giant's; only `level.bld`
  differs (textures and materials, and its own life-bar head sprite, named `112_MinionHead_Alt` or
  `110_MinionHead_Legendary`), and it converts with the same tools.
- Spyro's Adventure has no subtypes: its own variants have figure IDs of their own (404, 416, 419, 430, 28). Its
  engine fills the same header for every toy, and its `global.bld` has the same "Save - Bit Field - Get Bit Field".
  So the port reads word 7 bits 0-10 in "Portal - Load Portal Object NEW", right after "Portal - Get Object Level
  Info" returned the toy's entry, and looks figure ID + 1000 x that value up in the toy table; a match replaces the
  entry, of which the macro then reads only the stream to load. The matching entries are hidden ones added to
  `Init_Setup.bld`: the four codes per variant that bits 8 and 9 can make (Giants ignores them), the variant's load
  name, no name, element 99 (no toy has it, so the per-element loops of the collection screen and the ownership
  check never reach them). Name, element, portrait and collection bit stay the base Giant's.
- Why it is safe: streams are tracked by slot, not by name (the queue builds `character/<load name>` and sets the
  slot); the only other place a toy's load name is kept, `object info . level` (set from the base entry by
  "Display Minion On Portal"), is never read; and loops over the toy table compare names, item codes or elements
  that the hidden entries do not have.
- Op shapes used are all retail ones. Retail scripts never put an operator inside another one's operand, never
  compare a found subset with an expression, and never call a macro inside a call of the same macro. Return
  parameters are objects shared by the definition and its calls, and a call can even reuse the definition's own
  parameter ops. So the code is built in 'value out' by two assignments and the subset search compares it plainly.

## IGA archives (`.arc`, `.bld`)

Little-endian header in both versions (even on Wii).

| Field | v4 (Spyro's Adventure) | v8 (Giants) |
|---|---|---|
| 0x00 | `IGA\x1a` | `IGA\x1a` |
| 0x04 | version 4 | version 8 |
| 0x08 | table size: 16 × n, plus the block table | same idea |
| 0x0C | n (file count) | n |
| 0x10 | divider `0xFFFFFFFF // n` | sector size 0x800 |
| 0x14 | slop: the largest distance between an entry's position and `hash // divider` | `0xFFFFFFFF // n` |
| 0x18 | name table offset | ? |
| 0x1C | name table size | name table offset |
| 0x20 | 0 | name table size |
| 0x24 | u16 block-table entries | ? |
| 0x28 | u8 block-table entries | u16 block-table entries |
| 0x2C | 0 | u8 block-table entries |
| hashes | at 0x30, n × u32, sorted ascending | at 0x34 |

The engine finds a name (FNV-1a hash) by binary search only among the entries within slop of position
`hash // divider` (`fn_800F0F94`), so an entry farther away cannot be found. The slop is that exact largest
distance in all 278 retail v4 archives (`iga.search_window`); `floor(log2 n)`, which our writer used before
test 38, matched only small archives by chance, and left 3 to 83 entries of six Giants' `.arc` unreachable:
upgrade pictures (exactly the ones reported missing for Eye-Brawl and Hot Head) and voice lines (Swarm's portal
name call among them). A texture's entry is found by the hash of `0x%08x` of its `AnimatableTextureDataInfo`
+0x1C (all 15 of Spyro's pictures), in the archive the loader names in `%s/0x%.8x` (`fn_8008F000`).

After the hashes: n entries of `(offset, size, flags)` in hash order, then the block table (u16 per block).

- `flags == 0xFFFFFFFF`: stored raw. All `.arc` entries are raw (verified).
- Otherwise LZMA, split into 0x8000-byte blocks. The high nibble is 1 in v4 and 2 in v8. Block table entry:
  bit 15 = compressed, low 15 bits = sector (0x800) offset from the entry start. A block without bit 15 is
  stored raw (verified: block 27 of Spyro's `level.bld`).
- Block: `[u16 compressed size][5-byte LZMA props][payload]`. The size is big-endian in v4 and little-endian
  in v8 (verified). Props are lc=3, lp=0, pb=2, dictionary 0x8000. Compressed blocks are padded to the sector size.
- There are two block tables after the entries: a u16 table (length in header 0x24 in v4, 0x28 in v8) and then a
  u8 table (length in 0x28 / 0x2C). The low 24 bits of a compressed entry's flags index its list in one of them:
  entries up to 127 sectors (0x3F800 bytes) use the u8 table (bit 7 = compressed), bigger ones the u16 table
  (bit 15). Each list has one value per block plus an end offset. Verified on all 2,506 compressed entries of both
  discs; header 0x08 = 16 × n + 2 × u16 entries + u8 entries.
- Data offsets are sector aligned. The name table sits at the end: n u32 offsets (relative to the table), then
  NUL-terminated names in hash order. v8 adds 4 unknown bytes after each name.
- Names in `.bld` archives are bare (`level.bld`, `ENGLISH.pak`) and hash with case-sensitive FNV-1a, the function
  at `fn_80125B4C` (verified 7/7). `.arc` names are build paths (`c:/tfb/build/wii/.../0x90e08944.wav.hz.wav.enc`)
  and their hashes are not FNV-1a of the stored path: an entry is found by FNV-1a of `0x%08x` of the key of the
  object that uses it, a texture's `AnimatableTextureDataInfo` +0x1C (above) or a streamed sound's
  `tfbSoundDataInfo` +0x1C (verified for every voice line of the 12 Giants character files in all six languages).
  The writer keeps each entry's original hash.

`iga.write_v4` rebuilds the retail `016_Spyro.arc` with the same size and identical bytes except 32 bytes of
padding after the entry table, where the retail tool left uninitialized memory (0x750-0x76F).

## IGZ object files

| | v5 (Spyro's Adventure) | v6 (Giants) |
|---|---|---|
| 0x00 | `IGZ\x01` | same |
| 0x04 | version 5 (big-endian) | 6 |
| 0x08 | user version: 0 in every retail file checked | per-file value (e.g. `0x905372f6`) |
| 0x10 | sections: `(offset, size, alignment, pool)` × up to 127, zero-terminated | same |

- Section 0 is metadata. It repeats `IGZ\x01` + version, then fixup records `(tag, ?, ?, count, size, header size)`.
  Both versions use the same 14 tags in the same order. Verified meanings:
  - tag 0: object type names; tag 0x0C: one u32 size per tag-0 type (e.g. `igObjectList` 0x18, `igImage2` 0x34).
  - tag 5: the object list. Every object's first word is its type index into tag 0 (4304/4304 objects in Spyro's
    Adventure's Spyro, 7693/7693 in Tree Rex).
  - tags 6, 7, 0x0B, 0x0E, 0x0F, 0x10: lists of reference fields; every decoded entry falls inside its section.
    Tag 0x0E covers string references (for example `StringInfo` +0x8).
  - tag 3: the file's named references, `(namespace, name)` pairs of tag 1 strings, which the loader resolves
    into a table (case 3 of `fn_8011F614`): (`metaobject`, class) for a script class, or a named object such as
    Crusher's (`SpriteInfo`, `^102_Shoulder_Gem_00_Legendary`) or `global.bld`'s (`ActorInfo`, `^metrics_master`).
    Tag 1 is only their string pool. Fields listed in tag 0x10 hold class numbers: an index into tag 3, plain or
    with the top bit set (case 0x10 of `fn_8011F614` also adds a reference then); all 4.8 million in both games'
    738 level files are in range. A class number is the class's tag 1 position minus one only while no named
    object comes before it (true of most character files, not of Crusher's, Bouncer's or either `global.bld`),
    so an object copied between files needs its class numbers translated by name through tag 3
    (`script_fixes.script_classes`). Test 37 crashed loading Crusher (and had out-of-range numbers in Thumpback
    and Eye-Brawl): the "Turn To" copy had read Giants' `global.bld` numbers off tag 1 and written numbers past
    the end of the target's tag 3; `IgzDoc.check` now catches that.
  - tag 2: imports `(index or name hash, namespace hash)`; tag 7: the fields holding import handles
    `0x80000000 | n`. Besides `global.bld` exports, namespaces are engine classes (`system`, `sequence`, ...) whose
    member names are imported by hash, and the file itself (`level.bld`: an index among the file's own objects,
    not a class; each of Bouncer's 46 `tfbSoundInfo` has its own at +0x4C).
  - tag 0x0A: data blocks `(flags | size, offset)` (pixel, vertex and index data); tag 0x0B: the fields that index
    them (`igImage2`, `igIndexBuffer`, `igVertexBuffer`). Tag 0x0F: the size words of memory references
    (`0x80000000 | bytes` before a list's data pointer). Size words written as `0x90000000 | size` before the data
    pointers of `tfbPhysicsAnimation`, `tfbPhysicsBody` and `tfbSoundDataInfo` are not in any list.
- Packed records (5, 6, 7, 0x0B, 0x0E, 0x0F, 0x10) are nibble varints: low nibble first, 3 data bits plus a
  continuation bit. Each value is a delta applied as `delta * 4 + 4`. An offset is `(object section << 24) | offset`,
  where object section 0 is the section after the metadata section. Pointer fields in object data use the same
  encoding. See `tools/igzobj.py`.
- Spyro's Adventure's loader check (`fn_8011E5E8`): magic must be `IGZ\x01`, version must be at least 5, and the
  user version must equal the engine's value, otherwise the load fails ("incompatible user versions").
  `igz.to_v5` therefore writes version 5 and user version 0.
- Layout check (`tools/layout_check.py`, type sizes from tag 0x0C, reference: all 50 Spyro's Adventure `.bld`
  archives). Every Giants character file, Giants' Spyro included, has:
  - 5-7 types that no Spyro's Adventure file uses, 6 of them missing from its executable too: `tfbMaterialTintAttr`,
    `tfbDestinationAlphaAttr`, `tfbScrollUVAnimData`/`Track`, `tfbTransformUVAnimData`/`Track` (material and
    texture-animation features added in Giants). `tfbLightInfo` exists in the executable but in no file.
  - 9-10 types whose size changed: `igImage2` 0x34 -> 0x60, `igVertexBuffer` 0x28 -> 0x30, `igVertexFormat`
    0x40 -> 0x44, `igTextureAttr2` 0x3c -> 0x40, `tfbAlphaTextureUnitIDAttr` 0x1c -> 0x20, `AnimationInfo`
    0x48 -> 0x44, `tfbPhysicsAnimation` 0x30 -> 0x2c, `tfbSoundDataInfo` 0x2c -> 0x28, `GeneratorMovementFields`
    0x58 -> 0x4c, `LightningGenerator` 0x6c -> 0x68, `physicsRandomAnimationNetwork` 0x40 -> 0x3c.
  - The script types that make up most of a character (`Op*`, `*Stack`, `ScriptSet`, ...) have the same sizes.
  So a header patch is not enough: the converter must rebuild the changed objects in the old layout and replace
  or drop the new ones. Tests 2 and 3 are expected to fail until it does.

### Reference counts (`tools/refcounts.py`)

- Every object's +0x04 is its reference count: the low 19 bits are the count, the bits above are flags.
  `main.dol` adds a reference with `fn_800E6BA0` (atomic increment) and drops one with `fn_800E6968` (atomic
  decrement); when the count falls from 1, that call destroys the object (`fn_800E6788`).
- Files store the counts precomputed, and the loader adds none. Each object's count is exactly the number of live
  owning pointers to it in the same file. Live pointers are object fields, plus the words of buffers that a live
  field points to; a buffer's extent is the size word before its data pointer.
- Two fields are non-owning in both games: `tfbActorInfo` +0xA8 (to its `tfbScriptInfo`) and
  `AnimationBlendInfo` +0x18 (to a `tfbPhysicsAnimation`).
- With those rules, recomputing every count reproduces every IGZ file on both discs byte for byte: 1816 files
  (5.39 million objects) on Spyro's Adventure's, 3071 (6.18 million) on Giants' (`python tools/refcounts.py
  --verify <files dir>`).
- An edit that writes a new pointer to an existing object therefore owes it a reference. A list moved to a new
  buffer leaves its old buffer unreachable; its pointers stay in the fixup table but no longer count.
  `IgzDoc.to_bytes` recounts every object, so edits do not track counts themselves, and the test builder rejects
  any written file that is off balance.
- Why it matters (tests 19 and 20): the interpreter resolves a reference path's member stubs on first use.
  `fn_80053730` looks up the real member by name and IDs, stores it in the path, and releases the stub. Two paths
  sharing one stub with a count of 1 means the first evaluation destroys the stub under the second path.

## Converting a Giants character (tools/convert_character.py)

Everything below was derived from data both games share, mostly Spyro and other Series 1 characters that are on
both discs, and is checked by `tools/convert_check.py` (every fixup moved with its field, every pointer relocated,
every converted block's size word and magic) and `IgzDoc.check`.

- Container: version 6 -> 5, user version -> 0. Same records in the same order; section order may differ (the
  loader allocates by pool name).
- Objects: `tools/convert.py` lays out every section that holds objects again. Type mappings (`TYPE_MAPS`):

  | Giants type | Spyro's Adventure | How |
  |---|---|---|
  | `igImage2` 0x60 | 0x34 | Giants inserted 9 words after the name (four 1.0, five 0) and appended 2 |
  | `igVertexBuffer` 0x30 | 0x28 | Giants added a size/pointer pair (+0x20/+0x24, 12-byte buffer): dropped |
  | `igVertexFormat` 0x44, `igTextureAttr2` 0x40 | 0x40, 0x3C | one appended word dropped |
  | `tfbAlphaTextureUnitIDAttr` 0x20 | 0x1C | same fields reordered (flag, texture, second texture), one dropped |
  | `tfbPhysicsAnimation` 0x2C | 0x30 | Giants bitfield +0x20 -> flag bytes at +0x28: bits 4, 9, 5 (245 pairs) |
  | `AnimationInfo` 0x44 | 0x48 | fields from +0x30 shift by 4; bitfield +0x30 -> bytes at +0x38: bits 4, 5, 6 (216 pairs) |
  | `GeneratorMovementFields` 0x4C | 0x58 | bitfield +0x18 -> enum +0x18 (bits 2-3), flag +0x1C (bit 0), enum +0x34 (bits 4-5), flag +0x54 (bit 1) (92 pairs) |
  | `LightningGenerator` 0x68 | 0x6C | +0x44 = mode (bits 0-2) and segment count (bits 3+), split again (46 pairs) |
  | `tfbSoundDataInfo` 0x28 | 0x2C | Giants +0x24 (the line's lip-sync animation) dropped |
  | `tfbLightInfo` 0x10C | 0x108 | Giants added a "visible" flag (word 55, per the executables' field labels): dropped |
  | `tfbMaterialTintAttr` | `tfbMulti2MaterialTintAttr` | same layout (header + RGBA) |
  | `tfbScrollUVAnimTrack` | `tfbProceduralUVAnimTrack` | same layout |
  | `tfbScrollUVAnimData` 0x34 | `tfbProceduralUVAnimData` 0x48 | UV scale and scroll speed kept, the rest zero |
  | `tfbDestinationAlphaAttr` 0x18 | `igDestinationAlphaAttr` 0x14 | alpha and enable packed as Spyro's Adventure stores them (best effort, 4 objects) |
  | `igBlendMatrixSelect` 0xC0 | 0xC0 | same size, moved field: the bone index list (`igIntList`) is at +0xB4 in Giants, +0xB0 in Spyro's Adventure |
  | `tfbRuntimeTechniqueInstance` 0x38 | 0x38 | material flags at +0x20 re-encoded: Giants bits 18-20 (0-4) -> bits 6-7 (4 -> 3), bit 8 always set, bit 2 brings bit 0; known values from a 320-pair table (`TECHNIQUE_FLAGS`) |
  | `physicsRandomAnimationNetwork` 0x3C | 0x40 | flag bitfield +0x20 -> bytes at +0x28 as in `tfbPhysicsAnimation`; the fields after it move up by 4 (39 pairs) |
  | `RibbonGenerator` 0x60 | 0x60 | +0x44 = mode (bits 0-2) and segment count (bits 3+), as in `LightningGenerator`; the colours move from +0x54/+0x58 to +0x58/+0x5C; Giants' float at +0x5C dropped (163 of 191 pairs exact, the rest retuned counts) |
  | `GeneratorGenerationFields` 0x34 | 0x34 | the particle count moved to the upper half-word of +0x1C (the lower half takes +0x20's place); +0x20..+0x2C -> +0x24..+0x30; Giants' +0x30 (always 1.0) dropped (2042 of 2099 pairs exact) |
  | `GeneratorAppearanceFields` 0x9C | 0x9C | Giants halves the RGB of the colours at +0x18, +0x1C, +0x20, +0x24, +0x70 (alpha kept) and sets +0x98 bit 3: doubled back (2g+1, 0 stays 0) and the bit cleared (2039 of 2099 pairs exact) |
  | `tfbMulti2BasicFlagsAttr` 0x14 | 0x14 | Giants sets bit 20 of the flags (+0x10) on every material (343 of 343 pairs): cleared. Bit 18 is Giants-only (110 materials, all glowing effects or lit surfaces such as Hot Head's flame jet and Tree Rex's glow, all with bit 30, which in Spyro's Adventure marks dynamically lit materials: character bodies; its levels, skies and flames have it clear): read as self-illuminated, bits 18 and 30 cleared (test 39, an experiment) |
  | `tfbMipmapBiasAttr` 0x14 | 0x14 | the LOD bias (+0x10) is 2.5 times larger in Giants (-1 -> -2.5, -4 -> -10; 5 of 5 pairs): divided |
  | `tfbPhysicsBody` 0x40 | 0x40 | +0x30 `_visemeSet` (lip-sync mouth poses, a `tfbAnimationInfoList`): set on every Giants main body, on no Spyro's Adventure one; left empty |

  Same-size types can change too: `tools/field_check.py` compares, per type and offset, which fixups the two games
  use (pointer and its target type, string, handle, block, size, class); `tools/value_check.py` compares
  same-named objects of the characters on both discs word by word. Neither sees unnamed objects or the converted
  types, so `tools/converted_diff.py` converts the Giants version of each of the 37 shared characters and compares
  it with Spyro's Adventure's own file: objects paired by name, then through the pointers of paired objects, every
  type and offset compared. It found the last six rows and the vertex pack data. What it still reports is data
  (positions, retuned counts and colours, texture names and sizes, block indices, reference counts at +0x04,
  converted block sizes) plus:
  - `tfbFlipBookUVAnimData` +0x08/+0x10: (4, 4, 2) in Spyro's Adventure, (2, 4, 4) in Giants for the same five
    objects (one character); whether two fields swapped or three rotated is not known yet. Swarm and Hot Head use
    the type; Tree Rex does not.
  - `tfbSoundInfo` +0x18 bit 3: set on almost every Spyro's Adventure sound, cleared on almost every Giants voice
    line (not related to streaming or embedding). Left as Giants has it; sound works.
  The agreement ratio hides fields that only some objects use (one main body per character): the comparison also
  reports structural differences (a pointer, string or handle on one side only) however rare; that is how
  `tfbPhysicsBody` +0x30 showed up.
- Field names: `main.dol` describes each engine class with two parallel arrays (field-type constructors and field
  names, in field order). `tools/dol_fields.py NAME` prints the name array a field belongs to, e.g.
  `igVertexFormat`: `_vertexSize` +0x08, `_elements` +0x0C, `_platformData` +0x14, `_platform` +0x1C,
  `_softwareBlendedFormat` +0x20 (the CPU skinning output format), `_blender` +0x24, `_dynamic` +0x28,
  `_platformFormat` +0x2C, `_streams` +0x30, `_hashCode` +0x38, `_softwareBlendedMultistreamFormat` +0x3C;
  `tfbPhysicsBody`'s own fields `_node` +0x20, `_combinerPrototype` +0x24, `_boneMappingTable` +0x28,
  `_visemeSet` +0x30, `_eyeBlink` +0x34, `_footprintData` +0x38.
  Memory-size registrations (record 0x0F) follow Spyro's Adventure's convention (`MEM_SIZE_CONVENTIONS`: it lists
  `RHSReferenceStack` +0x10 and not `PositionStack` +0x10; Giants the other way round).
- Vertex pack data: a vertex element (`igVertexFormat` +0x10 list, 12 bytes: type, stream, ..., usage, usage
  index, pack-data offset, pack type, offset, frequency) that is quantized (pack type != 0: positions, normals,
  texture coordinates) takes its fixed-point shift from the vertex buffer's pack data, one word at its pack-data
  offset (typically 10, 6, 14). Spyro's Adventure stores the pack data at the end of the vertex block itself
  (920 of 920 buffers); Giants in a separate buffer (`igVertexBuffer` +0x20 size, +0x24 pointer, the 8 bytes it
  added). The converter appends it to the block (as many bytes as the elements need: 8, 12 or 16) and lays the
  Vertex section out again, 32-byte aligned; the block records are its only references. Without it, test 16 drew
  Tree Rex huge and torn. `igVertexFormat` +0x30 (per-stream strides, a memory reference): when empty its size
  word holds the file's VertexObject section index (3 in Spyro's Adventure files, 5 in Giants'), which stays right
  because the converter keeps Giants' section order.
- UI conventions (`convert_character.adapt_ui`, `widen_picture`): ability pictures are 512x512 in Spyro's
  Adventure, the picture in rows 77-434 (147 of 197) with alpha 0 elsewhere (its own files keep alpha in a second
  512x512 texture); Giants' are the picture alone, 256x180 with 1-bit alpha. The menu fits the texture into one
  frame, so Giants' pictures came out about a third too large: the converter scales them 2x into the band
  (re-encoded as CMPR, `tools/gxtex.py`) and declares 512x512 in their `AnimatableTextureDataInfo` (+0x24/+0x28).
  The life-bar head is the `NNN_MinionHead` sprite, cloned by "UI - Create Player Health UI" (which sets its
  position, alignment and priority, not its size) and drawn at its texture's size: Spyro's Adventure's head
  textures are 80x80 cut-outs, Giants' a 128x128 round portrait (stored upside down like Giants' portraits; the
  game shows it the right way up). Tests 16-18 showed the same portrait with sprite sizes 128, 80 and 64, so the
  converter scales the texture to 80x80 (`shrink_head`) and sets the image, texture-info and sprite sizes to it.
- Scripts: see "Character scripts" below. Converted characters get `tools/script_fixes.py` (starting scale,
  renamed stubs, controller lock, omitted parameters).
- Debugging in Dolphin: a map file `%APPDATA%\Dolphin Emulator\Maps\SSPP52.map` (".text section layout", one
  `address size address 0 name` line per function of the decomp's `symbols.txt`) is loaded at boot; Dolphin then
  hooks `OSReport` (an empty stub in the retail game) and logs every call under OSREPORT_HLE, including
  `__OSUnhandledException`'s register and stack dump. The call stack shows the script interpreter as
  `fn_80062860` -> `fn_8003E964` -> `fn_8003B000` -> `fn_8005C4E8` -> `fn_800570B8` (op loop: execute method of
  each op, with the cursor in `lbl_806695C0` and the end in `lbl_806695C4`) -> `fn_8004D070` (dispatch through a
  handler table by the op's +0x28).
  `tools/script_trace.py` patches the two calls of an op's +0x0C handler in `fn_800570B8` (0x80057160,
  0x80057224) to log through `OSReport`, with the hook at 0x80001800 (the hole after `.text2` is reclaimed at run
  time). Only spawn ops reach those two sites (test 27t), so the trace shows spawns, which is enough to see which
  branch of a macro spawned. Each op class registers in `.text2` with its name, object size and a prototype whose
  vtable's slot 10 (+0x28) prepares an op: it installs the op's handlers at +0x0C/+0x10/+0x14 from member-function
  pointers (OpSetValue's vtable 0x80484040, OpCheckValue's 0x80483C98; OpCheckValue's handler 0x8005A598). The
  other ops are dispatched from those handlers, which a general trace would have to hook.
- Health: every `HP_Minion_*` ValueInfo stores 1.0 in both games. Spyro's Adventure assigns the numbers at start-up
  (`global.bld`, "Minion - Tune Minions": VeryLow 200, Low 240, Medium 270, High 300, VeryHigh 340, nudge 10), and
  "Portal - Define Minion" takes the character's category (its "max hp" parameter) as level-1 maximum health.
  Giants assigns its numbers in `character/Init_Setup.bld` (op list 6, its counterpart of "Minion - Tune
  Minions"): the same values for the categories both games have, and Titan_Low 400, Titan_Medium 430, Titan_High
  460. The copied Titan categories would keep 1.0, so `giants.TITAN_HEALTH` gives them these values. Swarm and
  Ninjini use Titan_Low; Hot Head, Bouncer, Tree Rex and Eye-Brawl Titan_Medium; Crusher and Thumpback Titan_High.

- Animations and skeletons are Havok packfiles: Giants hk_2011.2.0-r1 (file version 9), Spyro's Adventure
  Havok-7.1.0-r1 (version 7). `hkaSplineCompressedAnimation`, `hkaAnimationBinding`, `hkaAnimationContainer` and
  `hkRootLevelContainer` have identical layouts; only the animation type enum differs (spline: 3 in 2011, 5 in
  7.1). `hkaSkeleton` 2011 adds `referenceFloats` (+0x30, empty in Tree Rex): removed in place.
  `tools/hkconvert.py` writes version-7 packfiles with a Spyro's Adventure header and class-name section (its
  class signatures). Spyro's Adventure's packfiles also carry an empty "Resource Data" container; not added.
- Animation compression: Spyro's Adventure's animations use spline quantization `0x45` on every track (16-bit
  positions and scales, 40-bit rotations); most of Tree Rex's animated tracks use `0x00` (8-bit positions,
  32-bit polar rotations). Havok 7.1 is expected to decode both; to be confirmed in game.
- Memory: converted Tree Rex needs 1.88 MB; the biggest Spyro's Adventure character 1.38 MB. The character
  budget (`main.dol` 0x8054208C, row `character`: 0xC0000, 0x100000, 0, 0x10000 bytes per slot, built by
  `fn_80542230`) is too small; raising pool B (0x8054210C) to 0x180000 with a Riivolution memory patch lets him
  load (test 14a).
- Lip-sync: 44 of Tree Rex's 136 `tfbPhysicsAnimation` objects are not Havok but `DEADBEEF` blocks, one per voice
  line (Giants characters talk). Only the voice lines' `tfbSoundDataInfo` +0x24 references them. Dropped, with
  their data.
- Imports: `global.bld` exports matched by type and name (33 of Tree Rex's 42 exist in Spyro's Adventure); engine
  members are identical pairs (all of Tree Rex's exist in some Spyro's Adventure file). The rest are copied into
  Spyro's Adventure's `global.bld` and exported (`giants.add_imported_globals`): Tree Rex needs 5 tuning values
  (`TurnRate_Titan`, `Titan_Attack`, `Titan_SuperAttack`, `Titan_FallImpact`, `HP_Minion_Titan_Medium`) and 4
  texts of Giants' per-Skylander quests.
- Language packs: converted like the level (they hold the localized voice lines and their lip-sync animations).
  Spyro's Adventure wants six; each PAL Giants disc has three (Spanish, German and Italian on SKYZ52, English,
  French and Dutch on SKYP52), so every pack comes from the disc that has its language (`paths.giants_discs`;
  until test 40 all six were Spanish). The level converted is SKYZ52's. The two discs' character `level.bld`
  are identical for 8 of the 12 files; the others differ in `OpMacroParameter` +0x40/+0x44 (build ids), and
  Eye-Brawl and Legendary Bouncer also in some script data. In all 12 the StringInfo keys and every pack's
  voice-line names (`tfbSoundDataInfo` +0x08) come in the same order, so every pack fits SKYZ52's level. Packs
  of one character differ by at most 384 bytes of pool B. The `global.bld` texts copied for imports
  (`giants.add_imported_globals`) are looked up by StringInfo key in each disc's packs (both discs' `global.bld`
  have the same 913 keys in the same order).

## Character scripts

Tools: `tools/script_print.py` prints a macro (or `--range FIRST:LAST [--oplist N]` of an op list) as statements
with expressions, comparisons, called macros and their arguments; `tools/macro_calls.py` lists a converted
character's calls of macros Spyro's Adventure lacks and the parameter differences of the rest;
`tools/engine_names.py` names engine imports.

- Op stream: each script is an `OpCodeList` (+0x08 count, +0x14 array of op pointers). An op's control word
  (+0x18) counts the ops of its block in its low half for every type in `script_edit.COUNTING` (macros,
  interfaces, flows, checks, loops, spawns, STARTUP/SHUTDOWN, ...). The array is directly followed by its first op
  object (PRESCRIPT) in every retail file; insertions are made in place (`script_fixes.grow_in_place`).
- Shared ops: retail arrays reuse identical op objects at many positions (in Tree Rex's script one
  `OpFlowBuiltInBehavior` serves 326 positions, one `OpMacroInterface` 46). An op's block count therefore cannot
  change for one position alone (`script_edit.check_unshared` refuses); edits that keep the op count (a parameter
  op replaced in its slot) are safe. Test 22's first attempt removed a parameter and shrank an unrelated call.
- Stubs: a character uses a global macro or structure through a local `OpDefineMacro` / `OpDefineStructure` with
  +0x1C = 1 (a local definition has 0): +0x08 name, +0x18 the definition's control word, +0x20/+0x24 creation IDs
  (a 64-bit time stamp, e.g. `01caebb5 a1970f40`, kept by both games for everything they share). Stubs are linked
  by name. Giants renamed five macros and two structures it inherited, with the same IDs and parameter IDs, so
  their stubs never linked; `script_fixes.rename_stubs` gives them Spyro's Adventure's names:
  "Projectile - Fire Projectile" / "Combat - Fire Projectile", "Projectile - Define Projectile" / "Combat - Define
  Projectile", "Projectile - Add Logic" / "Combat - Projectile Add Logic", "Projectile - Logic" / "Combat -
  Projectile Logic", "Camera - Set Relative Position and Orientation" / "Camera - Set Relative Zoom";
  structures "Projectile - Projectile Description" / "Combat - Projectile Description" and "Projectile -
  Projectile Info" / "Combat - Projectile Info".
- Calls: `OpUseMacro` (+0x1C -> `ScriptGroupStack` +0x18 -> stub), then `OpMacroInterface`, one `OpMacroParameter`
  per argument (+0x1C name, +0x20 class number (tag 0x10), +0x24 type, +0x30 value, +0x38 -> the macro's stub,
  +0x40/+0x44 parameter IDs), `OpFlowMacro`, `OpFlowBuiltInBehavior`. Arguments a macro does not have are ignored.
  A parameter a call leaves out is 0 (null for a reference): the defaults in a macro's interface are never read
  at run time, because Spyro's Adventure's editor writes every parameter into every call (test 27t: Tree Rex's
  Define call without 'is new-style projectile' gave his description 'new projectile' 0, not the default 1).
  `script_fixes.fill_omitted_parameters` passes Spyro's Adventure's default for each parameter a converted call
  leaves out whose default is not 0, in the slot of an argument the macro does not have. A call of a macro that
  does not link is skipped.
- Expressions: a `ValueRHSVariant` is a binary node, +0x08 left operand, +0x0C operator (0 +, 1 -, 2 *, 3 /;
  0xFFFFFFFF: a plain value), +0x10 right operand; operands are value stacks (paths, literals) or nodes. A literal
  (`RHSValueStack` with no path) keeps its value at +0x20 and a class number at +0x1C. Identical literals are
  shared too (one "1" served 1752 parameters in `global.bld`), so a literal must be copied before it is changed.
- Comparisons (`OpCheckValue` +0x20): 0 !=, 1 ==, 2 <, 3 >=, 4 >, 5 <= (code ^ 1 negates). Evidence in
  `script_print.COMPARISONS`; tests 24 and 26 settled it the hard way: codes 5 and 2, each written for >= into
  "Combat - Define Projectile"'s style test, made it skip the logic sets of every Spyro's Adventure projectile.
  Else: an `OpAbstractFlow` jumps over the ops its count covers, so `if X: A else: B` is the check (its block: A
  and the `OpAbstractFlow`), A, the `OpAbstractFlow` (count: the length of B), then B; `if X: (nothing) else: B`
  is a check whose block is only the `OpAbstractFlow`. Other conditional ops (membership checks, find
  subset/variable, control) take an else the same way. The control-word flags do not tell (bit 3 is set on checks
  with and without one); tests 23-26 were read with that wrong rule. An `OpFlowBehavior` 'flow end' of count
  0xFFFF returns (it opens no block).
- Engine imports: record 2 entries name a member and a namespace by FNV-1a hashes of their names, which are strings
  in `main.dol` (`parent@abstractplacement`, `my@optoplevelbehavior`, `null@abstractscriptgroup`,
  `controller` and `inactive controller` in `scriptcontroller`, `script timer@system`).
- Engine members only Giants has: comparing every converted character's engine import pairs with those of every
  Spyro's Adventure file (`tools/import_pairs.py`) leaves one, `attenuates` (0x235BF273) of namespace 0xAD36AAE8,
  which Giants sets on playing sounds (whether one fades with distance). Bouncer's "110 - Rocket Shutdown" sets it
  on the rumble sequence "Game - Player Rumble" returns; in Spyro's Adventure the path resolver leaves the
  member's field descriptor null and `fn_800588B8` (the assignment to an engine member) calls through it (test 35:
  his B attack crashed). An assignment to a null object is skipped safely; to a missing member of a real object it
  is not. `script_fixes.drop_missing_member_writes` puts an `OpAbstractFlow` of count 0 (a jump over no ops; the
  retail scripts have 55 in `global.bld`, in empty else branches) in the slot of each such assignment, so no
  block count changes, and stops the build if such a member is read anywhere.
- Calls Spyro's Adventure cannot link (Tree Rex: 22 macros, `tools/macro_calls.py`), by kind:
  - renamed: fixed by `rename_stubs` (above);
  - controller: "Movement - Activate/Deactivate Controller" (Giants' movement system). Spyro's Adventure
    characters swap their actor's `controller` for the `inactive controller` themselves when entering the disabled
    state (dialogues, cutscenes); "Minion - Set Controller to Inactive" does the same for a minion description.
    `script_fixes.redirect_controller_calls` points Tree Rex's two deactivating calls at it (test 22: he is held
    still in cutscenes), and calls that turn the controller back on (Crusher, Thumpback, Eye-Brawl) at "Minion -
    Attempt to Restore Controller from Inactive". The minion description argument is copied from a call of either
    macro in the same script; a script with no such call (Bouncer) gets the macro's call group (stub and
    interface) cloned from one of the other macro's. A call op shared by positions with different targets is
    cloned for its position;
  - renamed parameters: Giants' "Projectile - Add Homing Logic" ("Combat - Projectile Add Homing Logic") keeps
    Spyro's Adventure's seven parameter names but has new IDs (0x147b2e00-06; Ninjini, Bouncer).
    `script_fixes.rebind_parameters_by_name` gives an argument whose ID the macro does not know the IDs of the
    parameter with its name, before `fill_omitted_parameters` runs (which otherwise took such an argument for a
    slot of a parameter the macro lacks);
  - Giants' movement system ("Movement - Set/Get/Displace Velocity", "Set Minion Movement Characteristics"): a
    script-level mover list (`Movement Data . movers`) updated every frame; his B charge needs it;
  - small helpers with no counterpart: "Minion - Combat - Query to Add Enemy to Already Hurt Handler" and "...
    Already Hurt Cleanup" (the charge's damage is gated on them), "Sound - Ultra Sound", "Sound - VO Request",
    "Sound - Stop Loop" (most of his sounds and voice lines), "Minion - Get Minion Properties", "Portal - Toy Def
    Check if Tag is Ready", "World - Shake Objects Now";
  - Giants-only features: accolades, "Minion - Define Titan Generic Data".
  - ported as local macros (`tools/macro_port.py`, the branch for an actor that is not on Giants' mover list, which
    is every actor here): "Movement - Displace Velocity", "Get Controller Reference", "Simple Safe Movement" (with its
    local variables), "Turn To", "Set Velocity", and Giants' "Sound - Stop Loop" and "Sound - Ultra Sound".
    "Movement - Get Velocity" returns `velocity data`, a creature-description member (structure "Combat - Creature
    Description - Movement Velocity Data") Spyro's Adventure lacks, filled from the actor's velocity vector: it is
    defined empty, and `script_fixes.read_velocity_directly` turns each read of a returned member into that engine
    path on the call's actor (`[my . velocity . length@vectormeasurement]`; every call passes `my`). A call of a
    macro that `global.bld` lacks skips the statements of its block, and every Giant but Eye-Brawl nests code in
    this one (Hot Head launches his A fire there, Crusher places his boulder target). The porter copies a macro's
    local variables when the body asks for them, points a reference to a called macro's own parameter at the
    copied call's parameter of the same macro and IDs (the interpreter binds them alike), and adds script classes
    and object types the character's file did not use yet (`OpTurnTo`).
- Engine members read off an actor definition: Bouncer aims his rockets with "Calc - Ballistics - Get Angle FROM
  Constant Velocity", passing `[tfbActorInfo('110_RocketProjectile') . physics . gravity acceleration@actorphysics]`
  (Legendary Bouncer names the base Giant's rocket through a named reference). Giants answers that from the
  definition's ActorParameters (+0x30, gravity: 32 ft/s² for characters, 20 for the rocket, -5 for Hot Head's
  rising fire; +0x2C is a speed cap, 9999 for the rocket). Spyro's Adventure reads engine members on
  `tfbActorInfo` objects only in level files, where they are placed actors; no character file does it, and the
  rockets fell far from the target (test 38). `script_fixes.literal_definition_physics` turns such reads into
  literals of the definition's value. Parameter and member +0x20 is a class number too (fixup list 0x10).
  That alone did not make them land (test 39: farther still). Each rocket starts from a positioning actor
  spawned at its target and moved 75 ft up and 5 ft aside; the aim, from the target's horizontal distance and
  vertical offset, sends it forward from there in Spyro's Adventure, while in Giants it must come out close to
  straight down (about -85 degrees from that point). Spyro's Adventure's own volley (Flameslinger's arrows)
  measures through a remembered placement (`null actor . remembered@placementreference . horizontal distance`),
  uses a fixed gravity (175) and sets it on the live projectile after firing. `script_fixes.drop_rockets_from_above`
  makes the rocket call's pitch -90 (test 40).
- Playback rates: Spyro's Adventure's scripts set only whole rates (IntMeasurement literals, percent of normal
  speed); both games stop a sequence with 0. Crusher's B gaze starts its sequence with 0.001 and then sets and
  reads its position every frame; with that rate his steering behaved as if the position read back were NaN
  (test 39t). `script_fixes.whole_playback_rates` gives a sequence started with a fractional rate and then
  positioned the rate 1 (test 40). Sequences only paused that way keep it (Tree Rex's head turn, Eye-Brawl's
  eyeball).
- Script trace (`tools/script_trace.py`, a `t` test): every spawn op of every running script goes to Dolphin's log
  through OSReport. `tools/trace_map.py` finds where a character file loaded (the base that explains the most
  logged ops; a file's objects keep their distances) and names the logged ops by op list and index.
- Local macros: a character's op list has its own MACROS section (after STARTUP and SHUTDOWN) with local
  definitions: `OpDefineMacro` (+0x1C 0; +0x18 the number of ops that follow), `OpMacroInterface` (count: the
  parameters plus `OpFlowMacro`; +0x1C an `OpCreateVariableList` of the macro's local variables, or 0), the
  parameters (+0x38 the definition), `OpFlowMacro`, the body, a closing 'flow continue'. Calls reach a local
  definition through a `ScriptGroupStack` exactly as they reach a stub. `tools/macro_port.py` turns a stub of a
  Giants-only macro into such a definition before conversion, copying Giants' own ops after it (every script type
  has the same size in both games): the parameters keep their IDs, so the calls bind unchanged. Copies between
  files translate class numbers (fixup list 0x10: an index into record 3, plain or with the top bit set) by name,
  adding a class the target lacks to its records 1 and 3, refuse imports of the source file's own objects
  (namespace `level.bld`), copy engine imports as they are, and find a buffer's size in the word before its pointer (registered in list
  0x0F or not, depending on the type and the game). A pointer to an exported object of the source `global.bld`
  (its root list) becomes an import handle (index = root position + 0x27 in Giants, which the conversion maps to
  Spyro's Adventure's by type and name); a definition or structure member the target lacks gets a stub, a copy of
  the definition or member object outside every op list. Scripts of a file call each other's local macros (Tree
  Rex's lists 0 and 4 call "Minion - Giant Init" macros of list 8), so every ported macro goes into the main
  script. Tree Rex gets "Movement - Displace Velocity" (zero the horizontal velocity, then the branch for actors
  outside Giants' mover list), an empty "Minion - Combat - Query to Add Enemy to Already Hurt Handler", and Giants'
  whole "Sound - Stop Loop" and "Sound - Ultra Sound" (both find `Music Control Data` owned by `Macros_Music`, which
  Spyro's Adventure has with the same IDs and members).
- Inserting ops grows every block that encloses the insertion, and shared ops cannot grow alone; a shared
  `OpAbstractFlow` (a jump: Tree Rex's Fire call sits under three jumps that are also used elsewhere) gets a copy
  of its own for the position (`script_fixes.grow_in_place`). Shared checks are refused: the else-if tests after a
  check refer to the check object itself for its tested value.
- Redirected calls: `script_fixes.redirect_calls` gives a Giants-only macro's stub the name and IDs of a Spyro's
  Adventure macro that does its job and rebinds each argument by name (a table renames the ones that differ) to
  that macro's parameter IDs; argument ops belong to calls of one macro only, so they change in place and
  statements after a call keep reading its outputs. "Sound - VO Request" -> "Sound - Play Sound" (priorities lost;
  Giants' body needs Giants-only audio structures). "Sound - Ultra Sound" went to "Sound - Play From Set" in tests
  29-30 and is a port since test 31, as is "Sound - Stop Loop": Giants' body slides the sound's volume to 0 and adds
  it to `Music Control Data . streaming sounds being faded out`, which Spyro's Adventure's "Sound - System Update"
  stops at volume 0. Whether a sound loops is bit 0 of `tfbSoundInfo` +0x18 (Tree Rex's wing and charge wind loops 0x40000029,
  one-shots 0x40000028; Spyro's Adventure's portal loops 0x40000001).
- Push blocks (the big turtles: `GameElement_PushBlock_Turtles`, in `Level_001_Castle`, `Level_006_IslandEscort`
  and challenge levels 18, 25, 28; one generic push-block script per level, list 183 in `Level_001_Castle`): a
  minion of `G:ScriptSet('Minions')` within reach, not more than 10 above the block and facing it (FOV 75, 150 on a
  corner) gets the push arrow; then, unless `G:ValueInfo('Flying')` is in its `creature info . character
  parameters . gameplay properties` (Spyro adds and removes it when he flies), "Minion - Locked State Start/End"
  locks it (through `Game - Get Player Joined Data (OLD)` and the joined data's `minion local desc`; it fails when
  `lock state not allowed` > 0) and the block slides. Characters do nothing themselves. The facing checks
  (`OpCheckFOV` +0x38) reach only 14 units from the pusher's center; blocks are 15 wide and a Giant 14 (main actor
  `CollisionInfo` 14 x 21.2 x 3; Spyro 4 x 5 x 3), so a Giant touching a block is out of reach. Giants' script
  raised the reach to 25 (a variable, 'FOV check distance') and also refuses minions with `No_PushBlocks` in their
  gameplay properties; `tools/level_fixes.py` gives Spyro's Adventure's script Giants' reach (29 levels carry it;
  `build_tests.LEVEL_FIXES`). Some retail levels fail `IgzDoc.check` as shipped (`Level_009_Minefield`: 4 handle
  fields without the handle bit), so level edits are checked only for new problems.
- Velocities: an actor's velocity is engine member 0x32741c32 of namespace 0x58709542 (a `vectormeasurement`:
  length, heading, pitch, horizontal length, vertical difference). `OpDisplace` (+0x1C the target path, +0x20 a
  mode, +0x24/+0x28/+0x2C length, heading, pitch) in mode 0 adds to it; Spyro's Adventure sets a velocity by zeroing
  its horizontal length first and caps one by assigning its length. Mode 1 is used for launches and knockback.
- Particles of a projectile: Spyro's Adventure's Fire attaches the launch particle to the projectile and removes it
  when its first generator ends ("UI - Particle Remover"); Giants' Define also takes post-process macros for the
  particles, which Spyro's Adventure ignores (Tree Rex's muzzle macro attaches the flash to his node and removes it
  after 0.2 s). Without that macro the flash rode on every laser as a big yellow sphere (tests 28-29); with its
  attachments inserted after his Fire call (Fire returns the particle in the call's 'launch particle' argument)
  the same sphere sat over his hand (test 31): the flash particle `112_Megaseed_muzzle` itself draws that way in
  Spyro's Adventure, so `script_fixes.drop_post_processed_launch_particles` leaves it out of every Define call that
  has a post-process macro (Tree Rex, Hot Head, Ninjini). The null it puts in the argument is a null value of the
  argument's class, from the same call or, when the call has none (Ninjini), from any parameter of the script.
- Projectiles. Spyro's Adventure has two styles, chosen by the description's 'new projectile', which "Combat -
  Define Projectile" sets from its 'is new-style projectile' (every one of the 516 calls on the disc passes 1;
  Define adds the description's logic sets only for style 1). "Combat - Fire Projectile" begins
  `if new projectile == 0: (nothing) else: {style 1, return}` and continues with style 0:
  - style 1 (Fire ops 135-271 in `global.bld` op list 29): the projectile is registered in `projectile control
    data . projectiles`, which "Manage Projectiles" (a global prescript, every frame) moves and expires through
    the logic sets; it is spawned (op 148) with its tracking particle (176), and limits, over-limit logic and a
    wall-clip ray cast are handled. Every Spyro's Adventure projectile, and every Giants one (Giants has only
    this style and no such parameter);
  - style 0 (from op 272): the actor is spawned (304) and launched with `OpDisplace` only when its `parent` is
    undefined, and a projectile manager actor is spawned (334) and given the description, speed, owner and
    particles through `FindVariable 'owned by'`. Nothing on the disc uses it, and projectiles fired this way
    stay where they are fired: Tree Rex's lasers until test 28 (his Define call left the parameter out, so it
    was 0) and every projectile in tests 24 and 26 (whose `global.bld` changes broke Define's style test).
  'speed' -1 asks for the description's speed (style 1 resolves it), so converted Fire calls keep theirs.

## Sound

Spyro's Adventure: FMOD sound banks in `FSB4`; Giants: `FSB5`. Both carry GCADPCM (Nintendo DSP ADPCM), so
`tools/fsb.py` re-wraps the data without re-encoding: one sample per bank, mono or stereo (both interleave stereo
every 2 bytes: each channel's first frame header, stored with its coefficients, is at data offset 0 and 2).

- Embedded sounds: a `tfbSoundDataInfo` with data points (+0x18, size word at +0x14) at an FSB bank in the
  level's Audio section (39 in Tree Rex): converted in place.
- Streamed sounds: no data pointer, a key at +0x1C, data in the `.arc` entry whose hash is FNV-1a of `0x%08x` of
  the key (IGA archives above). Localized voice lines sit in per-language folders in both games
  (`.../german/vo_...wav`, Stump Smash's selected lines too), the English ones in the character's own folder next
  to the wordless sounds all languages share, and each language pack has its own key for the same line. A Giants
  disc's `.arc` holds only its three languages' lines, so a converted Giant's `.arc` is both discs' together
  (`convert_character.giants_arc`; the shared entries are identical on both): 291 to 375 entries, where Spyro's
  Adventure's characters have up to 128. The engine allocates an archive's table by the header's table size
  (`fn_800F1E10`), and retail archives have up to 1080 entries (`Level_010b_FinalBattle.arc`).

## Useful executable addresses (Spyro's Adventure)

| Address | What |
|---|---|
| `fn_80125A44` | FNV-1a over a buffer `(data, length, basis)` |
| `fn_80125B4C` | FNV-1a over a C string, case-sensitive |
| `fn_80125B7C` | FNV-1a over a C string, lowercasing each character |
| `fn_80125BE8` | reads the system language (`SCGetLanguage`) |
| `fn_8011E5E8` | IGZ header check |
