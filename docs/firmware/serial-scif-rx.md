# `serial_scif.dll` receive path — EU2011 build B (M8.H66)

Source: EU2011 `archive/head256.img` (SHA-256
`92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`),
build B at `--image-start 0x3e00200`. Every VA below is attributed through
`tools/cerom.py` to `serial_scif.dll` (module 62, load `0x88673000`,
vbase `0x03980000`, executable sec0 `0x03981000`..`0x0398f322`, vsize
`0xe322`). Reproduce with the commands in the companion EXP.

## 1. Verdict

Every SCIF receive channel that the firmware configures is served the same
way: **a receive FIFO register (FRDR, `SCIFn+0x14`) is the source of an
HPB-DMAC channel armed as a two-plane 128-byte transfer; the driver is
notified by that DMA channel's completion interrupt.** There is no
per-channel poll of FRDR by the stream driver for these channels. Two planes
of `0x80` bytes are used (DCR `0x00052000`, DTCR count `0x80`); the interrupt
is raised only after both planes complete (M8.H1 O6). The same shared
dispatcher arms the transmit channel (`FTDR`, `SCIFn+0x0c`), so the mechanism
is selected by which register the caller passes — base `0x14` (RX) vs `0x0c`
(TX) — not by an opaque per-channel flag; the task falsifier does not fire.

## 2. Per-channel map

The `r4` channel argument at each call to the DMA dispatcher `fn 0x0398d084`
is quoted from `sh4dis` (the instruction after each `jsr` to the dispatcher):
ch0=`0`, ch1=`10` (TX) and `1` (RX), ch2=`2`, ch3=`3`, ch5=`5`, ch7=`7`,
ch8=`19` (TX) and `20` (RX). The receive side is the call whose function
holds an FRDR pool word.

| SCIF | SCIF base / FRDR (VA) | RX via | DMA ch (r4 arg) | DMA completion INTEVT / ISR (nk.exe) | RX init fn |
| --- | --- | --- | --- | --- | --- |
| 1 | `0xffe41000` / `0xffe41014` | FRDR → HPB-DMAC, 2×0x80 planes | `1` (DSAR=FRDR, C2a O1) | `0xb80` / `fn 0x8803e654` | `fn 0x03987f54` |
| 3 | `0xffe43000` / `0xffe43014` | FRDR → HPB-DMAC, 2×0x80 planes | `3` (DSAR=FRDR, C2a O1) | `0xbc0` / `fn 0x8803e6cc` | `fn 0x039896bc` |
| 7 | `0xffe47000` / `0xffe47014` | FRDR → HPB-DMAC, 2×0x80 planes | `7` (DSAR=FRDR, C2a O1) | `0xc40` / `fn 0x8803e7bc` | `fn 0x0398b650` |
| 8 | `0xffe48000` / `0xffe48014` | FRDR → HPB-DMAC, 2×0x80 planes | `20` (RX; TX is `19`) | INT2-bit-19 IRQ row `0x9c0` / `fn 0x8803fb84` (see §5) | `fn 0x0398c198` |
| 0 | `0xffe40014` (FRDR only) | FRDR → HPB-DMAC | `0` | `0xb60` / `fn 0x8803e618` | `fn 0x0398740c` |
| 2 | `0xffe42000` / `0xffe42014` | FRDR → HPB-DMAC | `2` | `0xba0` / `fn 0x8803e690` | `fn 0x03988b0c` |
| 5 | `0xffe45000` / `0xffe45014` | FRDR → HPB-DMAC | `5` | `0xbe0` / `fn 0x8803e708` | `fn 0x0398a204` |
| 6 | `0xffe46000` (base only) | see §5 | — (no +0x14 pool word) | kernel debug SCIF | `fn 0x0398ad4c` |

The RX RAM planes quoted from the init functions: ch1 `0xa999a800` /
`0xa999a880`, ch3 `0xa999c800` / `0xa999c880`, ch7 `0xa999e800` /
`0xa999e880`, ch8 `0xa999f800` / `0xa999f880`. These are the destinations
M8.H1 fills when a host byte arrives on the chardev.

Corpus counts from `tools/scif_rx_map.py`: `16` SCIF register-literal pool
words, `9` call sites to the dispatcher, `2` DMAC base literals, `10`
`SCI_*` exports. SCIF4 (`0xffe44000`) has **no** register-literal pool word
and SCIF6 has no `+0x14` FRDR word; they are not asserted as RX-DMA channels
here.

## 3. The shared DMA dispatcher

`fn 0x0398d084` (VA from `sh4xref --to 0x0398d084`, 9 literal-pool call sites):

- `0x0398d098`: `mov #23,r3; cmp/hs r9,r3` → channel index in `r4`/`r9`
  must be < 23.
- `0x0398d16a`: `mov #21,r3; cmp/ge r3,r9`: index < 21 → loads HPB-DMAC
  base `0xffc08000` (pool `0x0398d3a0`, `r10=9`); index ≥ 21 → general DMAC
  `0xff801000` (pool `0x0398d3a4`, `r10=5`). SCIF8's channels 19/20 are HPB.
- `0x0398d1a2`: `mov.w 0x0604` VirtualCopy flags, the same value the SDHC
  driver uses (M8.C1 O1): the physical `0xffc08000` is mapped to a runtime
  virtual window, so `0x1fc08xxx` are not static literals.
- Establishes the per-channel register block (DSAR/DDAR/DTCR/DPTR/DCR at
  `+0x200`/`+0x204`/`+0x208`/`+0x22c`/`+0x228`) and the interrupt triple
  `+0x80c` (status) / `+0x810` (clear) / `+0x814` (enable), matching C1/C2a.

The `mov #N,r6` values passed to a RETAILMSG thunk (IAT slot `0x01f340ac`,
`fn 0x03987400`) are **debug identifiers**, not DMA channel numbers; the
real channel is the `r4` argument above.

## 4. Error-flag handling

The RX init functions set up two DMA planes and clear the channel's
interrupt status through the dispatcher's `+0x810`/`+0x814` pair. The DMA
ISR in nk.exe (`fn 0x8803e654` etc.) masks INT2 bit 19 in `0xff804040`,
clears its own bit in DINTMR0 `0xffc08814`, and returns a SYSINTR; the exact
per-channel bit is `1 << ch` for ch1/3/7 (C2a O2). The receive path itself
does not poll SCIF error flags in the stream driver; errors are reported
through the same DMA completion event and the RETAILMSG thunk. Deeper error
classification is **not established** by this static read.

## 5. Registry per-port configuration

Decoded build-B `default.hv` (regenerated with `nk_decomp.py files`,
SHA-256 `653227735d2a19f9ab2d6bbe2543a4035eb96d17ec0ad766cac93ba23a17493a`)
has 7 `Drivers\Launch\SCIF*` keys plus `HSCIF`, each
`Dll = serial_scif.dll`, `Prefix = SCI`, `Index`/`DeviceArrayIndex` equal to
the channel number (SCIF0..7; HSCIF = 8), `WaterMarker = 8`, distinct
`Priority256`. There is no registry value selecting IRQ vs DMA: the
mechanism is fixed in code (FRDR/FTDR literal), so the falsifier condition
("two channels with different mechanisms and no configuration value")
does not occur.

## 6. What an emulator must raise

Following M8.H1: bytes arrive on the `sciN` chardev into `sh_serial`'s SCIF
FIFO; when the driver has armed a receive channel (DSAR=FRDR, two planes),
the model drains the FIFO into the two guest RAM planes, reloads DTCR /
switches DPTR, and **raises the HPB-DMAC channel completion interrupt**
(INTEVT per §2, INT2 bit 19). The driver's ISR then acknowledges it. The
emulator does not need to emulate SCIF receive status bits for this path;
SCR bit 4 (receiver enable) is the firmware-side gate (M8.H1 O5).

## 7. Open items

- Ch6 (kernel debug SCIF) has no FRDR pool word; its RX is handled by the
  kernel debug path (`ze0_serial.py`, `fn 0x8804cfa4`), not the stream-driver
  DMA dispatcher. Not covered by this task's table.
- SCIF8's completion INTEVT is inferred from the OAL row `0x9c0` because
  ch20 has no dedicated row; confirm by an L3/L4 run with an sci8 peer.
- Deeper per-channel error-flag branch in the ISR is not resolved.
