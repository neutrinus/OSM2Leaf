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
