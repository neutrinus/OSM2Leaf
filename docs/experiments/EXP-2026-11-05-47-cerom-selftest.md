# EXP-2026-11-05-47: `cerom.py` self-test on a synthetic CE ROM

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** synthetic ROM built by `cerom.build_synthetic_rom()` (29,696 B,
  SHA-256
  `46aca5325bcacaed645380f094d708b8888843ff29b93dce6165542cc0195622`);
  no vendor data in this environment, so no image SHA-256 is pinned.
- **Claims:** C-516, C-517 (parser contract re-checked synthetically), C-563
  (registry discovery); C-568 below is **proposed**, `claims.md` was not edited
  in this session.
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `tools/cerom.py` (TODO M1.1) have a vendor-free unit test that pins the
`romhdr`, `va2file`/`file2va`, TOC/FILES, `o32` section-flag, `e32` and
`exports` results, runs from `tools/selftest.py`, and fails loudly on a corrupt
`ECEC`?

## Hypothesis

Yes. The parser takes an arbitrary byte buffer plus `image_start`, so a minimal
two-module ROM can be synthesised from the structures documented in
`docs/format/firmware.md` and `EXP-2026-11-05-35`: `ECEC` at image start
+ `0x40`, `pTOC`, a `0x54`-byte `ROMHDR` (`nummods = 2`, `numfiles = 1`,
`usCPUType = 0x01a6`), two 32-byte `TOCentry` records, one 28-byte
`FILESentry`, two `o32` sections per module (one `IMAGE_SCN_COMPRESSED`) and an
`e32` export directory with two named exports. Exact values are known ahead of
time, so every assertion is equality, not a range check.

## Inputs

| Item | Value |
| --- | --- |
| Tool | `tools/cerom.py` |
| Tool SHA-256 | `ee98f2dfb850ce88289952674f6c8e7be24bb7cf935d00baec2f7423ee8a5a77` |
| Python | 3.14.4 |
| Synthetic ROM | 29,696 B, `image_start 0x200`, `va_base 0x8cae1000`, `pTOC 0x8cae2000`, `ROMHDR` file `0x1200` |
| Platform | Linux, no hardware, no image file |

Synthetic layout (built by `build_synthetic_rom()`):

| File offset | Content |
| --- | --- |
| `0x0240` | `ECEC`, `pTOC = 0x8cae2000`, `toc_off = 0x1000` |
| `0x1200` | `ROMHDR` `0x54` B + `TOCentry[2]` `0x40` B + `FILESentry[1]` `0x1c` B |
| `0x2000` | names `NK.EXE\0`, `NAVI.EXE\0`, `default.hv\0` |
| `0x4000` / `0x4200` | `e32_rom` (units at `+36`) / `o32_rom[2]` of `NK.EXE` |
| `0x5000` | `NK.EXE` section 0, uncompressed: export directory, 3 arrays, 2 names |
| `0x5400` | `NK.EXE` section 1 payload, `IMAGE_SCN_COMPRESSED` |
| `0x6000` / `0x6200` | `e32_rom` / `o32_rom[2]` of `NAVI.EXE` (no exports) |
| `0x7000` | `default.hv` payload, `real = 0x200`, `comp = 0x100` |

## Method

```bash
python3 -m py_compile tools/cerom.py
python3 tools/cerom.py --selftest            # no image argument
python3 tools/selftest.py --only cerom
python3 tools/cerom.py --help | head -20

# Keep a copy of the fixture for the CLI checks below.
mkdir -p /tmp/opencode/cerom-selftest
python3 - <<'PY'
import hashlib, sys
sys.path.insert(0, "tools")
import cerom
rom, _ = cerom.build_synthetic_rom()
open("/tmp/opencode/cerom-selftest/rom.img", "wb").write(rom)
bad = bytearray(rom); bad[0x240:0x244] = b"XXXX"
open("/tmp/opencode/cerom-selftest/corrupt.img", "wb").write(bad)
print(len(rom), hashlib.sha256(rom).hexdigest())
PY
python3 tools/cerom.py /tmp/opencode/cerom-selftest/rom.img romhdr
python3 tools/cerom.py /tmp/opencode/cerom-selftest/rom.img modules
python3 tools/cerom.py /tmp/opencode/cerom-selftest/rom.img files
python3 tools/cerom.py /tmp/opencode/cerom-selftest/rom.img sections NK.EXE
python3 tools/cerom.py /tmp/opencode/cerom-selftest/rom.img exports NK.EXE
python3 tools/cerom.py /tmp/opencode/cerom-selftest/rom.img va2file 0x8ce02000
python3 tools/cerom.py /tmp/opencode/cerom-selftest/rom.img file2va 0x5040
python3 tools/cerom.py /tmp/opencode/cerom-selftest/corrupt.img romhdr; echo $?
```

## Observations

`py_compile` reported no errors. `--selftest` needs no image and exits 0:

```
$ python3 tools/cerom.py --selftest
cerom selftest: 46 checks OK (synthetic ROM, no vendor data)
$ echo $?
0
```

`tools/selftest.py` discovers `cerom` through the `--help` probe and runs it as
a subprocess:

```
$ python3 tools/selftest.py --only cerom
tool:cerom  PASS  0.08s

passed=1 failed=0 skipped=0 total=1 time=0.08s
selftest: OK
$ echo $?
0
```

```
$ python3 tools/selftest.py --list | grep cerom
tool:cerom              --selftest      tools/cerom.py --selftest
```

The 46 checks cover (grouped as in `selftest()`):

- header: discovered `image_start 0x200`, `va_base 0x8cae1000`,
  `pTOC 0x8cae2000`, `ROMHDR` file offset `0x1200`, the **full 22-field
  `ROMHDR` dict** compared to `synth_romhdr()`, `nummods/numfiles/usCPUType`
  `2/1/0x01a6`, `physfirst/physlast`, and agreement with an explicit
  `--image-start`;
- `va2file`/`file2va`: `va2file(va_base) == 0x200`, plus both round-trips for
  six offsets (`0x2000`, `0x4000`, `0x4200`, `0x5000`, `0x5040`, `0x7000`);
- TOC/FILES: 2 modules, names `NK.EXE`/`NAVI.EXE`, full `attrib/ft/size/e32/o32/load`
  records, one file `default.hv` with `real 0x200`/`comp 0x100`, payload at
  file `0x7000`, case-insensitive `module("navi.exe")`;
- `e32`/`o32`: `objcnt 2`, `vbase 0x8ce00000`/`0x8d000000`, `entryrva`,
  `vsize`, `timestamp`, export dir `(0x1000, 0x80)`; two sections per module
  with exact `(rva, vsize, psize, dataptr file, realaddr, flags)`,
  `[False, True]` compressed flags, `rva2file(0x1010) == 0x5010` and
  `rva2file(0x2010) is None` (compressed);
- exports: `[(1, "MAL_DataVol_getOffset", 0x1100),
  (2, "MAL_DataVol_getSize", 0x1200)]` (ordinal base 1) and an empty list for
  the module without exports;
- CLI: `main([path, "romhdr"])` and `main([path, "exports", "NK.EXE"])` both
  return 0 and print the expected `va_base` / export name;
- negative control: `XXXX` at image start + `0x40` raises `ValueError`
  mentioning `ECEC`, with both an explicit `image_start` and default discovery.

`--help` is unchanged in shape; the new flag is the second option:

```
usage: cerom.py [-h] [--image-start IMAGE_START] [--selftest]
                [image]
                {romhdr,modules,files,sections,exports,va2file,file2va,extract} ...
```

Existing subcommands on the fixture (raw output):

```
$ python3 tools/cerom.py rom.img romhdr
image_start  0x00000200
va_base      0x8cae1000
pTOC         0x8cae2000  (ROMHDR at file 0x00001200)
... nummods 0x00000002, numfiles 0x00000001, usCPUType 0x000001a6
$ python3 tools/cerom.py rom.img modules
  0 NK.EXE                       attr=001c size=   32768 load=8ce00000 vbase=8ce00000 objs=2
  1 NAVI.EXE                     attr=001c size=   16384 load=8d000000 vbase=8d000000 objs=2
$ python3 tools/cerom.py rom.img files
  0 default.hv                   attr=0040 real=     512 comp=     256 load=8cae7e00 (file 0x00007000)
$ python3 tools/cerom.py rom.img sections NK.EXE
NK.EXE: vbase=8ce00000 vsize=00008000 entry=8ce01000 export=00001000+80 import=00000000+0
  rva=00001000 vsize=00000400 psize=00000400 dataptr=8cae5e00 (file 0x00005000) realaddr=8ce01000 flags=c0000040
  rva=00002000 vsize=00000800 psize=00000100 dataptr=8cae6200 (file 0x00005400) realaddr=8ce02000 flags=c0002040 COMPRESSED
$ python3 tools/cerom.py rom.img exports NK.EXE
    1 MAL_DataVol_getOffset                    rva=00001100
    2 MAL_DataVol_getSize                      rva=00001200
$ python3 tools/cerom.py rom.img va2file 0x8ce02000
0x0000321200
$ python3 tools/cerom.py rom.img file2va 0x5040
0x8cae5e40
```

Corrupt `ECEC` (`XXXX` at `0x240`), via the CLI subcommand path:

```
$ python3 tools/cerom.py corrupt.img romhdr
Traceback (most recent call last):
  ...
ValueError: ECEC signature not found
$ echo $?
1
```

Missing arguments behave as before (argparse usage error, exit 2):

```
$ python3 tools/cerom.py
cerom.py: error: the following arguments are required: image
$ echo $?
2
```

## Interpretation

- **FACT:** `tools/cerom.py` parses a vendor-free synthetic ROM end-to-end:
  `ECEC` + `pTOC` + 22-field `ROMHDR`, `TOCentry`, `FILESentry`, `e32_rom`,
  `o32_rom` and the export directory all reproduce the values the builder
  wrote, bit for bit. This is an independent re-check of the structure claimed
  in C-516/C-517 that does not depend on the vendor image.
- **FACT:** The self-test is registered: `tools/selftest.py` lists and runs
  `tool:cerom` (C-563 mechanism), so TODO M1.1's "done when
  `tools/selftest.py` runs it" holds.
- **OBSERVED:** 46 checks, all equality assertions; no tolerance windows, no
  vendor bytes, no network, no hardware.
- **OBSERVED:** `rva2file` returns `None` for an RVA inside a section with
  `IMAGE_SCN_COMPRESSED` (`0x2000`), and the export walk only uses the
  uncompressed section. That is the code path the real image exercises for
  `Navi*.dll` RW data, now pinned synthetically.
- **OBSERVED:** a corrupt `ECEC` fails with `ValueError`, not a plausible
  `ROMHDR`; the CLI still surfaces it as an uncaught traceback with exit 1
  (pre-existing behaviour, deliberately unchanged).
- **UNKNOWN:** the pinned numbers are for the synthetic image only. Images A,
  B and C (C-524) still need the vendor bytes to be pinned end-to-end; this
  test pins the *parser*, not the firmware.
- **HYPOTHESIS:** none needed; the test is a regression guard for future edits
  to the parser (e.g. M1.3 `decompress`, M1.5 `ghidra`), which must keep these
  46 checks green.

## Conclusion

No format knowledge changed, so `docs/format/firmware.md` and
`docs/research/claims.md` were not touched (session scope). Added
`cerom.py --selftest` (fixture builder + 46 assertions) and this record.
Proposed ledger row:

- **C-568** — `tools/cerom.py --selftest` builds a 29,696-byte synthetic CE
  ROM (2 modules, 1 file, `nummods = 2`, `numfiles = 1`, `usCPUType = 0x01a6`,
  2 `o32` sections per module, one `IMAGE_SCN_COMPRESSED`, 2 named exports)
  and pins the full `ROMHDR` dict, `va2file`/`file2va` round-trips, module/file
  names, section flags and file offsets, export ordinals/names/RVAs, and a
  corrupt-`ECEC` negative; it needs no image and runs from
  `python3 tools/selftest.py --only cerom`. **VERIFIED** (tool, synthetic),
  confidence **H**.

## Follow-ups

- [ ] Pin images A, B and C end-to-end (`romhdr` + one module's `exports`)
      once the vendor bytes are available; keep the expected values in the EXP,
      not in `cerom.py`.
- [ ] After M1.3 (`cerom.py decompress`), add a compressed-section fixture whose
      decompressed length equals `vsize` to the same self-test.
- [ ] Consider pinning `extract` output bytes in the self-test (currently only
      `main()` return codes and stdout are checked for the CLI path).
