# EXP-2026-11-05-48: `cerom.py memmap` — the section table `rommap.py` consumes

- **Status:** done (tool, synthetic ROM); the A/B run is still open
- **Date:** 2026-11-05
- **Sample:** synthetic CE ROM built by `tools/cerom.py` (no vendor bytes);
  SHA-256 `46aca5325bcacaed645380f094d708b8888843ff29b93dce6165542cc0195622`,
  29696 bytes
- **Claims:** C-569
- **Supersedes:** none
- **Superseded by:** none

## Question

Can `tools/cerom.py` emit the per-`o32` section table that
`tools/l3_harness/rommap.py` already consumes — and a Ghidra script mapping the
same blocks — without ever passing compressed bytes off as raw section
contents?

## Hypothesis

The `o32_rom` fields are already parsed and validated (C-568, C-559): one block
per section at `o32_realaddr`, stored bytes at `p2f(o32_dataptr)`, `size` =
`o32_psize`, plus `o32_vsize` and the `IMAGE_SCN_COMPRESSED` bit. A JSON writer
plus a thin `createMemoryBlock` script should therefore be reproducible from
the documented layout alone; compressed sections must be flagged and must never
end up in a Ghidra block, because no CE decompressor exists (M1.2/M1.3).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | synthetic ROM written to `/tmp/opencode/cerom-memmap/synthetic-rom.img` |
| SHA-256 | `46aca5325bcacaed645380f094d708b8888843ff29b93dce6165542cc0195622` |
| Size | 29696 bytes |
| Layout | `ECEC` at `0x240`, ROMHDR at `0x1200`, 2 modules, 4 sections (2 compressed) |
| Tool version | `python3 tools/cerom.py` (worktree, no vendor data; no commit hash recorded) |

Build the sample (deterministic, no vendor bytes):

```bash
mkdir -p /tmp/opencode/cerom-memmap
python3 - <<'PY'
import sys
sys.path.insert(0, "tools")
import cerom
rom, exp = cerom.build_synthetic_rom()
open("/tmp/opencode/cerom-memmap/synthetic-rom.img", "wb").write(rom)
print(len(rom), hex(exp["va_base"]))
PY
```

## Method

```bash
cd /home/krzesimir/PycharmProjects/OSM2Leaf.session-ZMxuBT
python3 -m py_compile tools/cerom.py
python3 tools/cerom.py --selftest
python3 tools/cerom.py /tmp/opencode/cerom-memmap/synthetic-rom.img \
  memmap --out /tmp/opencode/cerom-memmap/memmap.json --pretty \
  --ghidra-script /tmp/opencode/cerom-memmap/cerom_map.py

# rommap.py rejects compressed sections by default ...
python3 tools/l3_harness/rommap.py convert \
  --report /tmp/opencode/cerom-memmap/memmap.json \
  --out /tmp/opencode/cerom-memmap/rommap.json

# ... and accepts the same report with an explicit skip.
python3 tools/l3_harness/rommap.py convert \
  --report /tmp/opencode/cerom-memmap/memmap.json --skip-compressed \
  --out /tmp/opencode/cerom-memmap/rommap.json
python3 tools/l3_harness/rommap.py validate /tmp/opencode/cerom-memmap/rommap.json

python3 tools/selftest.py --only cerom
```

CLI shape implemented (TODO M1.5/M9.1):

```
cerom.py IMG memmap [--modules M1,M2] [--out FILE] [--pretty]
                    [--exclude-compressed] [--ghidra-script FILE]
cerom.py IMG ghidra ...        # alias of memmap
```

## Observations

`--selftest`: `cerom selftest: 93 checks OK (synthetic ROM, no vendor data)` —
46 before this experiment, 47 added for `memmap`/`ghidra`.

`memmap --out … --pretty --ghidra-script …`:

```
wrote /tmp/opencode/cerom-memmap/memmap.json (2 module(s), 4 section(s), 2 compressed)
wrote /tmp/opencode/cerom-memmap/cerom_map.py (2 block(s))
```

The emitted JSON (one CE segment; `romhdr` values elided here, full dict in the
file):

```json
{
  "schema": "osm2leaf.cerom.memmap/v1",
  "generator": "tools/cerom.py memmap",
  "image": "synthetic-rom.img",
  "image_size": 29696,
  "image_sha256": "46aca5325bcacaed645380f094d708b8888843ff29b93dce6165542cc0195622",
  "image_sha256_scope": "whole file (29696 bytes)",
  "segments": [{
    "segment_index": 0, "segment_base": "0x200", "phys_base": "0x8cae1000",
    "pTOC": "0x8cae2000",
    "romhdr": {"physfirst": 2360217600, "physlast": 2360807424, "nummods": 2,
               "ulRAMStart": 2382364672, "ulRAMEnd": 2399141888, "...": "..."},
    "counts": {"modules": 2, "sections": 4, "compressed": 2,
               "skipped_compressed": 0, "skipped_modules": []},
    "modules": [
      {"module": "NK.EXE", "name": "NK.EXE", "vbase": "0x8ce00000",
       "sections": [
         {"name": "sec0", "va": "0x8ce01000", "file_offset": 20480,
          "size": 1024, "vsize": 1024, "characteristics": "0xc0000040",
          "compressed": false, "rwx": "rw-"},
         {"name": "sec1", "va": "0x8ce02000", "file_offset": 21504,
          "size": 256, "vsize": 2048, "characteristics": "0xc0002040",
          "compressed": true, "rwx": "rw-"}]},
      {"module": "NAVI.EXE", "name": "NAVI.EXE", "vbase": "0x8d000000",
       "sections": [
         {"name": "sec0", "va": "0x8d001000", "file_offset": 25600,
          "size": 512, "vsize": 768, "characteristics": "0x60000020",
          "compressed": false, "rwx": "r-x"},
         {"name": "sec1", "va": "0x8d002000", "file_offset": 26112,
          "size": 128, "vsize": 256, "characteristics": "0xc0002040",
          "compressed": true, "rwx": "rw-"}]}
    ]
  }]
}
```

`rommap.py convert` without `--skip-compressed` (negative control):

```
error: NK.EXE: sections[1] (sec1): compressed section (characteristics 0xc0002040); the CE decompressor is not implemented, so it cannot be loaded. Pass --skip-compressed to omit it explicitly.
error: NAVI.EXE: sections[1] (sec1): compressed section (characteristics 0xc0002040); the CE decompressor is not implemented, so it cannot be loaded. Pass --skip-compressed to omit it explicitly.
exit=1
```

With `--skip-compressed` and `validate`:

```
wrote /tmp/opencode/cerom-memmap/rommap.json (2 blocks, 2 skipped)
RESULT: PASS (2 blocks, segment 0x200)
exit=0
```

Generated Ghidra script, block list (`cerom_map.py`):

```python
IMAGE = '/tmp/opencode/cerom-memmap/synthetic-rom.img'
# (name, va, file_offset or None, size, read, write, execute)
BLOCKS = [
    ('NK.EXE/sec0', 0x8ce01000, 0x5000, 1024, True, True, False),
    ('NAVI.EXE/sec0', 0x8d001000, 0x6400, 512, True, False, True),
]
...
        block = mem.createMemoryBlock(name, addr, size, False)
```

with the header line `# Omitted compressed sections: NK.EXE/sec1, NAVI.EXE/sec1`.

`python3 tools/selftest.py --only cerom`:

```
tool:cerom  PASS  0.08s

passed=1 failed=0 skipped=0 total=1 time=0.08s
selftest: OK
```

## Interpretation

- **FACT:** `memmap` (alias `ghidra`) emits `segments[].modules[].sections[]`
  with `name`, `va` (`o32_realaddr`), `file_offset` (`p2f(o32_dataptr)`),
  `size` (`o32_psize`), `characteristics` (`o32_flags`), `compressed`,
  and the extra `vsize`, `rwx`. `rommap.py convert` consumes it with no
  transformation and `validate` returns `PASS` (2 blocks, 2 compressed skipped).
- **FACT:** a compressed section is flagged in the JSON (`compressed: true`) and
  is rejected by `rommap.py` unless `--skip-compressed` is explicit; the
  generated Ghidra script never creates a block for it and lists it in a
  comment. `--exclude-compressed` drops them from the JSON and reports the
  count (`skipped_compressed: 2`).
- **FACT:** `--modules` filters case-insensitively and keeps TOC order; an
  unknown name exits `2` with `error: no module named Nope.dll in this ROM`.
- **OBSERVED:** section names are synthetic (`sec%d`) because `o32_rom` carries
  no name; `rwx` follows the same rule as `rommap.py` (`MEM_*` bits, falling
  back to the content bits).
- **HYPOTHESIS:** the same JSON is valid for image A/B because `o32_rom` is
  layout-identical (C-568); the per-build run needs the vendor image, which is
  absent from this checkout.
- **UNKNOWN:** whether Ghidra's `Memory.createMemoryBlock(name, addr, size,
  overlay)` + `putBytes` works under 12.2/Jython; the script is not executed
  here (no Ghidra). It is marked as generated, not verified.

## Conclusion

`tools/cerom.py` now has `memmap`/`ghidra` (TODO M1.5, M9.1 tool half) and its
`--selftest` pins 47 new assertions: block count, per-section
`va`/`file_offset`/`size`, `compressed`, `rwx`, the module filter, the
`--exclude-compressed` count, the `rommap.py convert`+`validate` round-trip, and
the CLI/alias/script output. `docs/research/l3-ghidra.md` gained the implemented
invocation in its one-time setup.

Still open: the M1.5 "done when" (Ghidra opens `Navi.exe` with correct
addresses, checked against one known string) and the M9.1 "every A+B section is
listed" half — both need the vendor image and a Ghidra run. `docs/format/cerom.md`
§5/§11 still describes `e32`/`o32` as HYPOTHESIS for this image and was not
updated here (outside this task's file set).

## Follow-ups

- [ ] Run `memmap` on image A and B, record the section counts and check one
      known string VA (`0x004e7d28`) against the block list.
- [ ] Add `--image A,B` / multi-segment selection when the real image is
      available (M9.1 wording); today it is one CE segment per run.
- [ ] Execute the generated script under Ghidra 12.2/Jython and pin
      `createMemoryBlock` behaviour.
- [ ] Decompress the flagged sections (M1.2/M1.3) so RW globals are not zero.
