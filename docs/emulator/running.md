# Running the unit with its peers (NK1 + card, one command)

[`README.md`](README.md) boots the EU 2011 kernel from the card and gets a
map. This page is the next step: the unit's **own kernel** (NK1 from the
unit flash) with ROM image A from a card, plus the host programs ("peers")
that play the hardware around the head unit on its serial lines. One
command starts all of it: `tools/ze0_launch.py`.

## 1. What you need

| Input | Where | Committed? |
| --- | --- | --- |
| QEMU with the `ze0` series up to `ze0-h02` | `bash tools/qemu-ze0/build.sh` (step 2 of README.md) | patches only |
| NK1 kernel | `firmware/unit-flash/nk1-QY7200ND.bin` (default of `--nk`) | yes (owner decision, M8.C1k) |
| Unit flash dump (8 MiB, `nand.bin`) | your own dump (M6.18) | **never** |
| Card image | `LEAF_2011-2012_US.img` or the EU card | **never** |

The flash dump decides the region (the US unit's flash gives the US map
area, M8.C1m). An 8 MiB dump is emulated as the unit's NOR chip (M8.H18), so
the saved settings and the locator backup load too: the car starts where
the unit last was. Guest writes are discarded unless you pass `--flash-rw`;
use it only on a copy of the dump. Serial logs contain the SD card password: keep the work
directory out of the repository and never commit its files.

## 2. Start

```bash
python3 tools/ze0_launch.py \
  --qemu "$QEMU" \
  --card /path/LEAF_2011-2012_US.img \
  --flash /path/nand.bin \
  --workdir "$W/live" \
  [--peer gps] [--peer micon] [--gdb 1240 --ui-start] [--timeout 1800]
```

It prints the IPL, QEMU and peer command lines, writes the IPL patch
(`ze0_ipl.py patch CARD --nk NK1`), starts QEMU and then the peers, and stops
everything on `^C` or after `--timeout` seconds. `--dry-run` only prints.
The card is opened with `snapshot=on`, so it is never written.

A boot to the map takes about 3–4 minutes of wall time on 8 cores; the
display link comes up much earlier (look for `DISP_CNCT(SYS_DIAGLOG_REG_OK)`
in `serial.log`).

## 3. Lines and peers

| Line | Device on the real unit | Peer (`--peer`) | State |
| --- | --- | --- | --- |
| `sci3` | display unit (touch, keys, brightness) | `panel` (default): `tools/ze0_peers/panel.py --sci3` | **real protocol**: handshake and touch frames from `docs/firmware/lcddrv.md`; the driver accepts them |
| `sci7` | GPS receiver | `gps`: `tools/ze0_peers/gps.py --no-fix` | **real report frame** (36-byte `A0`, `docs/firmware/navdrv.md` "Receiver frames"): it reaches `OBJ_GpsInfo` with the sent position; the car position and the map do not follow it yet (M8.H78). Control: `gps LAT LON`, `on`, `speed`, `heading`, `alt`, `stat HEX`, `sats N` on `gps.ctl` |
| `sci1` | audio/system microcontroller (micon) | `micon`: `tools/ze0_peers/micon.py` | model: replies are not accepted yet (`invalid TXT size`, M8.H45) |
| `sci8` | Bluetooth module | `bt`: `tools/ze0_peers/bt.py --mode absent` | stub |
| `uat3` | VCAN sub-micro (ACC, power, vehicle CAN) | `vcan`: `tools/ze0_peers/vcan.py` | model on the `ze0-h03` external UART: frames of `docs/firmware/can.md`, wire framing still open (M8.H49); UAT3's INTEVT is not pinned yet |
| `uat4` | second external UART | `uat4`: `tools/ze0_peers/uart.py` (raw bytes, guest TX in `uat4.tx`) | raw |

Gyro and wheel pulses (dead reckoning) are not modelled (M8.H32).

**`--peer vcan` stops the NK1 boot today** (2026-11-23; `--peer uat4` alone boots): the
kernel log ends at `[1] : start: 90000000…`. `ze0-h03` raises the UART
interrupt on INTEVT `0x8c0`, which on NK1 is SCIF0's vector and is not
maskable for this source. On NK1 the board UARTs most likely come through
the external interrupt controller behind INTEVT `0x240` (ISR `0x8803ec74`,
registers at `0xb9300000`); modelling it is TODO M8.H75. Use `vcan`
with the EU kernel B (README.md) until then.

## 4. The work directory

| File | What |
| --- | --- |
| `serial.log` | kernel and driver debug text (contains the card password: never commit) |
| `qemu.out` | QEMU's own messages |
| `mon.sock` | HMP monitor |
| `sciN.sock` | the chardev socket of each line a peer is on |
| `panel.ctl`, `gps.ctl`, `micon.ctl`, `vcan.ctl`, `uat4.ctl` | peer control sockets (one command line in, `OK …` back) |
| `panel.log`, `panel.events` | what the panel peer did; `events` holds the decoded touch records |
| `uistart.log` | with `--ui-start`: when the join was patched and when touch was unlocked |
| `ipl.txt` | the IPL patch |

## 5. Driving it

Tap and drag (panel coordinates, 800 × 480; the firmware flips y, so
screen (x, y) is panel (x, 480 − y), see §6):

```bash
printf 'tap 400 240\n' | socat - UNIX-CONNECT:$W/live/panel.ctl
# or without socat:
python3 -c "import socket,sys;s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1]);s.sendall(b'drag 100 240 600 240\n');print(s.recv(99).decode())" $W/live/panel.ctl
```

`frame HEX` sends a raw SCI3 payload (for example a key frame `3401`).
Scenario files go through `tools/ze0_ui.py --panel-sock $W/live/panel.ctl
--gps-sock $W/live/gps.ctl --hmp $W/live/mon.sock …`.

Screenshot:

```bash
python3 tools/ze0_screenshot.py screen --monitor $W/live/mon.sock -o $W/shot.png
```

Screenshots show vendor map data: keep them outside the repository.

Wheels and gyro (M8.H32): the speed-pulse and gyro pages are the QEMU object
`/machine/dr`. Set them over HMP while the guest runs:

```bash
# 83.33 pulses/s; with the unit's learned scale about 50 km/h
printf 'qom-set /machine/dr pulses-milli 8333\n' | socat - UNIX-CONNECT:$W/live/mon.sock
printf 'qom-get /machine/dr irqs\n' | socat - UNIX-CONNECT:$W/live/mon.sock
```

`pulses-milli` is pulses per 100 ms tick × 1000 (0 = standing still).
`gyro0`…`gyro7` are the raw ADC words (zero and scale unknown, default 0).
The locator moves the car to the GPS only with good fixes: keep the GPS
peer's stat at 0x00 (its default). Record:
[`EXP-2026-11-23-M8.H32-trailer-test`](../experiments/EXP-2026-11-23-M8.H32-trailer-test.md).

Debugger: add `--gdb 1240` and use `tools/ze0_gdb.py` (see
[`debugging.md`](debugging.md)). Useful breakpoints for input:
`0x03d16300` (lcddrv queues a touch), `0x03d284e4` (kepdrv `InputLcdTouch`),
`0x03d27344` (kepdrv `IsKeyControlNotify`, where touch is dropped today).

`ZE0_SCIF_TRACE=scif3` in QEMU's environment prints the SCR/LSR/timeout
events of one SCIF to `qemu.out`; `-M ze0,…,hpbdmac-trace=on -d unimp`
logs the DMA side.

## 6. What works today (2026-11-23)

- The display link: handshake, polls, touch frames ACKed and queued, read
  by `kepdrv`.
- **UI and touch need `--ui-start`** (with `--gdb PORT`). Without it the
  screen state stays in `INI_STARTUP` and `kepdrv` drops every touch.
  Both wait for the audio side, i.e. the audio micom on `sci1`, which is
  not modelled yet (M8.H45):
  - `INI_STARTUP` is left on a join of `ANTITHEFT_CC_NTF_COMP_OK` and
    `NOTICE_AUDIO_SOURCE`;
  - the touch guard is cleared by `CApi_AntitheftUnlock`.

  `--ui-start` runs `tools/ze0_uistart.py` on the gdb stub. It makes the
  join wait for the first event only, then clears the guard at the first
  touch. It holds the stub until that touch, so attach your own gdb after
  `uistart.log` says `touch unlocked`. Record:
  [`EXP-2026-11-23-M8.C1n-ini-startup-join`](../experiments/EXP-2026-11-23-M8.C1n-ini-startup-join.md).
- With `--ui-start` on the US card, the consent screen
  (`SRT_COLD_I_AGREE_NAM`) comes about 120 s of guest time after boot.
  This is after AppLaunch's 60 s wait for the anti-theft module.
  - "OK" is at screen (277, 382), so tap at panel (277, 98).
  - The map screen then follows, and its "ZOOM IN" button (screen ≈ 765,
    410, panel `tap 765 70`) zooms the map.
- **Touch y is flipped.** The firmware turns the panel y around
  (`docs/firmware/touch.md` §4), so a button at screen (x, y) takes
  `tap x 480-y`.
- The buttons are drawn into DU plane 1, which `ze0_screenshot.py screen`
  does not show yet (M8.C1t). To see them, use
  `ze0_screenshot.py plane --monitor $W/live/mon.sock -n 1 -o $W/p1.png`.
  It writes both pages of the buffer; the UI is in rows 0–479.
- GPS: the 36-byte `A0` report reaches `OBJ_GpsInfo`; the car position and the map do not follow it yet (M8.H78).

## 7. Without the launcher

The launcher is a thin wrapper; the QEMU line it prints can be run by
hand. The parts that matter: `-M ze0,dbgmsg=0x880404c4,nk=NK1,ipl-patch=IPL,
flash=NAND,sci3=c3`, `-chardev socket,id=c3,path=W/sci3.sock,server=on,wait=off`,
`-kernel CARD -drive if=sd,index=0,file=CARD,format=raw,snapshot=on`,
`-icount shift=0,sleep=off`. Start each peer after its socket exists. A
peer must answer at once: with `-icount` a slow answer arrives at an
arbitrary guest time.
