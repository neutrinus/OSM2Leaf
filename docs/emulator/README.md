# Running the Nissan Leaf ZE0 head unit under QEMU

One page from a fresh checkout to a PNG of the emulated screen. Every command
below was run from a clean shell on this host on 2026-11-22 and is recorded,
with its exit code, in
[`EXP-2026-11-22-M8.H24-emulator-quickstart.md`](../experiments/EXP-2026-11-22-M8.H24-emulator-quickstart.md).
If a command fails for you, the EXP names the step and the exact output the
author saw.

The machine is the out-of-tree `-M ze0` QEMU device in
[`tools/qemu-ze0`](../../tools/qemu-ze0/README.md); it boots the EU 2011
Windows CE images from the SD card, runs them to the navigation map, and lets
the host save what the display unit is scanning out. A rendered map of central
London (roads, shields, parks, street labels) is what you should get at the end
of step 5. The screen is vendor map data: the page writes it under `$W` and
nothing of it is committed.

## 0. Prerequisites

| Need | Why | Check |
| --- | --- | --- |
| Linux x86-64, ≥ 4 cores | build and emulation host | `nproc` |
| ~2 GiB free under `$HOME` | QEMU tarball 127 MiB + source tree 0.8 GiB + build tree 0.9 GiB | `df -h "$HOME"` |
| QEMU build deps (`glib2-devel`, `pixman-devel`, `gcc`, `make`, `patch`, `tar`) | `build.sh` compiles `sh4-softmmu` only | `test -x /usr/bin/patch` |
| Python 3.10+ (stdlib only) | the `tools/` record and screenshot helpers | `python3 --version` |
| Network on the first build | QEMU is never vendored; `build.sh` downloads the pinned tarball | — |
| 8.1 GB free for the card | the full EU 2011 card image | `df -h "$HOME"` |

`qemu-img` is **not** needed: `tools/qemu-ze0/mkoverlay.py` writes the qcow2
overlay. The stock `qemu-system-sh4` in `/usr/bin` is **not** the ze0 build —
it has no `ze0` machine. You must build it with `build.sh`.

## 1. Set up shell variables

Run every command on this page from the repository root (the clean checkout):

```bash
cd /path/to/OSM2Leaf                                       # the clean checkout
QEMU=${XDG_CACHE_HOME:-$HOME/.cache}/qemu-ze0/build/qemu-system-sh4
W=$HOME/leafre-work/qemu-run                                # scratch: outside the repo
mkdir -p "$W"
```

`$W` is deliberately outside the repository: the card image, the overlay and
the PNGs are vendor data and must not be committed (`.gitignore` drops
`*.img`; the page never `git add`s `$W`).

## 2. Build the emulator (first run only)

```bash
bash tools/qemu-ze0/build.sh --jobs 8
```

What it does: downloads and SHA-256-checks QEMU 11.1.3 (`5a8289c7…b84b22`),
extracts it to `$HOME/.cache/qemu-ze0`, applies the thirteen `ze0` patches,
configures `--target-list=sh4-softmmu`, builds, and requires `-M help` to list
`ze0`. To put the cache on another disk add `--srcdir /some/disk/qemu-ze0`
(then set `QEMU=/some/disk/qemu-ze0/build/qemu-system-sh4`). Nothing is
written inside the repository. A second run is incremental and takes seconds.

Check the result:

```bash
"$QEMU" --version | head -1            # QEMU emulator version 11.1.3
"$QEMU" -M help | grep ze0             # ze0  Nissan Leaf ZE0 navigation unit (SH-4A, research skeleton)
```

Exit status: `0` on success, `1` build/machine failure, `2` usage error,
`3` network needed or a missing tool/input, `4` `--check-version` delta.

## 3. Get the images

The emulator needs two things: the 256 MiB firmware head (both CE images live
in it) and the full ~7.5 GiB EU 2011 SD card. In this checkout `archive/` is a
git-ignored symlink to where your data already lives (`archive/head256.img`,
`archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img`); the `wt`
`pre-start` hook links it into each worktree. If both paths exist, skip to
step 4. Otherwise download them from <https://files.viaaq.eu/sd-images/> into
`$W`, and use `$W/head256.img` / `$W/card.img` in place of the `archive/`
names below:

```bash
# firmware head: the first 256 MiB of the EU 2011 card
curl -fL --retry 3 --connect-timeout 20 -r 0-268435455 \
  -o "$W/head256.img" \
  https://files.viaaq.eu/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img

# the whole card (needed for the SD partition and the map tiles)
curl -fL --retry 3 --connect-timeout 20 \
  -o "$W/card.img" \
  https://files.viaaq.eu/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img
```

Verify the hashes (the EXP quotes these): `head256.img` is
`92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`,
`card.img` is
`105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`:

```bash
sha256sum "$W/head256.img" "$W/card.img"
```

If you downloaded them, use `--image "$W/head256.img"` / `--sd "$W/card.img"`
in step 5 instead of the `archive/` names.

## 4. Prepare the IPL patch and the overlay

The running kernel never joins ROM image A (the applications) by itself; an
IPL patch reproduces what the real unit's boot loader leaves in RAM. The
overlay is a qcow2 over the card so the factory image is never written.

```bash
# 1. what the IPL would leave in RAM (a header comment + 8 "PHYS HEXBYTES" lines)
python3 tools/ze0_ipl.py patch archive/head256.img -o "$W/ipl.txt"

# 2. qcow2 overlay over the card (QEMU's sd-card needs a power-of-two size)
python3 tools/qemu-ze0/mkoverlay.py \
  archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img "$W/eu2011.qcow2"
```

`ze0_ipl.py patch` prints
`chain pointer var 0x89e43c90 …, XIPCHAIN at phys 0x0e6f0000, RAM end 0x8c6e0000`
and `wrote …/ipl.txt (8 lines)` (the 8 `PHYS HEXBYTES` lines after the header
comment). `mkoverlay.py` prints the overlay's backing file. Both exit `0`.

## 5. Boot and take a screenshot

Run the emulator in one terminal and grab the screen from another after about
20–30 seconds. `run.sh` blocks until its timeout, so start it in the background
or a second terminal:

```bash
# terminal 1 — boot the EU 2011 card (blocks up to 300 s, then exits)
bash tools/qemu-ze0/run.sh --qemu "$QEMU" \
  --image archive/head256.img --verinf QSD-302-100 --mapdb 16-16 \
  --ipl-patch "$W/ipl.txt" --sd "$W/eu2011.qcow2" \
  --icount shift=0,sleep=off --timeout 300 --workdir "$W/run"
```

```bash
# terminal 2 — after the "run.sh: ze0 machine" line; run once at ~5 s, again at ~20–30 s
python3 tools/ze0_screenshot.py screen --monitor "$W/run/hmp.sock" -o "$W/run/shot.png"
```

The monitor socket exists within a few seconds and the screen is black at
first; `screen` exits `0` either way, so read the printed pixel count, not the
exit code. After about 20 s it prints the two DU planes it composed and the
pixel count, e.g.:

```
plane 2: mode 0x1002 800x480 at 0x0e932800 stride 800 window (0,0)
plane 4: mode 0x4002 800x480 at 0x0e9f2000 stride 2368 window (1376,193)
..../shot.png: 382721 non-black pixels
```

Open `$W/run/shot.png` — it is 800 × 480 and should show the map. If it says
`0 non-black pixels` the screen has not been drawn yet; wait and re-run the
`screenshot` command (the guest is not disturbed). `run.sh` writes under
`$W/run`: `serial.log` (the kernel debug text), `qemu.log` (every `-d` item;
it grows ~10–25 MB/s of boot), `registers.txt`, `memmap.json`, and `hmp.sock`
(the HMP monitor the screenshot tool talks to).

Why the options:

| Option | Meaning |
| --- | --- |
| `--image archive/head256.img` | CE images read by the machine's built-in loader (M8.A3) |
| `--kernel 0x3e00200` (default) | EU 2011 kernel is image B at that offset |
| `--verinf QSD-302-100 --mapdb 16-16` | the unit map code / map-DB window the launcher checks (EU card; `ze0-0010`) |
| `--ipl-patch "$W/ipl.txt"` | joins ROM image A so the applications start (`ze0-0012`) |
| `--sd "$W/eu2011.qcow2"` | the SD card on host port 0 (`ze0-0008`/`0009`) |
| `--icount shift=0,sleep=off` | guest time independent of host load, repeatable traces |
| `--timeout 300` | stop after 300 s; 0 = run until killed |
| `--workdir "$W/run"` | where the log, socket and screenshots go (default is a fresh `mktemp -d`) |

For a longer look (the navigation UI itself settles within 15 minutes) raise
`--timeout`; the map is already on screen in well under a minute.

**Live screen (M8.H4).** The machine exposes the display unit's planes as a
QEMU graphic console (`ze0-gfx`). Add `--display vnc=127.0.0.1:0` (or `gtk`,
`sdl`, or the `--vnc` shorthand) to `run.sh` and open the VNC display, or
save the same image from the monitor: `screendump shot.ppm ze0-gfx`. The
console frame and `ze0_screenshot.py screen` differ by 0 pixels
(EXP-2026-11-23-M8.H4). Without `--display` QEMU stays headless
(`-display none`), exactly as before.

## 6. Typical times (measured on 8 cores, 2026-11-22)

| Step | Time | Note |
| --- | --- | --- |
| `build.sh` from the tarball | 4 min 56 s | measured here on 8 cores; incremental relink ~1 s |
| firmware head download | ~7 s | 256 MiB, ~40 MB/s |
| full card download | ~3 min 15 s | 7.5 GiB, ~40 MB/s |
| `ze0_ipl.py patch` | ~1 s | 8 lines |
| `mkoverlay.py` | < 1 s | empty overlay, 256 KiB |
| boot to first non-black screen | **20 s** | measured from `run.sh` start (socket at ~2 s, black) to a 382 721-pixel PNG at ~27 s; the map is drawn by ~20 s |
| full UI / navigation screen | < 15 min | EXP-2026-11-22-M8.C1f |

The `qemu.log` grows fast: `-d unimp,guest_errors,int,invalid_mem` writes
hundreds of MB in minutes. For a long run pass `--log /dev/null` to `run.sh`.

## 7. What works, what does not

The connector architecture (what reaches the guest and how) is
[`docs/research/qemu-connectors.md`](../research/qemu-connectors.md); this
table is only the measured state of each device on the `ze0` machine today.
"Works" means a run on the EU 2011 card was observed to do it; the EXP column
names the record.

| Device / path | State | Evidence / task |
| --- | --- | --- |
| SH-4A CPU, DRAM, kernel boot | works — kernel to `filesys.exe`/`device.exe` | EXP-2026-11-20-M8.B5 |
| Debug SCIF serial log (`--serial log`) | works — kernel debug text on serial 0 | EXP-2026-11-19-M8.A6, M8.B6 |
| TMU / RTC (`CurMSec` real time) | works | EXP-2026-11-20-M8.B2, M8.B3 |
| SD host port 0 + HPB-DMAC, card unlock & mount (`Store Mgr Ready! [DSK1:]`) | works | EXP-2026-11-21-M8.C1b |
| Applications in ROM image A (via `ipl-patch`) | works — `Navi.exe`/`AuiApp.exe` `Process Create!!!` | EXP-2026-11-22-M8.C1d |
| Display unit vblank + 2DG display lists | works — map rendered | EXP-2026-11-22-M8.C1e, C1f |
| Screenshot (`ze0_screenshot.py screen`) | works — 800 × 480 PNG | EXP-2026-11-22-M8.C1f |
| Audio (HPB-DMAC serial channel 10 → SCIF1 TX) | partial — frames transmit, no peer | M8.C2a |
| Touch panel | not yet — no input path | M8.H36, M8.H38 |
| Hard keys / knob | not yet | M8.H37 |
| GPS receiver (`SCI7:`) | not yet | M8.H30, M8.H31 |
| Vehicle CAN (`UAT3:`) | not yet | M8.H50 |
| Bluetooth (`SCI8:`) | not yet | M8.H56 |
| USB host | not yet | M8.H57 |
| Second SD slot (`run.sh --sd2`) | works — port 1 card mounts `DSK8:` / `\UserSD` | EXP-2026-11-24-M8.H17 |
| NOR flash / saved position | not yet | M8.H18 |
| Live screen in a host window | works — VNC/gtk via `run.sh --display` (M8.H4) | EXP-2026-11-23-M8.H4 |
| UI layer (buttons, status bar) | not yet — plane 2 is fully colour-keyed | EXP-2026-11-22-M8.C1f O6 |
| US 2011 / 2014 / 2016 cards | untested on this machine | M8.H12 |

## 8. Troubleshooting

- **`-M help` has no `ze0`** — you are running the distro
  `qemu-system-sh4` (e.g. `/usr/bin/qemu-system-sh4`), not the `build.sh`
  output. Use `$QEMU` from step 1 and check it is
  `$HOME/.cache/qemu-ze0/build/qemu-system-sh4`.
- **`build.sh`: `NETWORK NEEDED` (exit 3)** — the pinned tarball is not cached
  and the download failed. Fix network, or copy `qemu-11.1.3.tar.xz` into the
  cache (`$XDG_CACHE_HOME`/`$HOME/.cache` `/qemu-ze0`) and re-run.
- **`build.sh`: a patch does not apply (exit 4 with `--check-version`)** — the
  series and the QEMU release disagree; you are on a version other than
  11.1.3. Only 11.1.3 is pinned (M8.A11).
- **`qemu-system-sh4: -drive … Could not open … No such file`** — the overlay
  path is wrong. `run.sh` still exits 0 (QEMU exited early); look at the first
  lines of the work dir's output. Re-run step 4's `mkoverlay.py`.
- **`screen` says `0 non-black pixels`** — boot has not reached the 2DG yet
  (around 20 s); wait and re-run the command. A screenshot taken too early is
  black, not an error.
- **`screen` cannot connect to the monitor** — `run.sh` has not created
  `hmp.sock` yet, or already stopped. Confirm the process is running and the
  file exists (`ls "$W/run/hmp.sock"`); the socket exists only while QEMU runs.
- **Every application logs `Launch Process Not Create!!!`** — the IPL patch
  is missing or stale. Re-run step 4 and pass the fresh `--ipl-patch`.
- **The launcher logs an empty `VerInf:` and starts `FailSafe.exe`** — the
  unit record is missing; pass `--verinf QSD-302-100 --mapdb 16-16` (EU 2011).
- **The map is drawn but the buttons/status bar are missing** — expected: the
  UI plane is fully colour-keyed in this build (C1f O6).
- **A long boot fills the disk** — `qemu.log` at `-d …` grows fast. Pass
  `--log /dev/null` to `run.sh`.

## Where the knowledge lives

- [`tools/qemu-ze0/README.md`](../../tools/qemu-ze0/README.md) — the pinned
  machine, patches, build options, exit codes.
- [`docs/research/qemu-connectors.md`](../research/qemu-connectors.md) — how
  each outside device reaches the guest, and the task that measures it.
- `docs/experiments/EXP-2026-11-2{1,2}-M8.C1{b..f}*.md` — the boots that
  reached the map, with commands and numbers.
- `docs/experiments/EXP-2026-11-22-M8.H24-emulator-quickstart.md` — this
  page's own validation: each command above with its exit code.
- [`debugging.md`](debugging.md) — how to debug the firmware: gdbstub, HMP
  monitor, debug serial, `tools/ze0_gdb.py`, key kernel addresses, traps.
- [`running.md`](running.md) — the unit's own kernel (NK1) with a card and
  the serial-line peers (display/touch, GPS, micon) in one command,
  `tools/ze0_launch.py`; which peer is real protocol and which a model.
