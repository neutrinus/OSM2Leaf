# Bluetooth stack (EU 2011, builds A and B)

Static map of the head-unit Bluetooth stack: what each module does, how the
modules call each other, the paired/connected device data model, where the
two-phone limit lives, and what changed in the 2014/2016 builds. Read-only
knowledge (M1.41); nothing was run on hardware and no patch is built. The wire
layer on `SCI8:` (BCSP, 38400) is covered in
[`bt-wire.md`](bt-wire.md) (M8.H55).

Status tags: **VERIFIED** (a command reproduces it), **OBSERVED** (seen in
strings/assembly, not executed), **HYPOTHESIS** (a reading, not proven).
Every VA is EU 2011; build A starts at `0x200200`, build B at `0x3e00200`.
VAs come from `tools/cerom.py` (never fitted deltas), function starts from
`tools/pdata.py` / `nk_decomp.py pdata`. SH-4 code is little-endian.

## 1. Modules

Code size is the module `size` from `cerom.py modules`; exec section VAs from
`cerom.py sections`. All A modules are in the apps image, the two B modules in
the kernel/updaters image.

| Module | ROM | Code (bytes) | Role | Evidence | Status |
| --- | --- | --- | --- | --- | --- |
| `BT_FW.dll` | B | 49152 | UART driver, BCSP framing, DFU download; exports `FWB_Init/Open/Read/Write/IOControl/Close/Deinit` | `cerom.py exports BT_FW.dll`; strings `DFU_CreatCOMBCSP`, `yabcsp_event` | VERIFIED |
| `BT_MGR.dll` | A | 438784 | BCSP command layer and profile init; stream driver `BTA1:`–`BTA9:` on `SCI8:` | exports `BTA_Init/Open/Read/Write/IOControl/…`; strings `MGR_BT_hfpInit`, `MGR_BT_a2dpInit`, `MGR_BT_pbapInit`, `MGR_BT_dunInit` | VERIFIED |
| `BT_ENG.dll` | A | 450560 | C++ engine layer: `DeviceManagementEngine`, `TelEngine`, `PhonebookEngine`, `AudioEngine`, `DunEngine`; pairing/search/connect state machines | mangled exports `*Engine@Bt@@`; pdata 2224 records | VERIFIED |
| `BT_WRPENG.dll` | A | 88064 | thin wrapper exporting the engine-open functions used by `PhoneBTA.exe` | `Bt_OpenDmEngine`, `Bt_OpenPbEngine`, `Bt_OpenTelEngine`, `Bt_OpenAudioEngine` | VERIFIED |
| `BT_DB.dll` | A | 15872 | paired/inquired device database and device-info getters | exports `Bt_PairedDeviceList_*`, `Bt_DeviceInfo_*`; pdata 96 records | VERIFIED |
| `BT_Modem.dll` | A | 25088 | DUN serial stream driver on `COM8:` | exports `COM_Init/Open/Read/Write/IOControl/…` | VERIFIED |
| `PhoneBTA.exe` | A | 697856 | phone application: joins the engine layer (`BT_WRPENG`) and the object store (`OBJDLL`) | imports `Bt_OpenDmEngine`, `Bt_PairedDeviceList_Size`, `OBJ_NetDevSts_BT_writeInit` | VERIFIED |
| `PhoneCC.dll` | A | 223744 | phone UI COM control (`DllGetClassObject`) | exports `DllGetClassObject`, `DllRegisterServer` | VERIFIED |
| `BtAudioCC.dll` | A | 52736 | Bluetooth audio UI COM control | exports `DllGetClassObject`, `DllRegisterServer` | VERIFIED |
| `BtUpdate.exe` | B | 46080 | updater carrying the radio module firmware payload (not patchable by us) | `cerom.py modules --image-start 0x3e00200` | OBSERVED |

`BT_DB.dll` and `BT_ENG.dll` have `attr=1007` (ROM with compressed data);
`BT_MGR.dll`, `BT_Modem.dll`, the CC controls and the EXEs have `attr=0007`.

## 2. Features

| Feature | String / export | Evidence | Status |
| --- | --- | --- | --- |
| Hands-free profile | `MGR_BT_hfpInit`, `hfp:%d`, `bt_hfp_rap_dial` | strings in BT_MGR sec0 | VERIFIED |
| A2DP / AVRCP | `MGR_BT_a2dpInit`, `MGR_BT_avrcpInit`, `a2dp:%d`, `avrcp:%d`, `A2D_CONNECTED`, `AVR_CONNECTED` | strings in BT_MGR/BT_ENG sec0 | VERIFIED |
| Phonebook (PBAP/OPP) | `MGR_BT_pbapInit`, `MGR_BT_oppInit`, `pb_connect`, `pb_waitPhonebook` | strings in BT_MGR/BT_ENG sec0 | VERIFIED |
| DUN | `MGR_BT_dunInit`, `DunEngine`, `COM8:` "BT (DUN)" | export + strings | VERIFIED |
| Pairing / search | `pairing`, `abortPairing`, `search`, `abortSearch` on `DeviceManagementEngine` | mangled BT_ENG exports | VERIFIED |
| TTY / TTS voice prompts | `hnw_voi_bt_00_16` … `hnw_voi_bt_11_19` | strings in BT_ENG sec0 | OBSERVED |

## 3. Interfaces — call graph between modules

```text
PhoneBTA.exe ──imports──> BT_WRPENG!Bt_Open{Dm,Tel,Pb,Audio}Engine
                    └────> BT_DB!Bt_PairedDeviceList_*/Bt_DeviceInfo_*
PhoneCC.dll / BtAudioCC.dll ──COM──> PhoneBTA.exe (messages)
BT_WRPENG.dll ──thin wrapper──> BT_ENG.dll engines
BT_ENG.dll ──21 imports──> BT_DB.dll ({Add,Clear,Retrieve,Size,Update,
                           CollectIdList}_PairedDeviceList, DeviceInfo_*)
BT_MGR.dll ──stream driver──> BT_FW.dll over SCI8: (BCSP, M8.H55)
BT_Modem.dll ──DUN stream──> COM8:
BT_FW.dll (B) ──SCI8:──> Bluetooth radio; BtUpdate.exe carries its firmware
```

Evidence: `cerom.py imports BT_ENG.dll` prints 21 `BT_DB!Bt_*` slots (e.g.
slot `0x032a1004` = `Bt_OpenDatabase`, `0x032a101c` = `Bt_PairedDeviceList_Size`,
`0x032a102c` = `Bt_DeviceInfo_GetCurrentConnectedId`); `cerom.py imports
PhoneBTA.exe` prints `BT_WRPENG!?Bt_OpenDmEngine@@…` and the `BT_DB` getters.
BT_MGR's imports contain `COREDLL!CreateFileW` (#168), `WriteFile` (#171),
`ReadFile` (#170), `SetCommState` (#118) and `DebugShellDll`, i.e. the serial
path, plus `Errlogdll!ErrorLogMsg` and `SYS_INF!SYS_DiagLogSet`.

`BT_FW.dll`'s `SCI8:` open is at `fn 0x035c4714` → `fn 0x035c53a0`
(`bt-wire.md`); BT_MGR's is at `fn 0x03694364`.

All profile dispatch inside the engines is **indirect** (`jsr @Rn` through
COM vtables at `0x0324229c`, `0x03242454`, `0x01dfb1bc` …), so "no static
caller" for an engine method does not mean it is unused (AGENTS.md trap).

## 4. Data — paired device table

`BT_DB.dll` sec0 exec starts at `0x032f1000`. The database handle global is
`0x01e050f8`, which `va_class.py` reports as `OUTSIDE no section` (BSS/heap,
not a stored constant). The three list getters have these implementations:

| Export | Export VA | Implementation | Role |
| --- | --- | --- | --- |
| `Bt_OpenDatabase` | `0x032f2f7c` | loads global `0x01e050f8`, calls `fn 0x032f1f14` | open/initialise DB |
| `Bt_PairedDeviceList_Add` | `0x032f319c` | `fn 0x032f27e8` → insert `fn 0x032f1384` | add paired device |
| `Bt_PairedDeviceList_Clear` | `0x032f3100` | `fn 0x032f2898` | clear list |
| `Bt_PairedDeviceList_Size` | `0x032f3170` | tail-jump `fn 0x032f1330` | count occupied slots |
| `Bt_DeviceInfo_GetCurrentConnectedId` | `0x032f3044` | `fn 0x032f2904` | the single active device id |
| `Bt_DeviceInfo_GetLastConnectedId` | `0x032f3070` | `fn 0x032f296c` | last-connected id (reconnect policy) |
| `Bt_DeviceInfo_GetSelectedDeviceId` | `0x032f30d4` | — | selected id |

**Paired capacity — six devices.** `fn 0x032f1330` at `0x032f1350` executes
`mov #5,r3` then `cmp/hi r2,r3` (loop for `r2 = 0..5`, six iterations); the
body at `0x032f1358`–`0x032f1364` shifts `1 << r2` and ANDs it with a 32-bit
word at the device block. The insert helper `fn 0x032f1384` at `0x032f13b0`
loads `mov.w @(…),r7 ; [0x032f146c]=0x021c` and applies the same bounded
`cmp/hi` loop at `0x032f13bc`. So the table holds a **6-bit membership mask**;
the capacity constant is the `5` at VA `0x032f1350` (VERIFIED by disassembly).

**Connected capacity — one device.** `Bt_DeviceInfo_GetCurrentConnectedId`
and `…GetLastConnectedId` are scalar getters (no array return). In
`BT_ENG.dll`, `fn 0x0325fdc4` prints `%s *** Selected device ID ***`
(`0x03241a24`), `%s *** Last connected ID ***` (`0x03241a44`) and `%s ***
Current connected ID ***` (`0x03241aa0`): one current id is kept and the
reconnect choice is by last-connected/selected id. `?maxEventSource@Engine@Bt@@IBAIXZ`
at `0x032670ce` is `mov #4,r0` (max concurrent event sources = 4, not device
count). Profile ids in the device-info functions are compared against
`2`, `4`, `6` at `0x032f291e`–`0x032f2926`, with `mov #6,r5` at `0x032f2942`
(a 1..6 profile index set).

Per-device info block: every `Bt_*` export adds `0x24` (36 bytes) to the
passed handle (`add #36,r4` at `0x032f3038`, `0x032f3064`, `0x032f3122`,
`0x032f3190`); the paired slot uses a 32-bit mask word.

The nine `BTA1:`–`BTA9:` instances (M1.39 registry) are logical per-profile
endpoints, not nine concurrent phones: `BT_ENG.dll fn 0x03266464`
(`sh4xref --to 0x032450e0`, the UTF-16LE `BTA1:`) opens them and indexes
object slots 66/87/88/89 (`mov #66,r3; shll2 r3` at `0x03266552`,
`0x0326660a`, `0x03266628`, `0x03266644`).

## 5. Verdict: why two phones work badly

**`policy in code`** (VERIFIED). The paired-device capacity is a code
immediate in our own `BT_DB.dll` (`mov #5` at `0x032f1350`, six slots) and the
active connection is a single id chosen by last-connected/selected id in our
`BT_DB`/`BT_ENG`. No HCI error from the radio module was found that would make
this a `module firmware` limit, so the patch idea is **not closed**: changing
the six-slot bound or the reconnect selection would be a code/data patch in
our modules. The real-world symptom is plausibly a second phone displacing
the first on reconnect with a small paired table (HYPOTHESIS — not tested on
hardware). What the radio's own firmware enforces beyond this is UNKNOWN and
out of scope.

## 6. What could be changed

| Item | VA (EU2011) | Change type |
| --- | --- | --- |
| Paired-device capacity (`mov #5`, six slots) | `0x032f1350` (BT_DB sec0) | code/data patch in our module |
| Paired-list insert bound (`mov.w 0x021c` mask) | `0x032f13b0` (BT_DB sec0) | code/data patch |
| Single active device (scalar `GetCurrentConnectedId`) | `0x032f3044` / `0x032f2904` | code change (data model) |
| Reconnect choice (last-connected/selected id) | `0x032f296c`, BT_ENG `fn 0x0325fdc4` | policy change in code |
| Max event sources (`mov #4`) | `0x032670ce` (BT_ENG sec0) | code patch |
| `SCI8:` baud table / DCB constants | `0x035c356c`, `fn 0x035c7f94` (BT_FW B) | data patch (see `bt-wire.md`) |
| Radio module firmware (`BtUpdate.exe` payload) | — | **not patchable** by us |

No patch is built by this task.

## 7. Differences between builds

Sizes from `cerom.py modules` on `archive/us256.img`, `archive/eu2014-256.img`,
`archive/eu2016-256.img`:

| Module | EU2011 | US2011 | EU2014 | EU2016 |
| --- | --- | --- | --- | --- |
| `BT_MGR.dll` | 438784 | 438272 | 440320 | 440320 |
| `BT_ENG.dll` | 450560 | 444928 | 451072 | 451072 |
| `BT_DB.dll` | 15872 | 15872 | 16384 | 16384 |
| `PhoneCC.dll` | 223744 | 223744 | 224256 | 224768 |
| `BtAudioCC.dll` | 52736 | 52736 | 52736 | 53248 |
| `PhoneBTA.exe` | 697856 | 697856 | 706560 | 706560 |
| `BT_FW.dll` (B) | 49152 | 49152 | 49152 | 49152 |
| `BtUpdate.exe` (B) | 46080 | 46080 | 46080 | 46080 |

`BT_FW.dll` and `BtUpdate.exe` are the same size in all four builds, so the
wire/firmware layer is unchanged. The stack above changed from 2011 to 2014
(`BT_MGR`, `BT_DB`, `BT_ENG`, `PhoneBTA`, `PhoneCC`) and again slightly in 2016
(`PhoneCC`, `BtAudioCC`); whether the six-slot constant itself changed needs a
separate disassembly of EU2014 `BT_DB.dll` (follow-up). US2011 is close to
EU2011 except for a smaller `BT_ENG.dll`.

Evidence: EXP-2026-11-24-M1.41-bluetooth-stack, claims C-6430–C-6439. See also
[`bt-wire.md`](bt-wire.md) (M8.H55) for the `SCI8:` wire layer and
EXP-2026-11-20-M1.39-hardware-map for the `BTA1:`–`BTA9:` registry.
