# SD card blocker/unblocker on a Raspberry Pi Pico (RP2040)

Status: **design + firmware, untested on hardware.** The driver passes a
host self-test against a simulated card (C-1941); nobody has locked a real
card with it yet, and no locked card has been tried in a unit. The bench test
is M6.9. Record: [`EXP-2026-11-06-M6.11`](../experiments/EXP-2026-11-06-M6.11-pico-sdlock.md).
Task: `TODO.md` M6.11.

This page explains how to build a small USB tool that puts an SD card into
the CMD42 lock state the navigation unit expects, and takes it out again, so
that a card image written on a PC can be used in the car.

## 1. Why a separate device

- The unit accepts a card only if it is **locked with the unit's CMD42
  password** and its own boot-time unlock succeeds. A card without a password
  ("no security") is also rejected and shows `SD UNLOCK NG` (C-790, C-797,
  C-798, EXP-2026-11-06-M2.8).
- CMD42 (`LOCK_UNLOCK`) is a card command, not a file-system operation. USB
  card readers do not pass it (their bridge chip speaks USB mass storage
  only), so a PC with a USB reader cannot set or clear the password. A
  native SDHCI slot with `mmc-utils` might (that is the M6.9 Linux route);
  many laptops do not have one.
- In **SPI mode** every SD card accepts CMD42. An RP2040 has a hardware SPI
  block, 3.3 V GPIO and USB, and costs about €5. That is all it takes.

The unit also has its own SD LOCK/UNLOCK service menu (EXP-2026-11-06-M2.13,
C-1882), so a card that stays with one unit can be (un)locked there. The Pico
tool is for what the menu cannot do: locking a card the unit has never seen,
checking a card's lock state off the bench, and the image-then-lock flow
without the unit.

Locking and unlocking change only the card's security state. They do not
read, write or move any data block (as long as the ERASE bit is never sent;
section 8).

## 2. What the tool does, in CMD42 terms

SD Physical Layer Simplified Spec §4.3.7. The CMD42 data block is
`[flags, PWD_LEN, password...]`; flags are bit 0 `SET_PWD`, bit 1 `CLR_PWD`,
bit 2 `LOCK_UNLOCK`, bit 3 `ERASE`.

| Tool command | CMD42 flags | Effect | Survives power-off? |
| --- | --- | --- | --- |
| `setlock YES` | `SET_PWD` + `LOCK_UNLOCK` | store password, lock now | yes: a card with a password **always powers up locked** |
| `lock` | `LOCK_UNLOCK` | lock a card that has this password and is unlocked | yes |
| `unlock` | none (`LOCK_UNLOCK` = 0) | unlock for this power session only | **no**: re-locks at next power-up |
| `verify` | unlock, then lock | prove the password on a locked card, leave it locked | — |
| `clear YES` | (unlock if needed), then `CLR_PWD` | remove the password | yes: card is a plain card again |
| — | `ERASE` | **forced erase: deletes the password AND all data** | **never sent; the code refuses it** |

Consequence for the workflow: a temporary `unlock` is useless for writing the
card in a PC, because moving the card to the reader power-cycles it and it
locks again. To write a locked card on a PC, **`clear`** the password, write,
then **`setlock`** again (section 7).

## 3. The password

**Do not commit the password.** The repo rule (`card-test-plan.md`, "Do not
attempt") is not to publish the CMD42 password; the firmware therefore has
no password compiled in. You type it into the tool at run time (`pw ...`),
it lives in RAM only and is gone when the Pico is unplugged.

What is known (claims ledger):

- Scheme: **4 unit-specific bytes followed by a fixed 12-character ASCII
  suffix** (C-075). The suffix is a firmware literal in `PRGUpdate.exe` and
  `TestMode.exe` (C-1880, VERIFIED, EXP-2026-11-06-M2.13); the 8-digit
  prefix is assembled at run time per unit (C-1881).
- The 4 unit bytes are shown on the unit's service screen **"SD PIN"** as
  8 hexadecimal digits (reported by Marek from a real unit; the exact value
  stays out of the repo). M2.13 recovers the bytes from `SDHC.dll`
  (`byPasswordLen`/`dPassword` logging, C-792/C-793); M2.13b traces how the
  prefix is derived.
- **Encoding (C-1940, HYPOTHESIS, strong):** an SD password is at most
  **16 bytes** (`PWD_LEN` ≤ 16). 8 digits typed as ASCII plus the 12-character
  suffix would be 20 bytes, which no SD card accepts. 4 raw bytes + 12 ASCII
  bytes is exactly 16. So the 8 digits are hex for 4 raw bytes:

  ```text
  pw hex:<the 8 digits from the SD PIN screen> ascii:<the 12-char suffix of C-075>
  ```

  The tool refuses anything longer than 16 bytes, so the 20-byte reading
  cannot be sent by accident.
- **Byte order is UNKNOWN** (C-1940): the screen may print the 4 bytes in
  memory order or as a little-endian number. Use the order shown first. If
  the unit then says `SD UNLOCK NG`, `clear` the card with the password you
  set (you know it, so nothing is lost) and try the reversed byte order
  (section 7.4). M2.13 should settle this from the firmware; prefer its
  result when it lands.

Keep a paper/offline note of **which password each card was locked with**.
A card whose password is lost can only be recovered by forced erase, which
this tool deliberately cannot do.

## 4. Hardware

### 4.1 Parts

| Part | Notes | Indicative price |
| --- | --- | --- |
| Raspberry Pi Pico (RP2040) | Pico, Pico H or any RP2040 board with SPI0 on GP16–19. Pico W works too (LED off). RP2350/Pico 2 works if built with `PICO_BOARD=pico2`. | €4–6 |
| microSD socket breakout, **3.3 V, no regulator, no level shifter** | e.g. a passive "microSD breakout" (push-push socket, pins broken out). A microSD→SD adapter with wires soldered to its pads also works. | €2–8 |
| 10 kΩ resistors ×4 | pull-ups on CS, MISO, DAT1, DAT2 (many breakouts already have them) | — |
| 10 µF + 100 nF capacitors | across 3V3/GND at the socket (hot-insert inrush) | — |
| USB cable (data, not charge-only) | Pico ↔ PC | — |
| Spare microSD/SDHC cards | SDHC, not SDXC (C-149); same or larger capacity than the image | €8–15 each |
| Ordinary USB card reader | for imaging (`dd`) on the PC | €8–15 |

Avoid the common blue "Micro SD Card Module" with an AMS1117 regulator and a
74LVC125 buffer when you can: it expects **5 V** on `VCC` (from `VBUS`,
Pico pin 40). Fed with 3.3 V its regulator drops the card supply below spec.
If that is all you have, power it from `VBUS` and keep the logic pins on
GPIO; its buffer runs at 3.3 V, so the levels still match.

### 4.2 Logic levels and power

- SD cards are 2.7–3.6 V devices; the RP2040 GPIO is 3.3 V. **Connect
  directly, no level shifter.** Never put 5 V on any card pin.
- Supply the card from **`3V3(OUT)`** (Pico pin 36). The Pico's regulator
  gives about 300 mA; a card needs under 100 mA even while busy.
- Put 10 µF + 100 nF across 3V3/GND at the socket. Inserting a card into a
  live socket draws an inrush current that can reset the Pico without it.
  Removing and re-inserting the card is also the **power cycle** that tests
  "locks at power-up"; no power switch is needed.

### 4.3 Wiring (SPI0)

| Pico GPIO | Pico pin | Function | microSD pin (SPI name) | Pull-up |
| --- | --- | --- | --- | --- |
| GP16 | 21 | SPI0 RX | 7 DAT0 (**MISO / DO**) | 10 kΩ to 3V3 (firmware also enables the internal one) |
| GP17 | 22 | CS (GPIO) | 2 DAT3 (**CS**) | 10 kΩ to 3V3 |
| GP18 | 24 | SPI0 SCK | 5 CLK (**SCK**) | — |
| GP19 | 25 | SPI0 TX | 3 CMD (**MOSI / DI**) | — (10 kΩ optional) |
| 3V3(OUT) | 36 | 3.3 V | 4 VDD | — |
| GND | 23 (or 38) | ground | 6 VSS | — |
| — | — | — | 8 DAT1, 1 DAT2 | 10 kΩ to 3V3 each (do not leave floating) |

microSD contact numbering, contacts facing you, notch on the right:
`1 DAT2 · 2 DAT3/CS · 3 CMD · 4 VDD · 5 CLK · 6 VSS · 7 DAT0 · 8 DAT1`.
(Full-size SD adapter: `1 CS · 2 CMD · 3 VSS · 4 VDD · 5 CLK · 6 VSS ·
7 DAT0 · 8 DAT1 · 9 DAT2`.)

```text
   Raspberry Pi Pico                     microSD socket
  +------------------+                 +----------------+
  | GP16 (21) RX  <--+-----------------+ 7 DAT0 / DO    |--[10k]--3V3
  | GP17 (22) CS  ---+-----------------+ 2 DAT3 / CS    |--[10k]--3V3
  | GP18 (24) SCK ---+-----------------+ 5 CLK          |
  | GP19 (25) TX  ---+-----------------+ 3 CMD  / DI    |
  | 3V3  (36)     ---+---+-------------+ 4 VDD          |
  | GND  (23)     ---+---|---+---------+ 6 VSS          |
  +------------------+   |   |         | 8 DAT1         |--[10k]--3V3
                     10uF=  =100nF     | 1 DAT2         |--[10k]--3V3
                         |   |         +----------------+
                        GND GND
```

Keep wires under ~15 cm. The tool runs SPI at 400 kHz for init and 4 MHz
after it; CMD42 moves 18 bytes, so speed does not matter and short wires
are only for signal integrity.

## 5. Software stack: why C with the Pico SDK

Chosen: **C, Raspberry Pi Pico SDK 2.x**, one `.uf2`.

- **Exact control of what goes on the wire.** The driver
  (`tools/sdlock-pico/src/sd_card.c`) sends only CMD0, 8, 55, 41, 58, 9, 13,
  16 and 42. There is no file-system layer and no read/write/erase command
  in the binary, so nothing can touch data blocks behind our back. The
  MicroPython `sdcard.py` driver and FatFs-style libraries do block I/O at
  mount time and have no CMD42 support; we would write the same low-level
  code anyway, but on top of an interpreter.
- **The protocol code is plain C99 without SDK calls** (`sd_proto.c`,
  `sd_card.c`), so it is compiled and tested on a PC against a simulated card
  (`tools/sdlock_pico_check.py`, run by `tools/selftest.py`). The self-test
  is what proves the ERASE bit is unreachable (C-1941).
- **Nothing to install on the Pico.** Drag one `.uf2` onto the `RPI-RP2`
  drive; no interpreter, no files, no REPL to misuse.
- MicroPython would be quicker to change on the bench. It is a valid
  alternative for experiments, but the C build is the reference.

## 6. Build, test and flash

### 6.1 Toolchain (Debian/Ubuntu)

```bash
sudo apt install cmake gcc-arm-none-eabi libnewlib-arm-none-eabi build-essential git python3
git clone --depth 1 -b 2.1.1 https://github.com/raspberrypi/pico-sdk ~/pico-sdk
git -C ~/pico-sdk submodule update --init --depth 1 lib/tinyusb   # USB serial
export PICO_SDK_PATH=~/pico-sdk
```

### 6.2 Host self-test (no hardware)

```bash
python3 tools/sdlock_pico_check.py -v
# expected last line: sdlock host test: 572 checks, 0 failed
```

### 6.3 Firmware

```bash
cd tools/sdlock-pico
cmake -S . -B build -DPICO_BOARD=pico      # pico_w / pico2 for other boards
cmake --build build -j
ls build/sdlock.uf2
```

### 6.4 Flash

1. Hold **BOOTSEL**, plug the Pico into USB, release. A drive `RPI-RP2`
   appears.
2. Copy `build/sdlock.uf2` onto it. The Pico reboots into the tool.
   (Or `picotool load -x build/sdlock.uf2`.)
3. Open the USB serial port: Linux `/dev/ttyACM0`, macOS
   `/dev/tty.usbmodem*`, Windows `COMn`.

   ```bash
   picocom /dev/ttyACM0        # or: screen /dev/ttyACM0, minicom -D /dev/ttyACM0, PuTTY
   ```

   Press Enter; the help text and a `>` prompt appear.

## 7. Operator procedures

Commands are typed at the `>` prompt. `setlock` and `clear` need the word
`YES`. Every command prints `OK` or `ERROR <n> - <reason>`, then the raw
`R1`/`R2` bytes and the resulting `card state: LOCKED | unlocked`. The
built-in LED (Pico, not Pico W) is on while the card is reported locked.

Before any procedure: **spare card only.** Never run `setlock`, `clear`,
`unlock` or `lock` on the original factory card (`card-test-plan.md`
"Do not attempt").

### 7.1 Bench check of the tool (first time, any spare card — M6.9)

Use a throw-away password here, not the unit's, e.g. `pw ascii:test1234`.

1. On the PC: write any small known file to the card, note
   `sha256sum /dev/sdX` (whole device). Eject.
2. Insert the card into the Pico socket. `init` → expect `init: OK`,
   `type=SDHC/SDXC`, `CMD42 (CCC class 7)=yes`, `card state: unlocked`.
   `CMD42 ... = NO` means the card cannot be locked: use another card.
3. `pw ascii:test1234` → `password: 8 bytes in RAM`.
4. `setlock YES` → `setlock: OK`, `card state: LOCKED`.
5. Pull the card out and push it back (power cycle). `init`, then `status`
   → `LOCKED`. This proves the password is stored and locks at power-up.
6. `verify` → `OK`, still `LOCKED`.
7. Wrong-password check: `pw ascii:wrong123`, `unlock` → expect
   `ERROR 10 - LOCK_UNLOCK_FAILED`, state still `LOCKED`.
8. Put the card in the USB reader: Linux shows no medium or I/O errors
   (`dmesg`). This is the expected behaviour of a locked card.
9. Back in the Pico: `pw ascii:test1234`, `clear YES` → `unlocked`.
   Reseat, `init` → `unlocked` (password gone).
10. On the PC: `sha256sum /dev/sdX` equals step 1. Record reader model, card
    model and results in the M6.9 EXP.

### 7.2 Prepare a card for the car (image first, then lock)

1. **Write the image with an ordinary USB reader** (fast; the card must have
   no password):

   ```bash
   lsblk                                   # identify the card: /dev/sdX
   sudo dd if=CARD.img of=/dev/sdX bs=4M conv=fsync status=progress
   sudo cmp -n "$(stat -c %s CARD.img)" CARD.img /dev/sdX && echo SAME
   ```

   (`cardcheck.py --image` / M5.10 for checking the image itself.)
2. Eject, move the card to the Pico. `init` → `unlocked`, class 7 `yes`.
3. `pw hex:<SD PIN digits> ascii:<C-075 suffix>` → `password: 16 bytes`.
   Anything other than 16 bytes means a typo.
4. `setlock YES` → `LOCKED`.
5. Reseat, `init`, `status` → `LOCKED`; `verify` → `OK`.
6. `pwforget`, unplug the Pico. Label the card (which unit, which byte
   order, date). The card goes into the unit with the power off.

### 7.3 Change a card that is already locked (unlock → write → lock)

1. Pico: `init` → `LOCKED`. `pw ...` with the card's password.
2. `clear YES` → `unlocked`. Reseat, `init` → `unlocked`. (A plain `unlock`
   is not enough: the reader power-cycles the card and it re-locks.)
3. PC: write and compare as in 7.2 step 1.
4. Pico: `setlock YES`, reseat, `status` → `LOCKED`, `verify` → `OK`.

### 7.4 The unit shows `SD UNLOCK NG`

1. Power the unit off, take the card out (M6.4 recovery: re-seat once
   first, `card-test-plan.md`).
2. Pico: `init`, `pw` with the password you used, `verify` → `OK` proves the
   card is locked with what you think it is.
3. `clear YES`, then `setlock YES` with the **4 unit bytes reversed**
   (`hex:AABBCCDD` → `hex:DDCCBBAA`), same suffix. Record both attempts.
4. If both orders fail, stop: the password model (C-075/C-1940) is wrong for
   this unit; feed the result back to M2.13.

## 8. Safety

- **Forced erase (CMD42 `ERASE`, bit 3) destroys everything** — the
  password and every data block — on a locked card. The tool cannot send it:
  `sdp_lock_block()` is the only producer of CMD42 payloads and rejects any
  flag outside `SET_PWD|CLR_PWD|LOCK_UNLOCK`; the host test tries all 256
  flag values and audits every frame the simulated card receives (C-1941).
  Do not "add an erase command" to this tool, and do not use other tools'
  erase functions (e.g. `mmc lock ... erase`) on any card you care about.
- **A lost password = a dead card** (only forced erase recovers it). Write
  down the password and byte order per card; `setlock` asks for `YES`.
- **Wrong card:** the tool reads the CSD first and refuses to send CMD42 if
  command class 7 (lock) is absent. Cheap/fake cards may claim class 7 and
  still misbehave; test with 7.1 before trusting a card model. Use SDHC, not
  SDXC (C-149).
- **Original card:** never lock, unlock, clear or write it. Keep it out of
  the bench. Image it read-only only (P1 in `card-test-plan.md`).
- **Voltage:** 3.3 V only on card pins. No 5 V, no level shifters that
  pull up to 5 V.
- **Hot-plug:** fine with the 10 µF cap; if the Pico resets on insertion,
  just reconnect the terminal and run `init` (the password must be typed
  again; it is not saved).
- **Password visibility:** the terminal echoes what you type and may keep it
  in scroll-back/log files; close or clear the terminal log afterwards. The
  tool itself never prints the password back.
- **No data operations:** the firmware contains no block read, write or
  erase command (CMD17/18/24/25/32/33/38 are absent; the host test fails if
  any other command reaches the card).

## 9. Error reference

| `ERROR` | Meaning | What to do |
| --- | --- | --- |
| 1 no response | MISO stays high | card seated? wiring, 3V3, pull-ups, CS |
| 2 CMD0 not idle | card answered garbage | short wires, check SCK/MOSI swap |
| 3 CMD8 voltage | not an SD v2 response | bad card/socket |
| 4 ACMD41 timeout | card never finished init | power supply, try another card |
| 5 R1 error | a command was rejected; see R1 bits | note R1, report |
| 6 no data token | CSD read got no start token | wiring (MISO), card fault |
| 7 no CMD42 | CSD class 7 clear | use another card model |
| 8 data rejected | data response ≠ `0x05` | report `data-resp` byte |
| 9 busy timeout | card held MISO low > 3 s | reseat, `init`, `status` |
| 10 LOCK_UNLOCK_FAILED | wrong password, wrong length, or no password set | check `pw` (16 bytes?), byte order |
| 11 bad arg | refused locally (ERASE or length) | — |
| 12 unexpected state | e.g. `setlock` on a card that is already locked | `clear` it first with its password |
| 13 not initialised | `init` not run since the card was inserted | `init` |

## 10. Open points

- Real-card test of 7.1 (M6.9): which card models work; whether
  `SET_PWD`+`LOCK` in one command locks immediately on them (the firmware
  falls back to a separate `LOCK` if not).
- Whether the unit accepts a card locked by this tool (M6.5, needs a unit).
- Password byte order and length from firmware (M2.13).
- The `.uf2` was not built in the Claude sandbox (building the external SDK
  was not permitted there); `sd_proto.c`/`sd_card.c` compile for Cortex-M0+
  with `-Werror`. First local build: record the result in the M6.9 EXP
  (C-1943).
