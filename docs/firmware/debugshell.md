# `DebugShell.dll` on `SCI6:` — retail debug shell (M8.H65)

Source: EU2011 `archive/head256.img` (SHA-256
`d3e5eac9cb5b4cbd…`, first 128 MiB), build B at `--image-start 0x3e00200`.
Every VA below comes from `tools/cerom.py` module/section data; nothing is a
fitted delta. All addresses are EU2011 = US2011 for the two modules named here
(`docs/research/rom-atlas.md` lists the same sizes and hashes for both heads).
Reproduce with the commands in §7.

## 1. Verdict

The debug shell **is present and started in the retail configuration**. It is
a stream driver `DSD1:` implemented by `DebugShell.dll`; it opens the serial
device `SCI6:` itself and its receive path emits a `>>` prompt (static
finding; the prompt was not observed in the live runs of §3). This is not dead data: the
command-name array has live code references (§4). The falsifier of M8.H65
("command table has no reference from any code") does **not** fire.

Two modules implement it:

| Module (build B) | Load VA / vbase | Size | Role |
| --- | --- | --- | --- |
| `DebugShell.dll` | `0x886c1000` / `0x03920000` | 46,080 B | stream driver `DSD1:`, owns `SCI6:`, built-in commands |
| `DebugShellDll.dll` | `0x886d0000` / `0x03910000` | 16,384 B | client shim exported to other modules (`DebugShellEntryFunc`, `DebugShellOutput`, `DebugShellDeleteFunc`) |

`DebugShell.dll` exports exactly the 10 stream-driver entry points
`DSD_Init 0x0392351c`, `DSD_Deinit 0x039234d0`, `DSD_Open 0x039235d0`,
`DSD_Close 0x039235d4`, `DSD_Read 0x03927974`, `DSD_Write 0x039235e0`,
`DSD_Seek 0x03923640`, `DSD_IOControl 0x0392364c`, `DSD_PowerDown` /
`DSD_PowerUp 0x039265fc`.

## 2. Start condition (why it runs on a retail card)

Neither registry hive has a `DebugShell` value under `init`; the driver is
started by the `AppLaunch.dll` table, the same mechanism that launches
`Navi.exe` (M1.34, `docs/research/rom-registry.md`).

| Evidence | Value |
| --- | --- |
| `default.hv` key | `Drivers\Launch\DebugShell`: `Dll = DebugShell.dll`, `Prefix = DSD`, `Index = 1`, `Order = 8` → device `DSD1:` |
| `default.hv` key | `Drivers\Launch\SCIF6`: `Dll = serial_scif.dll`, `Prefix = SCI`, `Index = 6`, `DeviceArrayIndex = 6` → device `SCI6:` |
| AppLaunch record 32 | `0x03bb8530`, type 1, `id = 0x28`, priority 127/0, name `DSD1:`, key `\Drivers\Launch\DebugShell`, `waits[2] = 10/30000 1/30000` — waits for **SCI6** (id 10) and **SCI1** (id 1), 30 s each |
| AppLaunch record 14 | `0x03bb4e10`, id 10, `SCI6:` ← `\Drivers\Launch\SCIF6`, priority 110/0 |
| `ce_drivers.py` B join | `32 Launch/default DebugShell DebugShell.dll DSD1 0x8 32 DSD1: id 0x28 waits 10/1` |

So there is no retail/debug build gate in the launch path: `AppLaunch.dll`
starts `DSD1:` after the serial ports come up. The driver then opens `SCI6:`
itself — the UTF-16 string `SCI6:` sits at sec0 file `0xdfc` (VA
`0x03921dfc`) and is loaded by `fn 0x03924930` (`sh4xref --to 0x03921dfc`).
`CEN1:` (VA `0x039213a8`, UTF-16) is the ACM driver the shell opens for
console I/O; its failure strings are `Can't Use/Open ACM Driver...`.

`DSD_IOControl` checks a `DebugShellMode` flag and refuses non-IOCTL traffic
with `CDsdMain::IOControl DebugShellMode OFF. Error!!` (UTF-16 at VA
`0x03921848`, loaded in `fn 0x03923e58`). The flag's setter was not located;
this is a **hypothesis**, not a second gate.

## 3. Live evidence on the factory image

A `-M ze0` boot of the EU2011 card (M8.H1 chardevs, `--serial-peer sci6=…`)
prints, in the DBGMSG serial log:

```
line 110: DebugShellDll: DLL_PROCESS_ATTACH
line 288: DSD: DLL_PROCESS_ATTACH
line 466: [BTMGR]DebugShell::BtMgrDebugShell resistration res=1
line 509/825/904: DebugShellDll: DLL_PROCESS_ATTACH  (further modules)
```

i.e. the driver and client modules attach to the shell during an ordinary
retail boot. A `>>` prompt string exists at VA `0x03921dec` and is emitted by
the receive path `fn 0x0392530c`; the byte callback treats `0x0d` (CR) as the
line terminator and `0x21` (`!`) as a special prefix. However, the live
injection of §7 captured no prompt and no command reply on `sci6` (only two
early `SVR_DISC:` kernel strings at t=1.0/1.37 s), so the interactive path is
**not demonstrated** by this session — see the EXP. It is not needed for the
static result above.

## 4. Command table

The names are a 16-byte-strided array starting at VA `0x039213b8` (sec0 file
`0x3b8`): each entry is a NUL-padded 16-byte ASCII name, indexed by an integer
command id. `fn 0x03924470` computes `name = 0x039213b8 + id*16` (`mov r6,r8`
then two `shll2 r8`), compares it to the received token with `strlen`/`memcmp`
(thunks `0x0392811c` / `0x03928104`) and dispatches through vtable slot 90.
`EXIT` and `C` are separate 4-byte / 2-byte comparisons in `fn 0x039237a0`,
which dispatches through slots 92 and 91.

| # | Command | Name VA | Handler / parser VA (evidence) | Output strings (VA) |
| --- | --- | --- | --- | --- |
| — | `EXIT` | `0x039213a0` | `0x039237a0` — compares 4 bytes, vtable slot 92 | — |
| — | `C` | `0x0392139c` | `0x039237a0` — compares 2 bytes, vtable slot 91 | `CEN1:` ACM open errors |
| 0 | `showid` | `0x039213b8` | parse `0x03924470`; executor `0x03924380` | `%02d ` (`0x03921a44`), `No RegisterID.` (`0x03921a34`); `0x03924380` calls vtable slot 93 for each id 1..99 |
| 1 | `showinitid` | `0x039213c8` | parse `0x03924470` (same array) | `No RegisterID.` re-used via helper `0x039263b0` |
| 2 | `showidtime` | `0x039213d8` | parse `0x03924470`; executor not resolved | `ID:%3d TIME:%10d ` (`0x03921a2c`) |
| 3 | `fix` | `0x039213e8` | parse `0x03924470`; executor not resolved | `ERROR. Cannot set fix ID [00].`, `ERROR. ID is not correct.` (`0x03921a80`, `0x03921aa0`) |
| 4 | `release` | `0x039213f8` | parse `0x03924470`; executor not resolved | — |
| 5 | `version` | `0x03921408` | parse `0x03924470`; executor not resolved | `Software Build Ver : ` (`0x03921afc`), `NK Ver : ` (`0x03921ba4`), `Device Ver : ` (`0x03921d70`) |
| 6 | `sramoutput` | `0x03921418` | parse `0x03924470`; executor not resolved | `ERROR. Input StartAddress.` / `ERROR. Input the output size.` (`0x03921abc`, `0x03921ad8`) |
| 7 | `mw` | `0x03921428` | parse `0x03924470`; writer-family `0x03924794` | `ERROR. Filler is less than 0xff/0xffff/0xffffffff?`, `ERROR. Count is between …`, `OK. Data output finished.` |
| 8 | `mh` | `0x03921438` | parse `0x03924470`; writer-family `0x03924794` | as `mw` (word variants) |
| 9 | `mb` | `0x03921448` | parse `0x03924470`; writer-family `0x03924794` | as `mw` (byte variants) |
| 10 | `mdump` | `0x03921458` | parse `0x03924470`; format select `0x03925218` | `%02X `, `%08X: ` (`0x03921f20`, `0x03921f38`); writes `mdump.bin` under `\UserSD` |

The vtable used by these objects starts at `0x03921468` and is installed by
constructors `fn 0x03923b04` and `fn 0x03923b7c` (`mov.l @(pc),r2` loads
`0x03921468`, stored as `this->vptr`). Slots 0…181 are import thunks into the
compressed IAT at `0x01f28000…`; slots 182…209 are real functions (slot 210 is
`0x03924470`, the name matcher). A full command → C++ method resolution needs
that object graph and is **out of scope** of this one-session reader task; the
rows above give every name, its verified address and the parser/handler VAs
that the disassembly does establish.

There is **no help text and no `help` command** in the module: the string pool
holds only the names above plus error/format strings. Any `help` behaviour
would have to come from a module that registers through `DebugShellDll.dll`.

## 5. What input it needs

- Device `SCI6:` (SCIF6, channel 6), opened by `DebugShell.dll` `fn 0x03924930`.
- RX on SCIF6 must reach the guest. `-M ze0` implements this through the
  named chardev `sci6` (M8.H1, `ze0-h01-serial-chardevs.patch`); SCIF6 is also
  the kernel debug SCIF, so `--serial-peer sci6=…` replaces the default
  `serial_hd(0)` backend for that channel.
- The driver prints `>>` (VA `0x03921dec`) from `fn 0x0392530c`
  (`DsdDrv recieve Control Command.` at VA `0x03921a50`) and then compares the
  received token with the fixed-length names above. The comparators use exact
  byte counts (4 for `EXIT`, 6 for `showid`), so the token is a bare command
  word; a trailing newline is consumed by the serial layer, not by the
  comparator.
- Other modules can add commands at runtime through `DSD1:` IOCTLs
  `IOCTL_DSD_REGISTER_ID`, `IOCTL_DSD_DELETE_ID`, `IOCTL_DSD_RCV_CMD` and
  `IOCTL_DSD_COMPLETE` (`DebugShellDll.dll` strings). The console is therefore
  a general in-guest control channel, not only the built-in list.

## 6. Open items (for a follow-up task)

- Resolve the C++ command objects and their virtual execution slots for rows
  1–10, giving one handler VA per command.
- Determine who writes the `DebugShellMode` flag and what turns it off.
- Confirm the exact RX framing (line ending / maximum token length) with a
  successful live command from §7.

## 7. Reproduce

```bash
# modules, exports, imports
python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img modules | grep -i debug
python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img exports DebugShell.dll
python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img imports DebugShell.dll

# strings and code xrefs
python3 tools/ce_strfind.py archive/head256.img --image-start 0x3e00200 --encoding all 'SCI6:' DebugShell
python3 tools/sh4xref.py archive/head256.img DebugShell.dll --image-start 0x3e00200 --to 0x039213b8
python3 tools/sh4dis.py  archive/head256.img DebugShell.dll --image-start 0x3e00200 --va 0x03924470 --count 60

# start condition
python3 tools/nk_decomp.py files archive/head256.img --image-start 0x3e00200 -o <scratch>/reg-B
python3 tools/cehive.py <scratch>/reg-B/default.hv --grep 'DebugShell|SCIF6'
python3 tools/ce_drivers.py archive/head256.img --image-start 0x3e00200 | grep -i debug
python3 tools/applaunch_table.py archive/head256.img dump | grep -E 'DSD1|SCI6'

# live channel (M8.H1 already on main)
bash tools/qemu-ze0/run.sh --qemu ~/.cache/qemu-ze0/build/qemu-system-sh4 \
  --image archive/head256.img --verinf QSD-302-100 --mapdb 16-16 \
  --ipl-patch <scratch>/ipl.txt --sd <card>.qcow2 --icount shift=0,sleep=off \
  --timeout 210 --workdir <scratch>/h65/run \
  --serial-peer "sci6=unix:<scratch>/h65/run/sci6.sock,server=on,wait=off"
python3 tools/ze0_serial.py peer <scratch>/h65/run/sci6.sock --send-hex 76657273696f6e0a --nowait
```
