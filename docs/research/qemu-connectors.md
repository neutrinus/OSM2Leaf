# `-M ze0` connectors: how the outside world reaches the emulated unit

Status: **plan** (PO, 2026-11-22). Nothing here is measured; every row names
the task that will measure it. Hardware facts come from
[`docs/hardware/head-unit.md`](../hardware/head-unit.md).

Marek's request (2026-11-22): send GPS coordinates and touch input into QEMU,
and consider the other connectors. This page fixes the architecture so that
many agents can build connectors at the same time.

## Rules

1. **A chip behind a serial line is a peer, not QEMU code.** GPS receiver,
   display unit, audio microcontroller, Bluetooth module and the VCAN
   microcontroller each talk to the SoC over a UART. QEMU only carries the
   bytes: every line is a host chardev (M8.H1 for SCIF, M8.H3 for the external
   UARTs). The chip model is a Python program in `tools/ze0_peers/` that
   connects to the socket. Peers have a `--selftest`, need no QEMU to develop,
   and never conflict with each other.
2. **QEMU patches only for blocks inside the SoC or on its bus** (OHCI, SSI,
   I²C, GPIO, NOR flash, display surface). Still a patch series on QEMU
   11.1.3, never a fork (M8.A11).
3. **Patch names carry the task:** `ze0-hNN-<slug>.patch` for task M8.H*NN*
   (sorted after the numbered `ze0-00NN` series). Two tasks never share a
   number, so parallel PRs do not collide on file names. A patch that edits
   the machine file keeps its hunk to one registration line where possible.
4. **Static read first.** Each connector starts with a `Step: reader` task
   that documents the protocol in `docs/firmware/<driver>.md`; the peer is
   written against that page, and the live test comes last.
5. **Every peer has a control socket** so `tools/ze0_ui.py` (M8.H7) can script
   it: `gps LAT LON`, `tap X Y`, `key NAME`, `ignition on`.
6. **No vendor bytes, no screenshots in the repo.** Screens hold vendor
   graphics: keep them under `archive/`, commit hashes and descriptions.

## Connector table

| Connector | Unit side | Carrier in QEMU | Protocol read | Peer / model | Live test |
| --- | --- | --- | --- | --- | --- |
| GPS receiver | `SCI7:`, `navdrv.dll` | chardev `sci7` (M8.H1, M8.H66) | M8.H27; RX path in [`docs/firmware/serial-scif-rx.md`](../firmware/serial-scif-rx.md) (M8.H66) | `ze0_peers/gps.py` M8.H30 | M8.H31, track M8.H33, map matching M8.H34 |
| Speed pulse, gyro, reverse | `kepdrv.dll`, timers `0xffc5a000` | patch M8.H32 | M8.H28 | in the patch, driven by the GPS peer | M8.H32 |
| Position without sensors | saved position in flash | flash file M8.H18 | M8.H19 | `ze0_seed.py` M8.H20 | M8.H20; demo mode M8.H21 |
| Touch panel | display unit frames on `SCI3:`, command `51` (`docs/firmware/lcddrv.md`) | chardev `sci3` (`ze0-h02`), peer `panel.py --sci3` | M8.H35 (done), M8.H36 | `ze0_peers/panel.py` M8.H38 | M8.H39 (tap reaches kepdrv, locked by UI state), live window M8.H40 |
| Hard keys, knob | to be found (M8.H37) | as touch, or the micon peer | M8.H37 | `panel.py` / `micon.py` | M8.H39 |
| Screen out | DU + 2DG (`ze0-gfx`) | console (`display=` on, M8.H4) or `pmemsave` | M8.C1e, M8.C1f, M8.H4 | — | `ze0_screenshot.py`, VNC/gtk via `run.sh --display` (M8.H4) |
| Audio microcontroller | `SCI1:`, `anwdrv.dll` | chardev `sci1` | M8.H43 | `ze0_peers/micon.py` M8.H44 | M8.H45 |
| Sound out | SSI `0xffe00000`, `wavessi1/2` | `ze0-h46-ssi-audio.patch`: register stub + HPB-DMAC 11/12/13 PCM sink, `-M ze0,ssi-audio=ID` | in M8.H46 | `tools/ze0_wavcheck.py` (`ssi-selftest` positive control) | Model verified; **no guest playback** in M8.H46, unblock M8.H47, prompt M8.H48 |
| Vehicle CAN | `UAT3:`, `CAN.dll` | chardev `uat3` (M8.H2, M8.H3) | M8.H49 | `ze0_peers/vcan.py` M8.H50 | M8.H51, EV screens M8.H52 |
| Power / ACC | `PowerMonitor` | vehicle peer + GPIO | M8.H53 | `vcan.py` | M8.H54 |
| Bluetooth | `SCI8:`, `BT_FW.dll` | chardev `sci8` | M8.H55 | `ze0_peers/bt.py` M8.H56 | M8.H56 |
| USB host | OHCI `0xffe70400` | patch M8.H57 | in M8.H57 | QEMU `usb-storage` M8.H58 | M8.H58 |
| Second SD slot | SD host port 1 | `run.sh --sd2` M8.H17 (done) | — | QEMU `sd-card` | M8.H17: `DSK8:` / `\UserSD` mounts (EXP-2026-11-24-M8.H17) |
| NOR flash | `FMD1:` | patch M8.H18 | in M8.H18 | QEMU pflash | M8.H18, M8.H54 |
| I²C | `0xffc71000` | logging patch M8.H59 | M1.40 (static limit) | NACK + log | M8.H59 |
| GPIO | `0xffc41000`…, `0x19400000` | logging patch M8.H60 | M1.40 (static limit) | latches + log | M8.H60 |
| Camera | `VIN.dll` | M8.H61 (low) | `docs/firmware/camera.md` | test picture | M8.H61 |
| Traffic (TMC) | `fmmdrv.dll`, tuner via micon | message injection, no radio | M8.H62 | call recipe | M8.H63 |
| Debug console | `SCI6:` | serial log today; chardev `sci6` | M8.H65 | a terminal | M8.H65 |
| Watchdog / reset | to be found | M8.H67 | M8.H67 | log | M8.H67 |
| On-chip DMAC | `0xff801000` (305 writes in one EU2011 boot, M8.H22 census) | shared by SD/SCIF drivers; today unmodelled | `docs/research/full-system-emulation.md` §1 | register stub for channels 0-13 + poll read-back | M8.H1 (SCIF DMA), M8.C10 (SD DMA) — standalone model unassigned |
| Unnamed P4 blocks | `0xffc40000`, `0xffcc0000`, `0xff800000`, `0xfffec000` (M8.H22 census) | unmodelled; no name in full-system-emulation.md §1 | firmware literal scan needed first | none until named | unassigned — name from firmware before a device task |

## Tooling around the connectors

| Need | Task |
| --- | --- |
| One-command L4 gate for a card | M8.H13 (`tools/l4check.py`), first generated card M8.H64 |
| Which files and bytes the firmware reads | M8.H8 (SD trace), M8.H10 (tile read-watch) |
| Which functions ran | M8.H9 (TCG plugin coverage), M8.H69 (symbols) |
| L3 results equal L4 results | M8.H11 |
| Fast start, repeatable runs | M8.H5 (`savevm`), M8.H6 (determinism), M8.H25 (time budget) |
| Scripted scenarios | M8.H7 (`tools/ze0_ui.py`), M8.H41 (route), M8.H42 (screen catalogue) |
| See inside the guest | M8.H15 (debug zones), M8.H23 (PC sampler), M8.H68 (process list), M8.H22 (unmodelled accesses) |
| Other inputs | M8.H12 (US card), M8.H16 (test-mode kernel), M8.H26 (`run.sh --card`) |
| For humans | M8.H24 (quick start), M8.H40 (live window) |
| Keep the series healthy | M8.H14 (CI applies the patches) |

## Order

Ready with no dependency: every `Step: reader` row above, M8.H1, and the
tooling rows except M8.H10/M8.H41/M8.H42. The first end-to-end goals are
**M8.H31** (a GPS fix moves the position) and **M8.H39** (a tap changes the
screen); both need M8.H1 plus their protocol page.
