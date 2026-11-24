# One QEMU machine type per Leaf generation (`ze0`, `aze0`, `ze1`)

Status: **design only, no QEMU code.** This is the plan requested by TODO
M8.G2. All facts below are either read from a command printed on an image we
hold or marked `unknown`; no vendor bytes are quoted. The primary target stays
`-M ze0` (ZE0 2011/2012). AZE0 and ZE1 are long-term. The QEMU pin is
**11.1.3 with an out-of-tree patch series** (M8.A11, C-6890); nothing here
proposes a fork or a different base version.

Inputs: [`generations.md`](../hardware/generations.md) (M8.G1,
C-6940–C-6949), [`full-system-emulation.md`](full-system-emulation.md) §1/§6a,
[`qemu-ze0-port-delta.md`](qemu-ze0-port-delta.md), the patch series
[`tools/qemu-ze0/patches/`](../../tools/qemu-ze0/patches/), and EXPs
M8.A3/A9/A11/C1b–C1e/C1f. M8.G1 is done, so the Stop clause "if ZE1 is not
SH-4/CE" applies only to the missing image: there is no ZE1 image, so ZE1
is a separate emulator decision for Marek (§5), not a planned machine here.

## 1. Evidence for the split (commands and numbers)

All four images we hold are CE 5.0 / SH-4 with the same BSP string
`R0P7772A00020S` and platform `CETUS_SH4` (C-6940, C-6941). But AZE0 is not
the same board with only extra modules:

| Measured on build B (`cerom.py --image-start 0x3e00200 IMG romhdr`) | EU2011 (`archive/head256.img`) | EU2014 (`archive/eu2014-256.img`) | EU2016 (`archive/eu2016-256.img`) |
| --- | --- | --- | --- |
| image SHA-256 (first 12, `sha256sum`) | `92aa525d0db2` | `30da3dce5c63` | `208b4fdbe5b4` |
| `physfirst` / `physlast` | `0x88000000` / `0x886e18a4` | `0x88000000` / `0x8870fb90` | `0x88000000` / `0x88714c44` |
| CE image length (`physlast-physfirst`) | 7,215,268 B | 7,404,432 B | 7,516,228 B |
| `ulRAMStart` / `ulRAMEnd` | `0x89e40000` / `0x8e600000` | `0x8a640000` / `0x8e600000` | `0x8a640000` / `0x8e600000` |
| `usCPUType` | `0x000001a6` | `0x000001a6` | `0x000001a6` |

So AZE0 moves the CE RAM window start by **+8 MiB** (`0x89e40000` →
`0x8a640000`) under the same ceiling and the same CPU type (C-6942).

**Falsifier test (M8.G2's own, run 2026-11-24).** An F0 try of the EU2014
kernel on the *unmodified* `-M ze0` uses the built-in loader at the EU2011
offset (`kernel-off=0x3e00200`, `app-off=0`) and the 11.1.3 binary built from
the current 30-patch series:

```bash
Q=~/.cache/qemu-ze0/build/qemu-system-sh4          # QEMU emulator version 11.1.3
bash tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img \
     --timeout 5 --workdir "$S/f0-2011" --qemu "$Q"
bash tools/qemu-ze0/run.sh --machine ze0 --image archive/eu2014-256.img \
     --app 0 --timeout 5 --workdir "$S/f0-2014" --qemu "$Q"
```

The two runs print **different** boot logs, so the falsifier ("same boot log
as EU2011 → no new machine needed") is **not met**:

| Observable (printed by `run.sh`) | EU2011 | EU2014 |
| --- | --- | --- |
| kernel image mapped by the built-in loader | `0x88000000..0x886e18a4` (7,215,268 B) | `0x88000000..0x8870fb90` (7,404,432 B) |
| `nk.exe` entry from the image TOC | `0x8800ebd0` | `0x8800f100` |
| debug text lines on the default `dbgmsg=0x880404f4` sink (counted before the `unmodelled` block) | 423 | 0 |
| unmodelled register accesses, first-seen | 35 | 30 |
| exceptions | 46,926 | 48,628 |
| final PC | `0x8803d266` | `0x8803d796` |

Both reach an idle kernel, but the EU2014 kernel prints nothing at the
EU2011 debug-string VA, its entry point differs by `0x530`, and its exception
sequence ends at a different PC. A new machine (or at least a parameterised
one with an X212 layout) is therefore justified. The EU2014 kernel boots
*far enough* on today's devices that F0 is a realistic first target: the first
five model differences that matter are RAM layout, kernel offset/entry,
debug-string VA, INTEVT/SYSINTR assignments and the flash/graphics driver
set.

## 2. Device × generation table

Legend: **shared** = reuse the existing model unchanged; **parameter** = one
model with per-machine properties (base address, size, INTEVT, window);
**new** = needs a new QEMU device model; **stub** = read-back/no-side-effect
answer is enough for the stated stage. "Patch" names the file in
`tools/qemu-ze0/patches/` that implements the ZE0 model today. The three
columns are the action for `-M ze0`, `-M aze0` and the (deferred) `-M ze1`.

| Device / block (ZE0 address or evidence) | ZE0 (`X210`, today) | AZE0 (`X212`) | ZE1 / Leaf 2 |
| --- | --- | --- | --- |
| SH-4A CPU (`sh7785`, `usCPUType 0x01a6`, BSP `R0P7772A00020S`) | shared — `ze0-0001` | shared — same CPU type in all images (C-6940) | unknown — no image |
| RAM + P1/P2 aliases (`0x08000000`, 128 MiB) | shared — `ze0-0001` | **parameter**: CE window start `+8 MiB` (`0x8a640000`); keep 102 MiB DRAM ceiling, pad with RAM to `0x8e600000` | unknown |
| CCN/MMU (`0xff000000`, arrays `0xf0000000`) | shared — `m8a4-0001..0003` | shared — same core registers, no generation-specific behaviour observed | unknown |
| Boot-blocker stubs (`0xffe70800..1c`, CPG `0xffc80000`, UBC, area 6) | shared — `0002-...-boot-stubs` | shared first; parameter (`0xffe70808` ready value, area-6 base) if the X212 OAL differs — unverified | unknown |
| INTC / INT2 (`0xff802000`/`0xff804000`) | shared — `ze0-0003` | **parameter**: INTEVT/SYSINTR table from the X212 `nk.exe` OAL; X212 debug text is unreadable here, so the table is `unknown` until an F0 run shows the vectors (`C-6944`) | unknown |
| TMU + clock (`0xffd80000`, `0x1fd80000`) | shared — `ze0-0003`, `ze0-0005` | shared; frequency `unknown` (not printed by any command here) | unknown |
| Built-in CE loader (`kernel-off=`, `app-off=`) | shared — `ze0-0004` | **parameter**: kernel file offset `0x3e00200` (same in both), app offset `0x200200` (X212 app image present, not booted here), entry derived from the image TOC (`0x8800f100` EU2014) | unknown |
| Debug-string hook (`dbgmsg`) | shared — `ze0-0007` | **parameter**: X212 sink VA differs (EU2011 `0x880404f4` yields 0 lines on EU2014); new VA must be found from the X212 `nk.exe` | unknown |
| Debug serial SCIF (`0xffe46000`) + SCIF 0–9 stubs / chardevs | shared — `ze0-0002`, `ze0-0008`, `ze0-h01`, `ze0-h02` | shared; `UAT3:` port string absent from X212 `CAN.dll` (C-6946) so the CAN peer's host line is **parameter** | unknown |
| HPB-DMAC (`0xffc08000`, SD/audio channels) | shared — `ze0-0009` | shared as a block; per-channel SD/SSI assignment (channels 8/9, 11–13 on ZE0) **parameter**, not yet printed for X212 | unknown |
| SD host (`0xffe4c000`/`0xffe4d000`, SDHI) | shared — `ze0-0008`, `ze0-0009` (M2.22 L4 PASS on EU2011) | shared first — X212 card layout is the same FAT/CE image family (`generations.md`); card-detect bits must be confirmed by an F3 run | unknown |
| Unit record / map-code (`ze0-0010`, `0x0101302C`) | shared | **parameter**: header +0x60 map code `X212…` (C-6941), `FlashManager2.dll` product record — new record layout plausible but unproven | unknown |
| IPL patch / image-A join (`ze0-0012`) | shared | shared mechanism; image A offsets **parameter** (`X212` apps at `0x200200`, header string differs) | unknown |
| NOR flash (`flash=`, CFI-02, `FMD1:`) | shared — `ze0-0017`, `ze0-h18` | **new**: X212 uses `fmmdrv_05.dll`/`fmmdrv_07.dll` and `FlashManager2.dll` (C-6943); chip geometry unknown (registry hive fails `nk_decomp.py`), so a new flash model is gated on identifying the chip | unknown |
| Graphics DU + 2DG (`0xfff80000`, `0xffe80000`) | shared — `ze0-0013..0016`, `ze0-hc1u`, `ze0-h04` | **new**: X212 adds DirectDraw (`ddraw.dll`, `ddcore.dll`, `ddhel.dll`, C-6944) and drops Bolero; resolution unknown. A DU-only variant may suffice for F0–F4; full X212 graphics needs a new model | unknown |
| External UARTs `UAT3:`/`UAT4:` | shared — `ze0-h03` | **new / parameter**: ZE0 `CAN.dll` opens `UAT3:`; X212 `CAN.dll` has no surviving `UAT*` string, so the vehicle micon link is unknown (C-6946) | unknown |
| SSI audio (`0xffe00000`, WaveSSI1/2) | shared — `ze0-h46` | shared as hardware; `Audio.exe` is larger on X212 (C-6944 row Audio) and codec hardware unknown | unknown |
| Sensors (speed/gyro, `ze0-h32`) | shared | shared first; X212 sensors unknown | unknown |
| USB OHCI (`0xffe70400`) | stub today (`0002-...`) | shared — still OHCI, no EHCI in any image (C-6945); `UsbConMngCC.dll`/mass storage are software, not a new host controller | unknown |
| Telematics / CAN / camera / Wi-Fi | stub / absent | parameter or new only if an F2–F4 run blocks on them; no X212 hardware evidence for a different controller (C-6945–C-6947) | unknown |

Counts from the printing commands used for this table: `ls
tools/qemu-ze0/patches/*.patch | wc -l` prints **30**; the device-type scan
`grep -hE 'TYPE_ZE0|create_unimplemented|TYPE_SH4_CCN' ze0-*.patch m8a4-*.patch
…` finds 8 distinct modelled QOM device types (`ze0`, `sh4-ccn`, `ze0-intc`,
`ze0-sdhi`, `ze0-hpbdmac`, `ze0-gfx`, `ze0-ssi`, `ze0-dr`) plus the catch-all
regions (`ze0-p4`, `ze0-area4`, `ze0-area6`). All are created by the machine
today; none is a separate machine class.

## 3. Machine-class layout decision

Today `ze0` is registered with `DEFINE_MACHINE("ze0", ze0_machine_init)` and a
flat `Ze0MachineState` holding properties (`kernel-off`, `app-off`, `dbgmsg`,
`gfx`, `sdhi`, `sciN`, …), converted later to a QOM class
(`TYPE_ZE0_MACHINE`, see the class-init hunk in `ze0-0004`). The plan:

- **One base class, one file.** Keep `TYPE_ZE0_MACHINE` in `hw/sh4/ze0.c` as
  the base, with a `Ze0MachineClass` holding generation parameters:
  `ram_start`, `ram_size`, `kernel_off`, `app_off`, `entry` (or the TOC rule),
  `dbgmsg_va`, `intevt_table`, `flash_model`, `gfx_model`. Defaults are the
  measured ZE0 values so `-M ze0` is byte-for-byte unchanged in behaviour.
- **Subclasses, not separate files.** `TYPE_AZE0_MACHINE` and a later
  `TYPE_ZE1_MACHINE` derive from the base via `DEFINE_MACHINE` with a small
  `class_init` that overrides those fields; they live in `ze0.c` next to the
  base, sharing the device instantiation and property wiring. Device files
  (`ze0_sdhi.c`, `ze0_hpbdmac.c`, `ze0_gfx.c`, …) are reused unchanged unless
  the table says **new**.
- **No version migration.** All of this is added to the same 11.1.3 patch
  series; a new patch is written, built and booted with the documented
  `build.sh` flow (M8.A11), never as a fork or a bump. The 8.2 series stays
  removed (C-6890).
- **Property names stay stable.** Existing `run.sh` flags map to the same
  property names on every subclass; a generation-specific override is a
  class default, not a different property. This keeps a single boot recipe
  for all three machines.

Rejected alternative: three independent `hw/sh4/ze0.c`/`aze0.c`/`ze1.c`
machines with copied device instantiation. It would duplicate ~30 patches'
worth of wiring and make the "shared devices" in §2 diverge.

## 4. What X212 needs first to reach F0 on `-M aze0`

F0 is "kernel debug log on stdout" (full-system-emulation.md §4). On EU2014
today the unmodified `-M ze0` already reaches an idle kernel (final PC
`0x8803d796`), but prints 0 debug lines because the sink VA is wrong and its
RAM window is 8 MiB off. In order, the first `-M aze0` work items are:

1. **RAM/map parameters** — `ulRAMStart 0x8a640000`, ceiling `0x8e600000`,
   entry `0x8800f100` from the image TOC (measured above).
2. **Debug string sink** — find the EU2014/X212 `dbgmsg` VA (the EU2011
   `0x880404f4` prints 0 lines); set it as the subclass default so F0 has a
   log. This is the first thing that makes F0 observable.
3. **INTEVT/SYSINTR table** — read from the X212 `nk.exe` OAL and parameterise
   the `ze0-intc` sources; needed before any interrupt-dependent stage.
4. **Flash model** — `FlashManager2.dll` + `fmmdrv_05/_07` (C-6943) and an
   unknown chip geometry; needed for F2, not for F0.
5. **Graphics model** — DirectDraw on X212 (C-6944); needed for F4/F5, not
   for F0.

## 5. ZE1 decision (deferred to Marek)

No ZE1 / Leaf 2 image is held (C-6948); the named 2019 e-NV200 image is a
different engine family and 404s from the image server. No architecture can
be asserted from bytes we hold. Therefore **no `-M ze1` implementation is
planned here**. The base-class design in §3 leaves a `TYPE_ZE1_MACHINE` slot,
but starting it requires a first decision by Marek: acquire a 2018+ Leaf 2
card head (~256 MiB), then determine whether it is still CE/SH-4 at all. If
it is not, ZE1 belongs to a different emulator choice (not this patch series).

## 6. Ordered follow-up tasks

One task per new device model / parameterisation, each added to `TODO.md` with
`board.py add-task`. IDs are in the M8.G series following G1/G2/G3. The first
is the mandatory follow-up from this task's Done when.

1. **M8.G4 — `-M aze0` F0: boot the EU2014 kernel with X212 RAM/entry/dbgmsg
   parameters** (new machine subclass, no new device). Done when: a 5 s
   `tools/qemu-ze0/run.sh --machine aze0 --image archive/eu2014-256.img`
   boot prints a non-zero count of X212 debug lines on its own `dbgmsg` sink,
   reaches an idle kernel with no CPU exception, and an EXP compares the
   EU2014 log with the EU2011 F0 log (entry `0x8800f100`, RAM
   `0x8a640000`). Falsifier: X212 prints debug text at the EU2011 VA and
   gives the same final PC as EU2011 (then no subclass is needed).
2. **M8.G5 — X212 INTEVT/SYSINTR table and parameterised `ze0-intc`**. Done
   when: the X212 OAL interrupt table is printed from `nk.exe` with addresses
   and INTEVT/SYSINTR values, the `aze0` machine uses it as a class default,
   and a 5 s boot shows a TMU tick on the expected vector with no spurious
   interrupt; the ZE0 vector table and boot log are unchanged.
3. **M8.G6 — X212 NOR flash model (`FlashManager2` / `fmmdrv_05` / `_07`)**.
   Done when: the chip geometry is printed from a command (or marked unknown
   with a named unblock), `FlashManager2` init returns success in an
   emulated boot, and the guest's NOR reads reach the new model with no
   unmodelled-access line at its window; ZE0 flash behaviour is unchanged.
4. **M8.G7 — X212 DirectDraw / graphics model**. Done when: X212's display
   resolution and DU/2DG register blocks are printed from the image (or a
   named unblock if not), the `aze0` machine selects the new `gfx` model, and
   a 2DG display-list submission writes non-zero VRAM pixels in an EXP;
   ZE0 screenshots stay byte-identical.
5. **M8.G8 — X212 vehicle-link (CAN / external UART) model**. Done when: a
   command prints the X212 `CAN.dll` port (the ZE0 `UAT3:` string is absent),
   the `aze0` machine binds the correct host chardev or stub, and a boot
   shows the CAN driver's init succeeding without a missing-port error; ZE0
   `UAT3:` loopback is unchanged.
6. **M8.G9 — acquire a ZE1 image and decide the emulator family** (decision
   task, blocked on Marek). Done when: a 2018+ Leaf 2 card head is hashed and
   `cerom.py`/file magic determines CE/SH-4 vs another architecture, and an
   EXP records go/no-go for `-M ze1` in this series or a different emulator.

Tasks 1–5 follow §4's order; task 6 is gated on hardware/image acquisition and
does not block tasks 1–5.

## 7. Falsifier and scope

- Falsifier result: **not met** — EU2014 on unmodified `-M ze0` does not give
  the EU2011 boot log (§1). This justifies the new machine; if a future image
  gives the same log, task M8.G4's own falsifier reverts to "properties only".
- Scope: design document + claim rows + one new follow-up task on the board.
  No QEMU code, no image bytes, no card change, no L5/car test. ZE1 remains a
  decision, not an implemented machine.
- The numbers in §1 were printed by the commands shown there or by
  `sha256sum`, `cerom.py … romhdr` and `run.sh` on the named heads; no value
  was inferred from an image hexdump or copied from a vendor dump.
