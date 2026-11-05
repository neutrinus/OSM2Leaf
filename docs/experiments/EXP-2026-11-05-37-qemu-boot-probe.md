# EXP-2026-11-05-37: SoC identification and a QEMU boot probe of the CE kernel

- **Status:** done (positive, partial boot)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image, first 256 MiB (`curl -r 0-268435455`), SHA-256
  of those 268,435,456 bytes
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (full image reference: `105e2032…6307`, 8,057,257,984 B per HTTP
  `content-length`)
- **Claims:** C-530…C-537
- **Supersedes:** none (refines the emulation verdicts in
  `docs/research/feedback-loop.md` Option B and `docs/format/firmware.md`)
- **Superseded by:** none

## Question

Which SoC does the unit use, which peripherals does the firmware touch, and
how far does the real Windows CE kernel get on a stock QEMU SH-4 CPU with no
board model?

## Hypothesis

Exploratory. Expected: an SH-4 part with a custom peripheral set; the kernel
dies early in `OEMInit` on an unknown register.

## Inputs

| Item | Value |
| --- | --- |
| Image | first 256 MiB of the EU 2011 image |
| Kernel image | B, image start `0x3e00200` (also C, `0x5200200`) |
| App image | A, image start `0x200200` |
| Tools | `tools/cerom.py`, `tools/ce_qemu_probe.py`, `sh4-linux-gnu-objdump` 2.42 (`binutils-sh4-linux-gnu`), QEMU 8.2.2 (`qemu-system-misc`, Ubuntu 24.04) |

## Method

```bash
curl -sS -r 0-268435455 -o head256.img https://files.viaaq.eu/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img

# BSP / build strings
strings -n5 head256.img | grep -E '\.pdb$' | sort -u
strings -n6 head256.img | grep 'Windows CE Kernel'

# Section flags of drivers (code is never compressed)
python3 tools/cerom.py head256.img --image-start 0x3e00200 sections SDHC.dll

# Literal-pool constants of nk.exe .text (file 0x03e01200, vsize 0x4c770)
dd if=head256.img of=nk_text.bin bs=1 skip=$((0x3e01200)) count=$((0x4c770))
sh4-linux-gnu-objdump -D -b binary -m sh4 --adjust-vma=0x88001000 -EL nk_text.bin > nk.dis
grep -oE 'mov\.l\s+0x[0-9a-f]+,r[0-9]+\s+! [0-9a-f]+' nk.dis   # then filter >= 0xa4000000
# same per driver: .text section from `cerom.py sections`, realaddr as VMA

# Boot probe
python3 tools/ce_qemu_probe.py head256.img --seconds 4
python3 tools/ce_qemu_probe.py head256.img --seconds 4 --patch 0x88048b70=0900
python3 tools/ce_qemu_probe.py head256.img --kernel 0x5200200 --seconds 3
```

## Observations

### Strings

- `Windows CE Kernel for Hitachi SH Built on Oct 23 2008 at 19:31:09`,
  `SH-4 Kernel`, `Booting Windows CE version %d.%2.2d for (%s)`.
- PDB roots: `C:\WINCE500\platform\CETUS\target\SH4\retail\` (B: 41 modules,
  C: 49), `C:\fuji\WINCE500\PRIVATE\Automotive\…` (ResUsage, DResUsage,
  AstLogApi, LogSaver), `C:\WINCE500\PBWorkspaces\AppRoot\apps\…` (A),
  `C:\WINCE500\PBWorkspaces\UpdateNK_Root\apps\UpdateNK\binary\…` (B updater),
  and once `C:\WINCE500\platform\R0P7772A00020S\target\SH4\retail\SdCardLch.pdb`
  (C).
- No string `SH77`, `SH-Navi`, `R8A77` anywhere in A/B/C.

### Section flags

For every module checked (`nk.exe`, `coredll.dll`, `filesys.exe`, `gwes.exe`,
`serial_scif`, `SDHC`, `gdisubdrv`, `GPIO`, `flash`) the `.text` section has
flags `0x60000020`/`0x68000020` (not compressed); the compressed sections
(`0x2000`) are the RW data sections.

### Literal-pool register addresses

`nk.exe` (B), selected, with counts: `ff000000`–`ff00001c` (MMU/CCN, 24),
`f4000000`/`f4001000`/`f4003000`, `ff200000`–`ff200020`, `ff801418`,
`ff802000`–`ff802064`, `ff804000`–`ff804088` (`ff804040` 42×, `ff804044` 41×),
`ffc0880c`–`ffc08814`, `ffc5a028`/`ffc5a02c`, `ffc80030`/`34`/`3c`/`44`,
`ffd80008`/`0c`, `ffd81010`, `ffe00004`, `ffe10004`, `ffe20004`,
`ffe4600c`/`10`, `ffe4c020`, `ffe4d020`, `ffe70094`, `ffe70800`–`ffe70858`,
`ffe80004`/`08`, `fff80008`–`fff80018`, `b9000000`, `b9100000`,
`b9300000`–`b9300024`, `b9400000`–`b9400008`, `b9800000`,
`a8000020`–`a800002b`, `a9980028`–`a9980a0c`, `a99bf000`, `a9a0d000`,
`a9a3f000`.

Drivers (B unless noted):

| Module | Constants |
| --- | --- |
| `serial_scif` | `ffe40014`, `ffe41000`…`ffe48014` (8 channels), `ff801000`, `ffc08000`, `a9999000`–`a999f880` |
| `serial_uat` | `b9b00000`, `b9c00000`, `b9d00000`, `b9e00000`, `a99a0000`, `ff801000`, `ffc08000` |
| `SDHC` | `ffe4c000`, `ffe4d000`, `ff801000`, `ffc08000`, `a9980a00`, `a99c1000`, `a99e1000` |
| `GPIO` | `ffc41000`, `ffc42000`, `ffc43000`, `b9400000` |
| `I2C` | `ffc71000` |
| `CAN` | `b9400000` |
| `navdrv` | `ffc5a000`, `ffc5b000`, `b9800000` |
| `kepdrv` | `ffc5a000`, `ffc5b000`, `ffd81000`, `a9a01000` |
| `fmmdrv` | `ffc55000` |
| `wavessi1` / `wavessi2` (C) | `ffe0000c`, `ff801000`, `ffc08000`, `a9981000`, `a9991000` |
| `Bolero` | `b9a00000` |
| `VSram` | `a9a40000`, `a9ac0000` |
| `FlashManager` | `a9b40000` |
| `gdisubdrv`, `ddddifull`, `DspDrv` | many `0x10000000`-based constants, no `0xffxxxxxx` |
| `UsbOhci` (C) | `07ff0000` (5×), `07000000`, `10000000` |
| `lcddrv`, `flash`, `VIN`, `bcndrv`, `PowerMonitor`, `dtvdrv`, `BeepDrv`, `IOLIB` | none in these ranges |

Kernel debug output routine (nk `0x8804cfa4`): loop over a UTF-16 string;
poll `0xffe46010` (16-bit) until bit `0x20` set, write the byte to
`0xffe4600c`, clear bits `0x60` of `0xffe46010`.

### Pre-partition layout (first bytes)

MBR: one partition, type `0x0b`, LBA start `0x6400400/512`. Non-zero data at
`0x200000`–`0x1a00000` (A), `0x2000000`–`0x3800000` (A copy),
`0x3e00000`–`0x4500000` (B), `0x4800000`–`0x4f00000` (B copy),
`0x5200000`–`0x5900000` (C), `0x5c00000`–`0x5e00000` (starts with ASCII
`BASSB`), `0x6000000` (`HDD_INFO` copy). The `u32` at each CE image header
(`0x3e00000`: `0x006e18a4`; `0x5200000`: `0x006683d8`) equals
`physlast − physfirst`. No boot code before `0x200000` (36 non-zero bytes =
MBR).

### Boot probe

Load: B → phys `0x08000000` (7,215,268 B), A → phys `0x0cae1000`
(24,456,328 B); PC = `0x8800ebd0` (`nk.exe` entry); `-M none -cpu sh7785
-m 512M`.

Unpatched (B and C identical): 15 distinct unmodelled accesses, in order
`ff00001c` W, `ff00000c` W, `ff000008` W, `ff000000` W, `ff000010` W,
`ff000000` R, `ff000004` W, `ff00001c` R, `ffc8003c` R/W, `ffe70858` R/W,
`ffe70800` W, `ffe70804` W, `ffe70808` R (forever). Code (`0x88048b4c`):
set bit 7 of `0xffe70858`, write 1 to `0xffe70800`, write 1 then 3 to
`0xffe70804`, poll `0xffe70808 & 0xc0000000 == 0xc0000000`.

Patched `0x88048b70=0900`: 50 distinct accesses; after the list above:
`ffe70094`, `ffe7009c`, `ffe7080c`, `ffe7081c`, `ff802044`, `ff802048`,
`ff804040`, `ff802000`, `ff80201c`, `ff802010`, `ff804000`…`ff804024`,
`ff802064`, `ffd80004`, `ffd80010`, `ffd80008`, `ffd8000c`, `ffd8001c`,
`ffd80014`, `ffd80018`, `ff804044`, then `f4000000`-array writes (cache
flush), `ff000024` R, `ff00000c` R. One exception:
`0x180 illegal_instruction` at `pc=0x00005b90`, `pr=0x880237b8`,
`vbr=0x8800ec10`; the call site loads `0x5b90` with `mov.w` and `jsr`s to it.
Final PC after 4 s: `0x8803d266` (just after a `sleep` at `0x8803d264`).
With `-m 256M` the kernel also reads `0x10000000` and writes
`0x19300010`–`0x19300018` (outside RAM; logged as invalid).

## Interpretation

- **FACT:** Code sections are uncompressed; driver MMIO addresses can be read
  statically today (C-530).
- **FACT:** the kernel debug port is an SH-style SCIF at `0xffe46000` whose
  register layout matches QEMU's `sh_serial` (C-534).
- **FACT:** stock QEMU's `sh7785` CPU executes the CE 5.0 kernel through
  early init into the scheduler; the stop is caused by missing MMU control
  registers (`MMUCR` writes rejected, so the kernel page at VA `0x5800`…
  `0x5bxx` is unmapped) and by the absence of a timer interrupt (C-533).
- **OBSERVED:** the peripheral map (table in
  `docs/research/full-system-emulation.md` §1) differs from SH7750/SH7751;
  the CPG `MSTPCR` offsets and the TMU layout match the SH7780 family (C-532).
- **HYPOTHESIS:** the SoC is a Renesas SH-NaviJ-family part (SH7772x), from
  the BSP name `R0P7772A00020S` and the driver set (C-531).
- **OBSERVED:** the SD card holds no bootloader; the IPL is on-board (C-535).
- **UNKNOWN:** the blocks at `0xffe70000`, `0xfff80000`, area 4
  (`0x10000000`) and area 6 (`0x19300000`); whether retail debug output is
  enabled; which of B/C the IPL boots (C-529 stays open).

## Conclusion

Full-system emulation is not blocked by the CPU: the remaining work is a
board model. New doc `docs/research/full-system-emulation.md`, new tool
`tools/ce_qemu_probe.py` (with a self-test of its log parser), claims
C-530…C-537, TODO M8.

## Follow-ups

- [ ] M8.A: `ze0` QEMU machine to F0 (debug log).
- [ ] M8.B: INTC + TMU for F1.
- [ ] Find the kernel-page setup and `OEMInit` in `nk.exe` and name the
  `0xffe70000` block.
- [ ] Read the IPL handshake area `0x08000020`–`0x0800002b` (boot arguments?).
