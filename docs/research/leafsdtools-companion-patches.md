# LeafSDTools Companion patches: GPS time fix and consent screen

[LeafSDTools Companion](https://github.com/developerfromjokela/leafsdtools_companion)
(GPL-2.0, Go) patches firmware images that LeafSDTools reads from a unit or
a card. Marek asked (2026-11-22) how two of its patches work and whether
they fit his 2011–2012 US unit (QY7200ND, ZE0) and the EU 2011 card. This
page summarises the code at release 1.2.1 / master `cbe3da4` and the dry
runs we made. None of their code or binaries is copied into this
repository. Claims are C-8358 and C-8359, record
EXP-2026-11-22-M8.C1m-unit-flash-region O6.

## GPS time fix ("Fix GPS Time Rollover", `patch/gpstimefix_qy7`)

**Problem.** The GPS receiver reports a date 1024 weeks back: the 10-bit
GPS week rollover. Marek's unit shows `GPS GMT` 2007-04-08 in 2026. The
patch's own description says this breaks the climate and charging timers
on all QY7xxx EV units.

**Where it patches.** NK1, the kernel image in the **unit's flash** (NAND
`0x40000`, LeafSDTools "NAND" dump). The card is not involved. The fix is
then written back to the unit with LeafSDTools.

**How.** There are three changes:

1. In `navdrv.dll`, the function that sets the system time from the GPS
   receiver (signature `SetTimeInformationPatch`) gets two 2-byte changes,
   at `+0x24` and `+0x8e`. It then calls `SetSystemTime` with a pointer to
   the raw GPS buffer instead of a `SYSTEMTIME`.
2. `navdrv.dll`'s import name `COREDLL.dll` becomes `COREXLL.dll`. A
   13 312-byte shim `COREXLL.dll` (credit YDean, 4pda) is added to NK1 as
   a file. Its `SetSystemTime` does the following:
   - reads `YY MM DD hh mm ss` at buffer `+0x10..+0x15`;
   - adds `0x1600A391000000` × 100 ns, which is exactly 1024 weeks
     (6 193 152 000 000 000);
   - writes the date back into the buffer;
   - sets the clock one second later.

   The shim's other exports must forward to coredll, which was not
   checked here.
3. NK1's checksums are recomputed: SUM2 at header `+0x30` and SUM4 at
   `+0x84`. The ROM keeps its size.

**On Marek's unit (dry run, nothing written).** On the committed NK1
(`firmware/unit-flash/nk1-QY7200ND.bin`):

- the original checksums verify;
- the signature is found;
- the patch applies in `navdrv.dll` at VA `0x03cf4988`;
- the ROM size is unchanged.

**What it fixes.**

- Certain: the system clock, and with it the charging and climate timers.
- Not known: whether Navi then accepts the Wrocław position (M1.50/M1.51).
  The shim corrects the buffer in place, but we have not traced whether
  Navi reads the date from that buffer or from the receiver's other
  messages.
- The emulator cannot test it yet. `-M ze0` boots image B's kernel, not
  NK1 (M8.C1r), and has no GPS peer.

**Use.** LeafSDTools Companion → "Fix GPS Time Rollover…" on a NAND dump
made with LeafSDTools, then write the dump back with LeafSDTools. Keep the
original dump (M6.18). This writes the unit's flash; a wrong image can
brick the unit.

## Consent screen ("Remove consent screen", `patch/agree_qy7`)

**Where it patches.** `ScreenStateCC.dll` in **card** ROM image A. The
image is stored twice on the card: NB00 at `0x200000` and NB01 at
`0x2000000`, each with a 512-byte `NKOK` header. The patch checks that both
copies agree, patches A, repacks it with new SUM2/SUM4, and writes it to
both places.

**How.** It reads ScreenStateCC's two state-name tables (main states, and
events/actions), the same table that M8.C1n needs. Then it does four
things:

1. In the class of state `SRT_COLD_I_AGREE_TELEMA_OK_SELECTED`, the
   vtable's event-listener slot (21) is pointed at the handler of
   `SRT_COLD_I_AGREE_TELEMA`.
2. In that handler, the event `SK_SCT_AGREE_CLICK` (the "I agree" button)
   is replaced by `SS_TMR_AGREE_TELEMA_OK_SELECTED`, a timer event. The
   screen accepts on its own when the timer fires, with no tap.
3. That state's timer goes from 5 000 ms to 2 000 ms (both init slots, 16
   and 18).
4. The two start-up transitions to `SRT_COLD_I_AGREE_TELEMA` go to
   `SRT_COLD_I_AGREE_TELEMA_OK_SELECTED` instead.

Its name in the tool says "QY7XXX (AZE0, E-NV200), NOT FOR JAPAN".

**On the EU 2011 card (dry run).**

- NB00 and NB01 are present and identical: `X210ECNI.158`, 24 456 328
  bytes, version `470-2824-34`, SUM2 `0x4682`, SUM4 `0xcdf87db0`.
- The state tables read cleanly: 675 main states and 3 887 events.
- **The patch stops with "cannot find SRT_COLD_I_AGREE_TELEMA".** The
  2011–2012 (ZE0) firmware has `SRT_COLD_I_AGREE` (611) and
  `SRT_COLD_I_AGREE_NAM` (612), not the `…_TELEMA` states of the later
  AZE0 firmware. So the patch does not support our cards as it is. A ZE0
  version would need the same four steps on `SRT_COLD_I_AGREE` (EU) or
  `SRT_COLD_I_AGREE_NAM` (North America), and the timer and transition
  sites found for those states. That is task M8.C1p.

Other ZE0 start states for reference: `INI_STARTUP` (215),
`SRT_COLD_ANTI_THEFT`, `SRT_COLD_OPENING_ANIMATION(_FIRST)`,
`SRT_COLD_SECURE`, `SRT_COLD_WAITING_MAP`, `SRT_COLD_STATUS_SCREEN`.
