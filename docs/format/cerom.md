# Embedded Windows CE ROM (`cerom`)

> **Scope.** This is the authoritative description of the Windows CE 5 / SH-4
> XIP image embedded in the Clarion firmware wrapper: where the segment starts,
> how `ROMHDR`, the TOC, `e32_rom`/`o32_rom`, the RAM copy table and the
> physical↔file address map are laid out.
>
> **Sample.** All observed numbers are from the EU 2011 image
> `LEAF_2011-2012_QSD-309-101_navi158_eu.img`,
> SHA-256 `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`.
> Vendor data is **not** in the repo and is not available on every machine;
> values marked *not recorded* were never written down and cannot be
> re-derived from the documents.
>
> **Status legend.** `VERIFIED` = reproducible with a command in this repo;
> `OBSERVED` = seen once, consistent, not re-checked; `HYPOTHESIS` = fits the
> public format/arithmetic, not yet exercised on this image; `UNKNOWN` = no
> data. Every section carries its own status.
>
> **Tool.** `tools/ce_rom_parse.py` is the only firmware parser in the repo.
> It reads the wrapper, the segment header, `ROMHDR` and the TOC. It does
> **not** parse `e32_rom`, `o32_rom` or the copy table — those sections below
> are format knowledge, not tool output.

---

## 1. Where the segment sits in the wrapper

**Status: VERIFIED** (all offsets and the `segment base ↔ physfirst` mapping);
the boot block's instruction stream is UNDECODED.

The pre-partition area holds a Clarion update container per build. The CE image
starts `0x200` bytes into each container — pinned by `ECEC` at base `+0x40` and
the wrapper size observed for A:

| Build | Container start | CE segment base | `ECEC` | `pTOC` (VA) | `size` |
| --- | --- | --- | --- | --- | --- |
| A | `0x00200000` | `0x00200200` | `0x00200240` | `0x8e232978` | `0x01751978` |
| A copy | `0x02000000` | `0x02000200` | `0x02000240` | `0x8e232978` (same VA) | `0x01751978` (same) |
| B | `0x03e00000` | `0x03e00200` | `0x03e00240` | *not recorded* | *not recorded* |
| B copy | `0x04800000` | `0x04800200` | `0x04800240` | *not recorded* | *not recorded* |
| C | `0x05200000` | `0x05200200` | `0x05200240` | *not recorded* | *not recorded* |

Build A's container header (updated; the older list in
[`firmware.md`](firmware.md) had the `ECEC` byte order reversed and no `pTOC`):

```
0x00200000  u32 0x01752c88        ROM payload length == physlast-physfirst (see §3)
0x00200014  "\x82FX210ECNI.158"   Clarion version string
0x0020002c  "SUM4" + u32 0xcdf87db0
0x00200034  "470-2824-34"         Clarion part number
0x002001fc  "NKOK"
0x00200200  CE segment base: 0x40-byte boot block (16 dwords), see §2
0x00200240  "ECEC"                signature; bytes 45 43 45 43 (ASCII "ECEC")
0x00200244  u32 0x8e232978        pTOC = VA of ROMHDR
0x00200248  u32 0x01751978        ROMHDR offset from segment base
```

The signature is the four ASCII bytes `E C E C`; `ce_rom_parse.py` searches for
the literal `b"ECEC"`. The DWORD `0x43454345` quoted in platform headers is
byte-swapped relative to the file image: do not search for `43 45 43 45`.
`ECEC` sits at **segment base + `0x40`** (the CE `ROM_SIGNATURE_OFFSET`), not at
segment base.

B/C put the Clarion ID at container `+0x220` and the part number at
container `+0x250`, i.e. CE segment `+0x20` (inside the `0x40`-byte area before
`ECEC`) and `+0x50` (just past the segment header) — while A keeps them in the
`0x200`-byte wrapper. So B/C's wrapper metadata is not cleanly separated from
the ROM header: the pre-`ECEC` area there is not pure SH-4 entry code (derived
from the documented offsets; the meaning is UNKNOWN). The CE anchor itself is
identical for all builds, which is why locating `ECEC` works where searching
for `B000FF`, `ROMHDR` or the Clarion strings fails (C-380/C-381).

`size` is **not** the image size. It is the distance from segment base to
`ROMHDR`, so `segment_base + size == romhdr_offset`. For build A:
`0x200200 + 0x01751978 = 0x01951b78`. The tool prints `size` but never checks
this identity (see §10).

The tool finds five valid segments (A, A copy, B, B copy, C). Payload A
contains two literal `ECEC` hits but only one resolves to a TOC; the other is
rejected by the `physfirst`/CPU/count checks.

---

## 2. Segment header

**Status: VERIFIED.**

| Offset (from segment base) | Size | Field | Notes |
| --- | ---: | --- | --- |
| `0x00`–`0x3f` | `0x40` | boot block | CE entry area, 16 dwords; EXP-24 recorded a palindromic pattern with `d108` at the ends, contents otherwise UNDECODED |
| `0x40` | 4 | signature | ASCII `ECEC` (`45 43 45 43`) |
| `0x44` | 4 | `pTOC` | VA of `ROMHDR`; must be in `0x80000000…0x90000000` |
| `0x48` | 4 | `size` | `ROMHDR` offset from segment base; `0 < size < 0x10000000` |

`pTOC` and `size` are both little-endian `u32`. `pTOC` is a **physical-space
VA** (§7), not a file offset.

---

## 3. `ROMHDR` — 0x54-byte header at `pTOC`

**Status: VERIFIED** (layout and A values); **OBSERVED** (B/C counts and
range); *not recorded* elsewhere.

`ROMHDR` is 84 (0x54) bytes, little-endian, at
`file = p2f(pTOC)`. Build A: `0x01951b78`. The TOC follows immediately at
`ROMHDR + 0x54`.

| Offset | Size | Type | Field | A | B | C |
| ---: | ---: | --- | --- | --- | --- | --- |
| `0x00` | 4 | ULONG | `dllfirst` | *not recorded* | *n/r* | *n/r* |
| `0x04` | 4 | ULONG | `dlllast` | *not recorded* | *n/r* | *n/r* |
| `0x08` | 4 | ULONG | `physfirst` | `0x8cae1000` | `0x88000000` | `0x88000000` |
| `0x0c` | 4 | ULONG | `physlast` | `0x8e233c88` | `0x886e18a4` | `0x886683d8` |
| `0x10` | 4 | ULONG | `nummods` | 149 | 91 | 88 |
| `0x14` | 4 | ULONG | `ulRAMStart` | *not recorded* | *n/r* | *n/r* |
| `0x18` | 4 | ULONG | `ulRAMFree` | *not recorded* | *n/r* | *n/r* |
| `0x1c` | 4 | ULONG | `ulRAMEnd` | *not recorded* | *n/r* | *n/r* |
| `0x20` | 4 | ULONG | `ulCopyEntries` | *not recorded* | *n/r* | *n/r* |
| `0x24` | 4 | ULONG | `ulCopyOffset` | *not recorded* | *n/r* | *n/r* |
| `0x28` | 4 | ULONG | `ulProfileLen` | *not recorded* | *n/r* | *n/r* |
| `0x2c` | 4 | ULONG | `ulProfileOffset` | *not recorded* | *n/r* | *n/r* |
| `0x30` | 4 | ULONG | `numfiles` | 1 | 11 | 10 |
| `0x34` | 4 | ULONG | `ulKernelFlags` | *not parsed, not recorded* | — | — |
| `0x38` | 4 | ULONG | `ulFSRamPercent` | *not parsed, not recorded* | — | — |
| `0x3c` | 4 | ULONG | `ulDrivglobStart` | *not parsed, not recorded* | — | — |
| `0x40` | 4 | ULONG | `ulDrivglobLen` | *not parsed, not recorded* | — | — |
| `0x44` | 2 | USHORT | `usCPUType` | `0x01a6` (SH-4) | `0x01a6` | `0x01a6` |
| `0x46` | 2 | USHORT | `usMiscFlags` | *not recorded* | *n/r* | *n/r* |
| `0x48` | 4 | PTR | `pExtensions` | *not recorded* | *n/r* | *n/r* |
| `0x4c` | 4 | ULONG | `ulTrackingStart` | *not recorded* | *n/r* | *n/r* |
| `0x50` | 4 | ULONG | `ulTrackingLen` | *not recorded* | *n/r* | *n/r* |

Types are the CE `ROMLDR.H` declarations; `PTR`/`LPSTR` fields are 32-bit
physical-space VAs in this image. `IMAGE_FILE_MACHINE_SH4` is `0x01a6`.

Sanity checks — all **VERIFIED by arithmetic** on the recorded A values:

1. `physfirst ≤ pTOC < physlast`:
   `0x8cae1000 ≤ 0x8e232978 < 0x8e233c88`.
2. `physlast − physfirst = 0x01752c88`, which is **exactly** the Clarion
   container's declared payload length at `0x00200000`. The payload is one
   continuous ROM image.
3. `size + 0x54 + nummods*0x20 + numfiles*0x1c = 0x01751978 + 0x1310 =
   0x01752c88 = physlast − physfirst`: the TOC ends exactly at `physlast`.
   This only holds with 28-byte `FILESentry` records (§4), so it doubles as
   the proof for that size.
4. `nummods`/`numfiles` are in the expected range (tens to hundreds);
   `usCPUType = 0x01a6` for every segment.
5. `pTOC` must be page-consistent with `physfirst`: the tool requires
   `romhdr_file = segment_base + pTOC − phys_base` to land inside the image
   and `physfirst` to equal the candidate `phys_base`. In practice this means
   `physfirst` must be 4 KiB aligned.

For B and C **only** `physfirst`, `physlast`, `nummods`, `numfiles` and
`usCPUType` are recorded. Their `ROMHDR` offsets, `pTOC`, `size`,
`dllfirst`/`dlllast`, RAM window, copy table and profile table were never
written down.

Checkable prediction (**HYPOTHESIS**, needs the image): if the TOC ends at
`physlast` in every build, then

| Build | predicted `size` | predicted `ROMHDR` file offset |
| --- | --- | --- |
| B | `0x006e0bbc` | `0x044e0dbc` |
| C | `0x0066776c` | `0x0586796c` |

computed as `span − (0x54 + nummods*0x20 + numfiles*0x1c)` with
`span = physlast − physfirst`. If these do not match the report, the
"TOC is last" assumption is wrong for B/C and the FILESentry size is suspect.

Note the scale difference: A spans 24.4 MB with 149 modules, B/C span 7.2/6.7 MB
with 91/88 modules. B and C are most likely a separate, smaller XIP image
(map/navigation application), not a second build of the whole OS
(**HYPOTHESIS**).

---

## 4. TOC — `TOCentry` (32 B) then `FILESentry` (28 B)

**Status: VERIFIED** (layout, count, name resolution). The wrong-stride defect
below is also proven by arithmetic.

The TOC starts at `ROMHDR + 0x54`:

```
TOCentry  modules : nummods × 0x20   (index 0 … nummods-1)
FILESentry files  : numfiles × 0x1c  (index nummods … nummods+numfiles-1)
```

The split is positional only: `index < nummods` is a module, the rest are
files. Attributes do not distinguish them reliably.

`TOCentry` (module BIB entry), 32 bytes:

| Offset | Size | Type | Field |
| ---: | ---: | --- | --- |
| `0x00` | 4 | DWORD | `dwFileAttributes` |
| `0x04` | 8 | FILETIME | `ftTime` (100 ns ticks since 1601-01-01) |
| `0x0c` | 4 | DWORD | `nFileSize` |
| `0x10` | 4 | LPSTR | `lpszFileName` — VA of a NUL-terminated ASCII name |
| `0x14` | 4 | ULONG | `ulE32Offset` — VA of the module's `e32_rom` |
| `0x18` | 4 | ULONG | `ulO32Offset` — VA of `o32_rom[e32_objcnt]` |
| `0x1c` | 4 | ULONG | `ulLoadOffset` — VA of the module load buffer in ROM |

`FILESentry` (FILES BIB entry), **28 bytes**:

| Offset | Size | Type | Field |
| ---: | ---: | --- | --- |
| `0x00` | 4 | DWORD | `dwFileAttributes` |
| `0x04` | 8 | FILETIME | `ftTime` |
| `0x0c` | 4 | DWORD | `nRealFileSize` (logical size) |
| `0x10` | 4 | DWORD | `nCompFileSize` (on-disk size; `!=` real ⇒ compressed) |
| `0x14` | 4 | LPSTR | `lpszFileName` — VA |
| `0x18` | 4 | ULONG | `ulLoadOffset` — VA of the payload |

Name resolution — the only formula needed to read the TOC:

```
name = C-string at file  p2f(lpszFileName)          // Latin-1, NUL-terminated
p2f(va) = segment_base + (va - physfirst)           // §7
```

A name pointer is valid only when `physfirst ≤ lpszFileName < physlast`. The
tool widens the guard to `0x80000000…0x90000000`; that is safe for this image
but weaker than the real domain.

Build A observed: 149 modules, 1 file, TOC
`0x01951bcc`–`0x01952e88` (`0x54 + 149*0x20 + 1*0x1c`). Names resolve for
`gwes.exe`, `fatfsd.dll`, `diskcache.dll`, `fatutil.dll`, `shell.exe`,
`toolhelp.dll`, `commctrl.dll`, `OBJDLL.dll`, `STDDLL.dll`, `Navi.exe` and
`NaviStateCC.dll` among others. The JSON report carries the full 149-entry
array; only these examples are recorded in the repo, so do not assume the
resolved count equals `nummods`.

**Tool defect.** `parse_romhdr()` walks *all* `nummods + numfiles` entries at a
`0x20` stride. That is correct for modules and for the **first** file entry
only. Consequences:

- build A (`numfiles = 1`): correct, except the walk reads 4 bytes past
  `physlast` (`0x01952e8c` instead of `0x01952e88`);
- builds B/C (`numfiles = 11/10`): file entry *k* is read `4*k` bytes too far,
  so `nRealFileSize`, `nCompFileSize`, the name pointer and `ulLoadOffset` are
  all garbage after the first record. The printed `files (...)` list, and the
  `files` array in the JSON, are unreliable for B/C.

The fix is a separate loop with `0x1c` stride — see §11. Until then, treat
non-zero `numfiles` on B/C as *count only*. The module arrays are unaffected,
so module names/bases from the report are trustworthy for all builds.

---

## 5. `e32_rom` and `o32_rom` — module metadata

**Status: HYPOTHESIS** for this image (layout from the public CE
`ROMLDR.H`/`PEHDR.H`; **no tool in the repo parses these yet**, so nothing
below is verified against the sample).

Each module has one `e32_rom` (module header) and `e32_objcnt` `o32_rom`
records (sections), addressed by the TOC VAs. `o32_rom` is **24 bytes**
(`0x18`); this matches the repo's own earlier observation of 24-byte
`o32_rom`-shaped records at `0x374000`. Two other sizes circulate in older
notes — `0x1c` for `e32_rom` and `0x28` for `o32_rom`; neither matches CE 3–5,
so do not hard-code either.

`e32_rom` (CE 3–5):

| Offset | Size | Type | Field |
| ---: | ---: | --- | --- |
| `0x00` | 2 | u16 | `e32_objcnt` — number of `o32_rom` records |
| `0x02` | 2 | u16 | `e32_imageflags` |
| `0x04` | 4 | u32 | `e32_entryrva` |
| `0x08` | 4 | u32 | `e32_vbase` — module link-time VA |
| `0x0c` | 2 | u16 | `e32_subsysmajor` |
| `0x0e` | 2 | u16 | `e32_subsysminor` |
| `0x10` | 4 | u32 | `e32_stackmax` |
| `0x14` | 4 | u32 | `e32_vsize` — total virtual size |
| `0x18` | 4 | u32 | `e32_sect14rva` |
| `0x1c` | 4 | u32 | `e32_sect14size` |
| `0x20` | 8×`ROM_EXTRA` | `struct info[]` | `e32_unit[]`: `{rva,size}` pairs, indices `0` export, `1` import, `2` resource, `3` exception, `4` security, `5` fixup, `6` debug, `7` image-description, `8` machine-specific |
| `0x20+8*ROM_EXTRA` | 2 | u16 | `e32_subsys` |

Total `0x20 + 8*ROM_EXTRA + 2`: `0x6a` with `ROM_EXTRA = 9` (the value in the
public CE 4.x header), `0xa2` with the PE-style `16`. The record size is
therefore **UNKNOWN for this image** until read; it must be derived from the
first two module headers, not assumed. `e32_unit[EXP]` is the module's export
directory.

`o32_rom` (section), 24 bytes:

| Offset | Size | Type | Field | Meaning |
| ---: | ---: | --- | --- | --- |
| `0x00` | 4 | u32 | `o32_vsize` | virtual (uncompressed) size |
| `0x04` | 4 | u32 | `o32_rva` | RVA inside the module (`vbase`-relative) |
| `0x08` | 4 | u32 | `o32_psize` | physical size **as stored in ROM** |
| `0x0c` | 4 | u32 | `o32_dataptr` | **physical-space VA** of the stored bytes |
| `0x10` | 4 | u32 | `o32_realaddr` | runtime VA where the section is mapped |
| `0x14` | 4 | u32 | `o32_flags` | section characteristics |

`o32_flags` uses PE section bits plus one CE addition:

| Value | Name | Note |
| ---: | --- | --- |
| `0x00000020` | `IMAGE_SCN_CNT_CODE` | executable code |
| `0x00000040` | `IMAGE_SCN_CNT_INITIALIZED_DATA` | `.rdata`, `.data` template |
| `0x00000080` | `IMAGE_SCN_CNT_UNINITIALIZED_DATA` | BSS, no file bytes |
| `0x00002000` | **`IMAGE_SCN_COMPRESSED`** | CE-only; body at `dataptr` is compressed, `psize < vsize` |
| `0x20000000` | `IMAGE_SCN_MEM_EXECUTE` | |
| `0x40000000` | `IMAGE_SCN_MEM_READ` | |
| `0x80000000` | `IMAGE_SCN_MEM_WRITE` | usually RAM-resident + copy table |

**Never read `0x2000` with PE rules.** No standard PE section bit carries that
meaning (`IMAGE_SCN_LNK_REMOVE` is `0x0800`); in a CE XIP it means the section
body is compressed and must be unpacked before it is code. `o32_psize` is then
the *stored* length and `o32_vsize` the unpacked length. Which compressor this
image uses (CE `CEDecompress`/LZX family, or the unexplained `HCXCmp` library)
is **UNKNOWN**; nothing in the repo has decompressed a section yet. Do not
assume map zlib applies.

What these records buy, once parsed:

- exact `(file, VA, size)` per section — the block that firmware.md has been
  looking for since round 1;
- `e32_vbase` per module, which is the only legitimate static module base
  (replace every `module_scan` `(file_base, va_base)` guess, C-382);
- `e32_unit[EXP]`, so the 135-export scan in firmware.md can be attached to
  exact module bases and `DllGetClassObject` targets can be named.

---

## 6. RAM copy table (`ulCopyEntries` / `ulCopyOffset`)

**Status: HYPOTHESIS** (public layout); values *not recorded*.

The copy table is an array of 16-byte `COPYentry` records at
`p2f(ulCopyOffset)`, `ulCopyEntries` of them:

| Offset | Size | Field | Meaning |
| ---: | ---: | --- | --- |
| `0x00` | 4 | `ulSource` | source VA (physical space, inside the ROM) |
| `0x04` | 4 | `ulDest` | destination VA (RAM) |
| `0x08` | 4 | `ulCopyLen` | bytes to copy |
| `0x0c` | 4 | `ulDestLen` | destination extent; if `> ulCopyLen`, zero-fill the tail |

`ulCopyOffset` itself is a VA, like every other pointer in `ROMHDR`, and must
satisfy `physfirst ≤ ulCopyOffset < physlast`. A naive `file = ulCopyOffset`
is wrong.

At boot the kernel copies writable sections from their ROM template into RAM.
**What this explains:** why some VAs are RAM addresses with no file backing
after boot; why a writable section can appear twice (ROM template at
`o32_dataptr`, live copy at `o32_realaddr`); why the "same VA, two meanings"
pattern exists at all.

**What it does not explain:** the `0x0367b180` collision. That VA is a `jsr`
target in the builder *and* the UTF-16 string at file `0xe7b180` under the
guessed data delta `0x02800000` (EXP-2026-11-05-22, C-384). The string only
lands there because a single global delta was applied across sections; the
real cause is the missing per-section map (§5), not the copy table. Nor does
the copy table explain the failed prologue scoring of `module_scan` (C-382).

**Retraction of an older ID.** The 32-byte records at `0x1952b00` (and
`0x1951ee0`) that firmware.md called a "RAM copy list" are **not** the copy
table. Arithmetic puts both inside build A's TOC:

```
TOC start            = 0x1951b78 + 0x54 = 0x1951bcc
0x1951ee0 - TOC      = 0x314 = 24*0x20 + 0x14   → TOCentry[24], field ulE32Offset
0x1952b00 - TOC      = 0xf34 = 121*0x20 + 0x14  → TOCentry[121], field ulE32Offset
```

Both readings start `0x14` bytes into a `TOCentry`, at its `ulE32Offset` field,
so the 32 bytes are the tail of one entry (`ulE32Offset`, `ulO32Offset`,
`ulLoadOffset`) plus the head of the next (`dwFileAttributes`, `ftTime`,
`nFileSize`, `lpszFileName`). That accounts for the 2011 timestamp, the size and
the four `0x8C…0x8E` pointers. The older note's exact
`srcVA`/`srcVA+0x70`/`dstVA` reading is not re-derived here, but the region is
TOC, not a copy table. The real copy table is the 16-byte `COPYentry` array at
`ulCopyOffset`.

---

## 7. VA ↔ file

**Status: VERIFIED** for the physical space (A); derived for B/C;
**HYPOTHESIS** for the module-space step.

This image has **two** address spaces. Conflating them is the root cause of
every failed delta fit.

### Step 1 — physical (ROM) space: `physfirst … physlast`

```
p2f(va) = segment_base + (va - physfirst)
f2p(file) = physfirst + (file - segment_base)
```

| Build | `p2f(va)` | `f2p(file)` | file range |
| --- | --- | --- | --- |
| A | `va - 0x8c8e0e00` | `file + 0x8c8e0e00` | `0x00200200`–`0x01952e88` |
| B | `va - 0x841ffe00` | `file + 0x841ffe00` | `0x03e00200`–`0x044e1aa4`\* |
| C | `va - 0x82dffe00` | `file + 0x82dffe00` | `0x05200200`–`0x058685d8`\* |

\* end = `segment_base + (physlast − physfirst)`; B/C span from §3.

Domain: `physfirst ≤ va < physlast`. Outside it — in particular for every VA in
the `0x02xxxxxx`/`0x03xxxxxx` module band and the `0x1a…`–`0x1d…` RAM band —
`p2f` is undefined and any value it returns is garbage. This formula is what
resolves `ROMHDR` pointers, TOC name/e32/o32/load pointers, `pExtensions`,
`ulCopyOffset` and every `o32_dataptr`.

### Step 2 — module (link-time) space: `e32_vbase + o32_rva`

Module code and data VAs are *not* in the physical domain. The correct
three-field walk (needs §5):

```
given a code/data VA:
  find module m with  e32_vbase[m] <= va < e32_vbase[m] + e32_vsize[m]
  rva  = va - e32_vbase[m]
  find section s with o32_rva[s] <= rva < o32_rva[s] + o32_vsize[s]
  if o32_flags[s] & IMAGE_SCN_COMPRESSED: unpack psize bytes at
      p2f(o32_dataptr[s]) to obtain vsize bytes
  file = p2f(o32_dataptr[s]) + (rva - o32_rva[s])
```

`o32_realaddr` is the RAM address where the section lives after the loader has
done its work; typically equals `e32_vbase + o32_rva` for a read-only XIP
section, and is a RAM address fed by the copy table (§6) for a writable one.
Which of the two this image uses per section is **UNKNOWN** — it is one of the
first things the `e32`/`o32` dump must establish.

The A copy shows why the base matters: it repeats every VA at a different file
offset, so the same `pTOC` resolves to `ROMHDR` `0x03751b78` instead of
`0x01951b78` (derived; the copy is byte-identical). The only quantity that
changes is `segment_base`, which is exactly what a hard-coded delta cannot
express.

### Why the old delta guessing failed

- **C-380/C-381 are RETRACTED.** The "no XIP/section table" negative came from
  searching for the literal strings `B000FF` and `ROMHDR`. `B000FF` is a
  *container* signature that this vendor wrapper does not use, and `ROMHDR` is
  a binary struct with no magic text. The segment was there all along at
  `0x200240`; C-088/C-089 supersede the negative.
- **A single constant cannot be injective.** The map module's `.rdata` fits
  `+0x02000000` (C-086), OBJDLL's `VA 0x03480000` against file `0x7dd200`
  gives `+0x02ca2e00`, the comparator module's data gives `+0x02800000`, and
  the per-instruction band sits at `+0x01f07d5c`. Sections are placed
  independently, so each has its own delta.
- **The collision is structural.** EXP-2026-11-05-22: `0x0367b180` is both a
  `jsr` target and the string at `0xe7b180`; `0x0369d400`/`0x036922cc` land on
  `0x7c`-pipe string data. With one delta those are indistinguishable; with
  `e32`/`o32` records each VA belongs to exactly one module and one section.
- **Prologue scoring was the symptom.** `module_scan`'s per-module bases reach
  65 % only for OLEAUT32, 0–4 % for TFAT/FATUTIL/commctrl/WAVEAPI (C-382,
  EXP-2026-11-05-24). That is what a wrong mapping looks like, not what a
  correct one looks like.

The rule that follows: **physical VAs go through `p2f`; module VAs go through
`e32`/`o32`; never mix, never fit one constant.**

---

## 8. Commands and expected output

**Status: VERIFIED** for the tool; expected values pinned to the sample hash.

```bash
python3 tools/ce_rom_parse.py \
  --image archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img \
  --out /tmp/opencode/ce-rom-report.json
```

The tool scans the **whole** image for `ECEC` in 4 MiB blocks (read-only),
rejects occurrences below `--offset` (default `0x200200`), then validates each
candidate. It prints one block per valid segment and writes the full JSON
report, including every TOC entry with its raw VA fields.

Expected on the EU 2011 sample:

```
image: …/LEAF_2011-2012_QSD-309-101_navi158_eu.img
sha256: 105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307
segments: 5
--- segment base 0x200200 (ECEC 0x200240) ---
pTOC=0x8e232978 size=0x1751978 romhdr=0x1951b78 phys_base=0x8cae1000
nummods=149 numfiles=1 cpu=0x01a6 physfirst=0x8cae1000 physlast=0x8e233c88 ulCopyEntries=<not recorded> pExtensions=0x<va, not recorded>
modules (149): … Navi.exe … NaviStateCC.dll … OBJDLL.dll … STDDLL.dll …
--- segment base 0x2000200 (ECEC 0x2000240) ---
… identical counts, phys range and names (byte copy of A) …
--- segment base 0x3e00200 (ECEC 0x3e00240) ---
… nummods=91 numfiles=11 cpu=0x01a6 physfirst=0x88000000 physlast=0x886e18a4 …
--- segment base 0x4800200 (ECEC 0x4800240) ---
… identical to the previous block (copy of B) …
--- segment base 0x5200200 (ECEC 0x5200240) ---
… nummods=88 numfiles=10 cpu=0x01a6 physfirst=0x88000000 physlast=0x886683d8 …
```

`<not recorded>` marks fields the repo never captured: `ulCopyEntries` and
`pExtensions` are printed by the tool but their values are not written down
anywhere. Everything else above is fixed by EXP-2026-11-05-33/34. The
`files (...)` line is trustworthy for A only and suspect for B/C (§4).

Reproducible self-check of the TOC arithmetic and the address formula — needs
only the JSON, no vendor bytes beyond the report:

```bash
python3 - <<'PY'
import json
r = json.load(open("/tmp/opencode/ce-rom-report.json"))
s = r["segments"][0]                      # build A
h = s["romhdr"]
base, phys, last = s["segment_base"], h["physfirst"], h["physlast"]
end = s["romhdr_offset"] + 0x54 + h["nummods"]*0x20 + h["numfiles"]*0x1c
print("pTOC ok    :", h["physfirst"] <= s["pTOC"] < last)
print("size ok    :", base + s["size"] == s["romhdr_offset"])
print("span==decl :", last - phys == 0x1752c88)
print("TOC at end :", end == base + (last - phys), hex(end))
print("A delta    :", hex(phys - base))
PY
```

Expected: lines 1–4 print `True` (line 4 also shows `0x1952e88`), line 5 shows
`0x8c8e0e00`. The third and fifth lines are build-A constants by design.

Other useful invocations:

```bash
# start scanning at the image start (include wrapper candidates)
python3 tools/ce_rom_parse.py --image <img> --offset 0

# JSON only, then inspect: fields are listed in §3, TOC entries in §4
python3 -c 'import json;print(json.load(open("/tmp/opencode/ce-rom-report.json"))["segments"][0]["modules"][0])'
```

`tools/selftest.py`, `cardcheck.py`, `l2check.py` do **not** cover firmware;
this parser has no synthetic fixture. Every firmware verification is tied to
the image hash above.

---

## 9. What this does and does not establish

Established:

- the embedded image is a standard CE XIP segment, not an opaque blob;
- segment base, signature, `pTOC`, `size` and `ROMHDR` for build A, and the
  segment bases/counts/ranges for A×2, B×2, C;
- module names, hence module identity, across the 149-entry A TOC (every name
  that resolves is a plausible OS/navi module);
- the physical↔file map for each segment;
- that A's TOC ends exactly at `physlast`.

Not established:

- `e32_rom`/`o32_rom` contents, section map, compression scheme;
- `dllfirst`/`dlllast`, RAM window, copy table, profile table, extensions;
- the meaning of the boot block and the `NKOK` field;
- which build the car actually boots (A/B/C selection is UNKNOWN);
- the reader functions: `.cmp`/`.ind`, `DRSTR001.DAT`, tiles and `HDD_INFO`
  parsers remain unlocated. The TOC makes them findable; it does not find them.

---

## 10. Discrepancies found while writing this document

Code vs documentation, all checked by reading
`tools/ce_rom_parse.py`, EXP-2026-11-05-33, EXP-2026-11-05-34 and
[`firmware.md`](firmware.md):

| # | Finding | Where | Impact |
| ---: | --- | --- | --- |
| 1 | File TOC entries are read at a `0x20` stride; `FILESentry` is `0x1c`. Proven by `TOC end == physlast`. | `ce_rom_parse.py` `parse_romhdr()` | A correct (1 file, +4 bytes read); B/C file arrays garbage |
| 2 | `ROMHDR` bytes `0x34`–`0x43` (`ulKernelFlags`, `ulFSRamPercent`, `ulDrivglobStart`, `ulDrivglobLen`) are never read, though `TODO.md` lists them. | `ce_rom_parse.py` | fields missing from the report |
| 3 | `ulE32Offset`, `ulO32Offset`, `lpszFileName`, `ulCopyOffset`, `pExtensions` are emitted as raw VAs with no `p2f` conversion and no e32/o32/copy walk. | `ce_rom_parse.py` | report is not directly usable for Ghidra |
| 4 | No assertion that `segment_base + size == romhdr_offset`, nor that `physlast − physfirst` equals the container's declared payload length. | `ce_rom_parse.py` | a false-positive segment could pass |
| 5 | "Builds A, B and C each have a duplicate copy" contradicts the observation table: 5 segments = A×2, B×2, C×1. | EXP-33 and EXP-34, Interpretation | C has no duplicate in the report |
| 6 | EXP-33 and EXP-34 are near-duplicate records of the same run (same claims, same numbers); -34 adds no new observation. | both EXPs | duplicate evidence trail |
| 7 | `ECEC` byte list written as `43 45 43 45`; the file/tool has `45 43 45 43`. | `firmware.md` §Firmware container | a literal search for the documented bytes does not find the signature |
| 8 | "15 × u32 table" at `0x00200200`; it is the `0x40`-byte CE boot block, i.e. 16 dwords up to `ECEC` at `+0x40`. Also it is the segment base, not container metadata. | `firmware.md`, EXP-24 | mislabels the CE entry block |
| 9 | "Section table is a dead end" (records at `0x374000`, `0x3e0060`): both offsets lie inside build A's segment (`0x200200`–`0x1952e88`), so they can be genuine `o32_rom` arrays reached via `ulO32Offset`. `0x3e0060` is **not** in build B's wrapper (B starts at `0x03e00000`, about 58 MiB higher). | `firmware.md` | stale negative, re-check with the TOC |
| 10 | "`0x1952b00` is a RAM copy list (32-byte records)": both `0x1951ee0` and `0x1952b00` are TOC entries at phase `0x14` (the `ulE32Offset` field). Real `COPYentry` is 16 bytes. | `firmware.md`, EXP-29 | wrong structure identification |
| 11 | `ROMHDR` sanity checks are ticked in `TODO.md` but no values were recorded for `dllfirst`/`dlllast`/`ulRAM*`/`ulCopy*`/`pExtensions`/`ulTracking*`. | `TODO.md` Step 1 | cannot be re-derived without the image |
| 12 | `e32_rom`/`o32_rom` sizes quoted in older notes (`0x1c`, `0x28`) do not match the CE 3–5 headers (`0x20 + 8*ROM_EXTRA + 2`; `0x18`). | older notes | do not hard-code a record size |

---

## 11. Follow-ups

1. Fix the file-entry stride in `tools/ce_rom_parse.py`: walk modules with
   `0x20`, files separately with `0x1c` (`nRealFileSize`, `nCompFileSize`,
   `lpszFileName`, `ulLoadOffset`), and stop at `physlast`.
2. Add the missing `ROMHDR` fields and convert every pointer field through
   `p2f`, flagging any pointer outside `physfirst…physlast`.
3. Read the first two `e32_rom` records and settle `ROM_EXTRA` / record size
   from the data, then dump `o32_rom` for one small module (`toolhelp.dll`) and
   one large one (`Navi.exe`), including `o32_flags` with
   `IMAGE_SCN_COMPRESSED`.
4. Dump the `COPYentry` array and test whether writable sections' `realaddr`
   are RAM copies of their `dataptr` template.
5. Then the `TODO.md` Step 2 goal: `tools/cerom.py` with `romhdr`, `modules`,
   `files`, `sections`, `va2file`, `file2va`, `extract`, plus a Ghidra memory
   map or reconstructed PE per module.
6. Re-run the known anchors with exact VAs: `0x6fab2c` → `0x6faeb0` →
   `0x6fb05c`, `MAL_DataVol_getOffset`, `0x0369d400`.

See [`firmware.md`](firmware.md) for the surrounding wrapper, code recovery and
the dead-end list, and `docs/experiments/EXP-2026-11-05-33`/`-34` for the raw
run.
