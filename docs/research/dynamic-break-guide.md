# Dynamic break guide (firmware reader)

Static analysis is closed for the NaviStateCC object vtable. This is the exact
capture plan for the first hardware/debug session.

## Primary — MAL volume accessor

Break on one of:

| Symbol | VA | File offset |
| --- | --- | --- |
| `MAL_DataVol_getOffset` | `0x03498d48` | `0x7f5f48` |
| `MAL_DataVol_getSize` | `0x03498d28` | `0x7f5f28` |

While opening a map page, capture:

- `pr` — return address; this is the `.ind`/volume wrapper,
- `r4` — the object/descriptor pointer,
- dump `[r4]`, `[r4+4]`, `[r4+8]` and the caller frame,
- the arguments (base/offset/size) and the eventual read length.

The first caller should be the `.ind` reader wrapper; from there the map
reader is one frame up.

## Secondary — fd methods

Break on the fd/IOB methods:

```
0xc42520   IOB/fd dump (type tag +0xC0)
0xc426a4   directory/disc dump (type tag +0xB4)
0xc438a4   stats formatter
```

At each break:

- `pr` = caller,
- `r4` = object,
- dump `[r4]` (vtable pointer) and slots `+0x00…+0xd0` (component methods are
  likely in `+0x70…+0xc0`, as in the reconstructed iPodCC object).

The slot that calls the MAL chain is the reader candidate.

## Tertiary — fd thunks / IAT

Break on the fd thunk targets / IAT slots to classify the real API even without
names:

```
0x2e07344 / 0x01ab9240
0x2e073c8 / 0x01ab902c
0x2e07350 / 0x01ab902c
0x2e076a4
```

Record the caller and the object argument for each.

## Offline — `.ind` mutation matrix

If no debugger is available, run `tools/ind_mutate.py` variants on a spare
card:

| Variant | Question |
| --- | --- |
| `size_8000` | is `chunk_size` compared to `0x10000` or used as a buffer size? |
| `size_20000` | same, larger value |
| `off_last_m1` | exact seek or `78 9c` scan? |
| `off_last_p1` | same, opposite direction |
| `count_p1` / `count_m1` | is the chunk count trusted or derived? |
| `off0_1` / `off_last_0` | is offset 0 special / validated? |

Each variant is paired with the original `.cmp`; the unit's accept/reject
behaviour is the oracle.

## Safety

- Original card read-only and hashed.
- Work on a spare card only.
- Keep an untouched rollback card.
- Stop at the first map-data/`SECURE`/black-map/reboot symptom.

## Bench kit and access plan (M6.8)

> Planning record, 2026-11-06; no hardware is available yet. Every price is an
> **ESTIMATE** (2026 EU retail range, one-off, excluding shipping, the head
> unit and the card it came with). Nothing here was tried on a unit. The claim
> text lives in
> [`EXP-2026-11-06-M6.8-bench-kit`](../experiments/EXP-2026-11-06-M6.8-bench-kit.md)
> (C-1130–C-1139; planning claims, not ledger rows yet).

Each part buys one of three things: readable errors (UART, camera), a card
loop that does not require dismantling the unit (extension, writer, relay), or
control over the two risky inputs (`SECURE`, CAN).

### Parts

| # | Part | Qty | ESTIMATE (EUR) | Purpose | Unblocks |
| --- | --- | --- | --- | --- | --- |
| 1 | 12 V bench supply, current-limited, 0–20 V / 5 A | 1 | 80–140 | power the unit; the current limit is the first fuse | C-1130 |
| 2 | 4 mm² leads, banana-to-spade, 2 A blade fuse + holder, multimeter | 1 set | 20–40 | polarity check, in-line fuse, safe connection | C-1130 |
| 3 | SPST switch + 2 m lead for `TEST_B1` to ground (1 kΩ in series optional) | 1 | 5–15 | bypass `SECURE` in a removable way | C-1131 |
| 4 | CAN interface: USB CAN adapter (CANable 2.0 class), **or** SBC + MCP2515/TJA1050 HAT | 1 | 35–130 / 30–60 | replay ignition, speed, VIN frames | C-1132 |
| 5 | CAN socket shell (OBD-II or the unit's 4-pin shell) + 2 × 120 Ω termination | 1 set | 5–15 | mate with the harness, terminate the bus | C-1132 |
| 6 | SD extension cable, male→female ribbon, ≤ 30 cm | 1 | 10–20 | reach the card without opening the unit | C-1133 |
| 7 | USB SD reader/writer | 1 | 8–15 | write card clones and deltas from the host | C-1133 |
| 8 | USB-UART, 3.3 V VIO (CP2102/FT232RL with jumper) | 1 | 8–20 | read the kernel debug SCIF, **if** the pins are found | C-1134 |
| 9 | Logic analyser, 8 ch, ≥ 24 MHz (Saleae clone / DSLogic class) | 1 | 15–40 | find the debug TX, watch SD CMD/DAT, check CAN framing | C-1135 |
| 10 | Oscilloscope, 2 ch, 100 MHz (alternative/addition to #9) | 0–1 | 300–450 | signal integrity, differential CAN, SD clock | C-1135 |
| 11 | Spare SD cards, 8–32 GB, class 10 (work, control, rollback) | 3 | 10–15 each | keep the original card off the bench | C-1136 |
| 12 | Relay / USB-controlled 12 V switch | 1 | 15–35 | scripted power cycles | C-1137 |
| 13 | Camera on a clamp, or USB video capture + old camera | 1 | 0–60 | capture error screens and map state | C-1137 |
| 14 | GPS replay/simulator (optional, later) | 0–1 | 40–150 | fixed position for routing tests | C-1137 |
| 15 | Host laptop | 1 | 0 (existing) | runs the card writer, CAN tool, capture | — |

**Kit total:** ≈ €220–550 with the analyser and no scope; ≈ €520–1000 if a
2-channel scope is added. Add the optional GPS replay only when routing tests
arrive (M6.7). All prices **ESTIMATE**; re-check before buying.

### Wiring and safety notes

- **Ground first, +12 V last.** Meter the polarity and the 12 V level before
  the unit sees it; put a 2 A fuse in the +12 V lead even with a current-limited
  supply. First boot at a **2 A limit**; raise it to 5 A only if a legitimate
  load (drive, display) needs it.
- **Never the original card.** Hash it, store it, and put only clones in the
  bench unit. A clone that fails `SD UNLOCK NG` is a lock/clone problem, not a
  map problem (C-790, C-798).
- **`TEST_B1` through a switch, not a solder strap.** Label it, and be ready to
  open it if the unit boot-loops, loses audio or shows a black screen; whether
  grounding alone bypasses `SECURE` or a VIN/CAN frame is also needed is
  **UNKNOWN** (C-082 is external research).
- **CAN needs termination.** 120 Ω at both ends of the stub, twisted pair, and
  a common ground with the unit. Do not probe CAN single-ended with a scope
  without a differential probe or a transceiver.
- **SD: power off before insert/remove.** No hot-plug on a ribbon extension;
  keep it ≤ 30 cm, and treat intermittent `SD UNLOCK NG` as a cable/contact
  fault before touching the card contents.
- **UART is 3.3 V only.** GND first, VIO jumper on 3.3 V, never a 5 V TX.
  Measure the idle level with the analyser before connecting the adapter's RX;
  a 5 V pull-up on the unit side would otherwise be a silent risk.
- **First power-up with no card, camera rolling, 2 A limit.** Record which
  screen appears before the map UI; that baseline is what later card variants
  are compared against.

### Access plan (in the order the dynamic guide needs it)

| Step | Access | What it gives | Claim |
| --- | --- | --- | --- |
| 1 | **UART / debug output** — kernel debug SCIF `0xffe46000` (writer `0x8804cfa4`, pointer `0x8804ce78`); pins **unconfirmed** | boot banner, `OSM_Printf`/`StatusData` text instead of screen OCR, and the answer to "is retail debug output enabled?" | C-1134, C-1135 |
| 2 | **Break on `MAL_DataVol_getOffset`** `0x03498d48` (file `0x7f5f48`) | `pr` = `.ind`/volume wrapper, `r4` = descriptor, arguments and the eventual read length | C-1138 |
| 3 | **fd methods** `0xc42520` / `0xc426a4` / `0xc438a4` | which object slot calls the MAL chain → the reader candidate; runtime vtable slots `+0x70…+0xc0` | C-1138 |
| 4 | **Card matrix** — extension + writer + relay + camera, `tools/ind_mutate.py` variants | accept/reject oracle for `chunk_size`, exact seek vs `78 9c` scan, count trust, offset-0 special case | C-1133, C-1137 |

**Reality check.** Steps 2–3 need a debug path that does not exist today: no
BDM/JTAG header is documented, and the static route is closed. The two
candidates are a QEMU `ze0` gdbstub breakpoint at the VA (M8.A4/A5, no
hardware) or a physical debug header found by probing. Find the UART TX pin
first (step 1) because it is the cheapest source of error text for every later
step; if the pins are not found in two sessions, stop probing and start
step 4, which is the only step runnable with today's knowledge.

## Clarion debug console (MONI / `FW>`) — UNVERIFIED

> Planning record, 2026-11-06; no hardware. Nothing in this section has run on
> a unit. It is the fallback when neither a debugger (primary/secondary above)
> nor a QEMU gdbstub exists: use the unit's own firmware monitor for memory
> reads instead of a breakpoint. It supplements the M6.8 kit above and is
> independent of the kernel debug SCIF (M8.A6). Claim text and the full
> evidence split live in
> [`EXP-2026-11-06-M6.12-debug-console`](../experiments/EXP-2026-11-06-M6.12-debug-console.md)
> (C-2010–C-2019 reserved; only C-2010 is written, and it is **not** a
> `claims.md` row).
>
> **Status: UNVERIFIED.** Every step below is a plan, not a procedure. The
> procedure becomes real only when a bench session captures the prompt and one
> memory read whose bytes match a known image string.

### What is reported, and by whom

The input is a single secondary write-up (zelemar.eu, "SD Card Toolbox – Nissan
Leaf navigation interface"), summarised in `TODO.md` M6.12. It reports a
**service connector** carrying `Rx`, `Tx` and a **Mode select** line, reachable
without disassembling the unit, and a monitor whose prompt depends on the
selected mode:

| Reported mode | Reported prompt | Reading |
| --- | --- | --- |
| `FACT` | `>>` | factory/user mode; the application runs |
| `NORM(EVA)` | `>>` | normal/evaluation; whether it is distinct from `FACT` is UNKNOWN |
| `MONI` | `FW>` | the firmware monitor this section wants |
| `PROD` | `clarion>` | production/test mode; **off-limits** on a unit we cannot restore |

`MONI` is reported to correspond to `DSW=0006`. The command set is reported as
`?`/`h`, `r`, `g`, `mb`/`mh`/`mw`, `e`, `s`, `w`/`wr`, `m1`/`m2`, `cb`/`ch`/`cw`
and `mv`. All of that is **hearsay**: comment-level reports, not reproduced, not
tied to any firmware address, and not evidence that this unit's retail firmware
contains the monitor at all.

### Entry paths: what the evidence supports

| Route | Reported? | Static support | Verdict |
| --- | --- | --- | --- |
| **Serial service connector + Mode select** (the zelemar path) | yes | none for this port; the kernel debug SCIF is a different interface (C-534, C-532) | primary candidate; UNTESTED |
| **Key sequence on the unit** | not in the inputs; a common assumption for service menus | C-818 reports no key-combination string in the scanned test-mode modules, and C-708 puts `TestMode.exe` behind a boot-mode flag | unsupported; do not spend the first session on it |
| **Service menu / `TestMode.exe`** | implied by "service menu" in some write-ups | `TestMode.exe` is recorded only in image C of the reference sample (C-526, C-810–C-812), gated by the IPL/boot-mode flag (C-708, C-818); image B carries the updater set instead | unsupported on a retail A+B unit; needs the image-C test build and an IPL flag |

The key negative is C-818: a string scan found no key-combination literal, so
there is no static address to hook a button path to. Its recorded evidence is a
string scan, not a proof over every module; it does not prove no key sequence
exists. It does mean a key sequence is the **weakest** of the three candidates
and must not be the first bench attempt.

### `DSW=0006`: two readings, both untested

Nothing in the repo says what `DSW` is. The report fits two models equally well:

- **M-A, hardware:** `DSW` is a switch/strap bank or a mode register read by the
  IPL or monitor; `0006` is the MONI encoding and the **Mode select** line
  presents it. In this reading no command sets it — the mode line does.
- **M-B, software:** `DSW` is a monitor variable, displayed by the monitor and
  changed with `s` (or `e`); `0006` selects the MONI personality and the prompt
  changes to `FW>`.

Resolve it without writing anything: for **each** Mode-select position,
power-cycle and record the prompt and any `DSW` readout shown by `?`/`h`. Only
if no position yields `FW>` *and* help documents a `DSW` **display** may the
value be read. Do **not** write `DSW`: a wrong value may persist in NAND/PROD,
and there is no unit backup (M6.10 is blocked).

### Connector, levels, terminal

| Item | Reported / known | Status | How to establish it |
| --- | --- | --- | --- |
| Connector | TE Connectivity **1674312-1** is named | hearsay; pin count and assignment are **not** in the repo | obtain the mating shell/pigtail, buzz out a scrap harness with a meter |
| Signals | `Rx`, `Tx`, `Mode select`; ground implied | hearsay; assignment **UNKNOWN** | continuity + scope on each candidate line at power-up |
| Logic level | not stated | **UNKNOWN** | measure idle high level before connecting an adapter; assume 3.3 V CMOS, never 5 V; 1 kΩ series in the adapter's RX |
| Baud / framing | not stated | **UNKNOWN** | capture a power-up byte stream with the analyser; shortest pulse = 1 bit; try 8N1 at `1/t_bit`; 9600/19200/38400/57600/115200 are a search order, not a claim |
| Mode select | selects `FACT`/`NORM`/`MONI`/`PROD` | **UNKNOWN** electrical form (switch, strap, level) | measure both states; never tie a line to a rail before its function is known |
| Flow control | not stated | **UNKNOWN** | start with none |
| Address space | not stated | **UNKNOWN** | resolved only by the positive control below |

No claim backs any row of this table. The only adjacent claims are C-1134 and
C-1135 for the 3.3 V UART/analyser tooling and C-1130 for the power source;
everything specific to this connector is UNKNOWN.

The M6.8 UART rules apply unchanged: ground first, VIO at 3.3 V, RX-only at
first, and an analyser on the line before any adapter (C-1134, C-1135). Note
that this port is **not** the kernel debug SCIF `0xffe46000` (C-534): the SCIF
is a register-level console with unknown pins, while this is a reported service
connector. Whether the two are physically the same pads is **UNKNOWN**; do not
assume it.

### Safe command subset vs bench-only commands

| Command | Reported meaning | Class | Rule |
| --- | --- | --- | --- |
| `?`, `h` | help | read-only | **use first**, every session |
| `r` | register dump | read-only | safe; map `PC`/`PR` through `cerom.py` (module, section, offset) |
| `mb`, `mh`, `mw` | read byte/half/word | read-only | safe **only** in XIP/ROM/RAM ranges |
| `m1`, `m2` | not stated | unknown | do not use; semantics may be a memory mode or a move |
| `cb`, `ch`, `cw` | not stated (compare? change?) | unknown | do not use until help defines them |
| `mv` | move/copy (inferred; not defined in the report) | **bench-only / risky** | writes |
| `e` | edit memory | **bench-only / risky** | writes |
| `s` | set register/option | **bench-only / risky** | may change `DSW`/boot state |
| `w`, `wr` | write | **bench-only / risky** | may write flash/NAND |
| `g` | go / execute | **bench-only / risky** | arbitrary code execution |

Two cautions that survive the "read-only" label:

- Reads of **memory-mapped I/O** (`0xffe…`, `0xffc…`) can pop FIFOs or clear
  status flags. Restrict the first reads to XIP/ROM/RAM, never peripherals.
- The monitor itself may be the flash programmer. A command that looks like a
  read (or entering `PROD`) can expose erase/write paths; stop if the help text
  mentions erase, write, format or download.

**Hard rule:** no write/execute command until M6.10 (unit NAND/PROD backup)
exists and a restore has been proven. Today it is blocked, so a monitor write is
a one-way action on the only unit. Report a negative instead.

### What to capture

| Artifact | Detail |
| --- | --- |
| Raw serial log | bytes from **before** power-on to the prompt, timestamped; one file per run |
| Help text | `?`/`h` output verbatim, including the prompt and the exact line endings |
| Prompt transcript | every prompt byte (`>>`, `FW>`, `clarion>`) and the mode-select position that produced it |
| Register dump | `r` output, with `PC`/`PR` resolved through `cerom.py` |
| Positive-control read | 32 bytes at a known anchor, both candidate address spaces (below) |
| Screen | camera or USB capture of the unit from power-on to prompt |
| Power-cycle log | time, mode position, current limit/draw, prompt, exceptions (template below) |
| Unit identity | model/QY number, Clarion part number, firmware/version screen, second SD slot yes/no |

**Positive control.** Read 32 bytes at the kernel XIP string and compare with
the image. C-705 places the ASCII format string
`Navi Version : %c%c%c%c%c%c%c%c-%c%c%c` at VA `0x8800e5a8`; the kernel XIP
window is physical `0x08000000` = VA `0x88000000` (C-535;
`full-system-emulation.md` §1), so the physical
candidate is `0x0800e5a8`. Expected prefix hex:
`4e 61 76 69 20 56 65 72 73 69 6f 6e`. A second control is the UTF-16LE
`DIFFERENT MAP CODE` at file `0x4136abc` / module VA `0x03bb18bc` in build B
(C-760), but its mapping depends on the module load, so use it only after the
kernel string resolves the address space.

If neither address yields the expected bytes, record what came back and stop:
that is a **negative on the address model**, not proof the monitor is broken.
Whichever candidate matches tells us whether reads are physical or virtual —
the single most useful fact this session can produce.

### Static vs hearsay vs untested

**Proven by static analysis / reproducible offline (not about the monitor):**

- The kernel debug console is a different interface: SCIF `0xffe46000`,
  `SCFTDR +0x0c`, `SCFSR +0x10`, `TDFE 0x20` (C-534; channel map C-532).
- The SD card has no bootloader; the on-board IPL selects image B or C
  (C-535, C-706). A monitor could therefore live in the IPL/flash we do not
  have — absence from the CE modules is **not** a refutation.
- `TestMode.exe` exists only in image C of the reference image and is gated by
  the boot-mode flag; no key-combination string was found (C-526, C-708,
  C-810–C-812, C-818).
- Error screens (`SD UNLOCK NG`, `DIFFERENT MAP CODE`, `NAVI VERSION NG`) are
  shown before the map UI and are the visible state to compare a monitor run
  against (C-790, C-803).
- **Repo negative (2026-11-06):** `FW>`, `MONI`, `DSW` and `1674312` occur
  nowhere outside `TODO.md` and the M6.12 experiment; no connector pinout
  exists in the repo (C-1134 for the SCIF, same absence here). Positive
  control for the method: the same grep does find `DIFFERENT MAP CODE`,
  `HDD_INFO` and other known strings, so the tool works and the negative is
  about these tokens only.

**External hearsay only (not reproduced here):**

- The entire entry route: service connector, `Rx`/`Tx`/Mode select, TE
  **1674312-1**, "no disassembly needed".
- `MONI` = `DSW=0006` → `FW>`, and the mode/prompt mapping
  (`FACT`/`NORM`→`>>`, `PROD`→`clarion>`).
- The command list and its semantics (`m1`/`m2`, `cb`/`ch`/`cw`, `mv` are not
  even described).
- Unit variance from the same comments: QY5017HC with SST38VF6401 (WinCE+XIP)
  vs QY8602/QY8350 with MICRON PC28F512 and no second SD. Confirm the model
  before assuming any layout.

**Untested (no unit has run this):**

- Whether retail firmware exposes the monitor at all, and on which QY models.
- Pin assignment, logic levels, baud/framing, flow control, mode-select
  electrical form.
- Whether `DSW=0006` is hardware or software (M-A vs M-B), and whether it
  survives a power cycle.
- Whether entry is non-destructive, and whether any read works in a known
  address space.
- Whether the monitor sees the map card, the CE filesystem or only raw flash.

### Bench checklist (M6.8 items)

Before the first run:

- [ ] Record model/QY number, Clarion part number, firmware screen and whether
  a second SD slot exists (variance above).
- [ ] Original card hashed and stored; only clones on the bench (M6.8 #11,
  C-1136).
- [ ] 12 V current-limited supply at **2 A**, ground first, 2 A fuse in the
  +12 V lead (M6.8 #1/#2, C-1130).
- [ ] Camera or USB capture framing the screen, clock visible (M6.8 #13,
  C-1137).
- [ ] Logic analyser on the three candidate lines **before** any adapter is
  connected (M6.8 #9, C-1135).
- [ ] USB-UART with VIO 3.3 V, RX only at first, common ground (M6.8 #8,
  C-1134).
- [ ] Relay/switch for scripted power cycles and a timestamped log (M6.8 #12,
  C-1137).
- [ ] Baseline run with nothing attached: screens, current, idle levels on the
  three lines.

Every power cycle:

- [ ] Serial capture open **before** power is applied.
- [ ] Power-cycle row filled in before the next cycle (table below).
- [ ] Camera rolling for the first 60 s.
- [ ] If a prompt appears, send only `?`/`h`; save the output verbatim.
- [ ] At most one read command per cycle, with address, length and returned
  bytes logged.
- [ ] Stop and power off on: erase/write prompt, `clarion>` prompt, reboot
  loop, current above the limit, black screen, or `SD UNLOCK NG` without a
  card change.

| # | Time | Mode sel. | DSW (if shown) | Prompt | Current | Screen | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | | |
| 2 | | | | | | | |

The first session's success criterion is deliberately small: **one prompt and
one read-back that matches a known image string.** A prompt with no verified
read is a partial result; a read that matches without a captured prompt is not
attributable to the monitor. Neither promotes the procedure past UNVERIFIED.
