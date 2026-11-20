# ROM registry: SD card, SD driver and the Navi launch

Source: the ROM registry hives `boot.hv`, `default.hv`, `user.hv` of build B
(`--image-start 0x3e00200`) and build C (`0x5200200`), decoded by the kernel
routine (`tools/nk_decomp.py files`) and read with `tools/cehive.py`
(M1.21, EXP-2026-11-19-M1.21-filesentry-decode, C-3520–C-3527). Build B's
bytes are identical on the EU2011 and US2011 heads, and build C's decoded
files are identical on both (same SHA-256), so every row below holds for
EU2011 and US2011. Paths are relative to the hive root (HKLM for
`default.hv`/`boot.hv`). Only key paths and the values needed here are
quoted; reproduce the full listing with:

```bash
python3 tools/nk_decomp.py files archive/head256.img --image-start 0x3e00200 -o /home/user/scratch/m1.21/eu-B
python3 tools/cehive.py /home/user/scratch/m1.21/eu-B/default.hv --grep 'SDProfile|Drivers\\SD|Launch\\SD|AppLch|^init'
```

## The SD card mount points (`SystemSD`, `UserSD`)

| Key (`default.hv`, builds B and C) | Value |
| --- | --- |
| `System\StorageManager\Profiles\SDProfile` | `Name` = `Main Slot SD Card`, `Folder` = `SystemSD`, `AutoMount` = 0 |
| `System\StorageManager\Profiles\SDProfile\FATFS` | `EnableCache` = 0 |
| `System\StorageManager\Profiles\SDProfile2` | `Name` = `Sub Slot SD Card`, `Folder` = `UserSD`, `AutoMount` = 0 |
| `System\StorageManager\Profiles\SDProfile2\FATFS` | `EnableCache` = 0 |

So the map card mounts as `\SystemSD` because the main slot's storage
profile names that folder, on the stock FAT file system (`FATFS`). The
second slot is `\UserSD`; `Drivers\Launch\LogSaverDriver` writes there
(`MountPath` = `\UserSD`, `WaitForMount` = 1).

## The SD driver

| Key | Value |
| --- | --- |
| `Drivers\Launch\SD` | `Dll` = `SDHC.dll`, `Prefix` = `SDC`, `Index` = 1 (the host controller) |
| `Drivers\SD\Card` | `Dll` = `SDHC.dll`, `Prefix` = `DSK`, `Index` = 1, `PortNumber` = 0, `Profile` = `SDProfile` |
| `Drivers\SD\Card2` | `Dll` = `SDHC.dll`, `Prefix` = `DSK`, `Index` = 8, `PortNumber` = 1, `Profile` = `SDProfile2` |

`Drivers\SD\Card` and `Card2` both carry `IClass` = the CE block-device
class `{A4E7EDDA-E575-4252-9D6B-4195D48BB865}`. Port 0 → `DSK1:` →
`SDProfile` → `\SystemSD`. The driver is `SDHC.dll` (build B module) for
both the controller and the disks; there is no `sdbus`/`sdmemory` stack.

## The Navi launch

The registry does **not** launch `Navi.exe`:

- `init` holds only `Launch20` = `device.exe` and `Launch30` = `gwes.exe`
  (`Depend30` binary `1400`).
- `device.exe` loads the built-in driver `Drivers\BuiltIn\AppLch`
  (`Dll` = `AppLaunch.dll`, `Prefix` = `LDR`, `Index` = 1, `Order` = 0).
- `AppLaunch.dll` carries the application list itself, as UTF-16 strings
  in its code section (build B, EU2011/US2011): `\windows\Navi.exe` at VA
  `0x03bc0f54` (with `NxJpNavi.exe`, `SystemExe.exe`, `AuiApp.exe`,
  `Speech.exe`, `Audio.exe`, … in the same table) and the
  `\Drivers\Launch\<name>` keys it activates (`\Drivers\Launch\SD` at
  `0x03bb8ba4`). The same module checks the card before launching:
  `\SystemSD\VER_INFO\HDD_INFO.TXT` (VA `0x03bc92f0`) next to `MapDBVer :
  %d <= [%d] <= %d` — the map-version gate of `docs/format/validation.md`.
  `python3 tools/sh4xref.py archive/head256.img AppLaunch.dll --image-start 0x3e00200 --to 0x03bc92f0`
  finds the `HDD_INFO.TXT` path loaded in `fn 0x03bd2ad8` and
  `fn 0x03bd2ce4` (EU2011); `\windows\Navi.exe` has no literal-pool
  reference, so the launch table is data (M1.34).

To change what starts, the target is `AppLaunch.dll`'s table, not a
registry key (C-3525).

## The launch table (M1.34)

Source: `AppLaunch.dll` build B sec0 (identical on EU2011 and US2011), read
with `tools/applaunch_table.py` (EXP-2026-11-20-M1.34-applaunch-table,
C-3528, C-3529, C-5350, C-5351). VAs are EU2011 (= US2011); build C has the
same layout at `0x03b92318` with 111 records.

```bash
python3 tools/applaunch_table.py archive/head256.img dump
python3 tools/applaunch_table.py archive/head256.img select --area 0x30 --name Navi.exe
```

- **Where:** base `0x03bb2330`, 112 records × `0x310` B, end `0x03bc7a30`.
  No literal points to a record; the base comes from the leaf getter
  `0x03bccb88` and the count from `0x03bccb84` (`mov #112,r0`), both called by
  the launcher main `fn 0x03bcc680`, which hands them to the walker
  `fn 0x03bcc5b0`. The walker starts one thread per selected record
  (`CreateThread(proc(type), rec)`, priority `rec[+0x25c]`).
- **Record:**

  | Offset | Field |
  | --- | --- |
  | `+0x000` | type: 1 driver, 2 DLL, 3 process, 4 process gated by the launch flag, 5 `NK2`, 6 `MountStorage`, 7 event, 8 `OpImg`, 9 virtual id; others (`LSD1:` = 10) are not started |
  | `+0x004` | boot-mode mask (mode 0/5/8 → `1`, 1 → `2`, 2 → `4`, 3 → `8`, 4 → `0x10`, 6 → `0x20`, 7 → `0x40`, 9 service tool → `0xffff`) |
  | `+0x008` | model base-type mask (`CApi_GetModelBaseType` 1 → bit 1, 2 → bit 2, -1 → any) |
  | `+0x00c` | area mask (JP `0x10000`, USA `0x40000`, Euro `0x20000`, RU `0x80000`, CN `0x100000`) |
  | `+0x010` | option flags (capability queries in `fn 0x03bcbc18`) |
  | `+0x014` | name, WCHAR[32] |
  | `+0x054` | path / driver key / event name |
  | `+0x25c` / `+0x25e` | u16 priority of the launcher thread / of the started main thread |
  | `+0x260` / `+0x264` | wait count / wait entries `{id, timeout_ms, arg, 0}` (`IOCTL_ACM_WAIT_ID` on `ACM9:`) |
  | `+0x304` | own id, signalled with `IOCTL_ACM_SET_ID` when the entry is up (ids ≥ `0xc0` never) |
  | `+0x30c` | argument: command line (3/4), entry point (2), event name (7) |

- **`Navi.exe` records:** five records, type 4, mode mask
  1, id `0xa2`: #77 `0x03bc0f00` and #79 `0x03bc1520` (Japan, base type 1/2),
  #78 `0x03bc1210` `NxJpNavi.exe` (Japan), **#80 `0x03bc1830` USA**, **#81
  `0x03bc1b40` Euro**. The EU record waits for ids 80 (`SystemEventGdi`),
  20 (`NAV1:`), 3 (`SRM1:`), 4 (`FLM1:`), 40 (`DSD1:`), 94 (not a table id)
  and **82 (system SD mounted and checked)**, 30 s each, and has no argument.

### The gate before `Navi.exe` runs

The type-4 thread `fn 0x03bcc078` creates `\windows\Navi.exe` and suspends its
main thread at once. It resumes it only when its waits have returned and the
launch error flag `0x01f733f0` is still 0. The `MountStorage` thread
(`fn 0x03bcc2dc` → `fn 0x03bd224c`) is what signals id 82, in this order:

1. open `SDC1:` and its IOCTLs `0x80032004`/`0x80032000` (retries) — fail →
   error `0x80` `NO SD CARD`;
2. wait for `DSK1:`, open the store, mount every partition — fail → `0x82`
   `SD INIT NG`;
3. partition 0 only (`fn 0x03bd2ecc(0)`): check 1 `fn 0x03bd2ad8` (HDD_INFO
   line 1 vs unit `+0x60`) — fail → `0x50` `DIFFERENT MAP CODE`; then check 2
   `fn 0x03bd2ce4` (MapDBVer in unit `+112..+114`) — fail → `0x51` `MAP DATA
   BASE UNMATCH` ([validation.md](../format/validation.md));
4. `SET_ID(82 + partition)`.

Every error goes through the dispatcher `fn 0x03bcafb8`, which sets the flag
to 1 on the first error it shows and then does not return (screen, wait for
ACC off, endless loop; C-5351). A failed check 1 therefore stops the sequence
before check 2, id 82 is never signalled, and `Navi.exe` stays suspended. On a
unit whose `KernelIoControl(0x01013200)` byte is `0x1x`/`0x2x` ("ProtoLevel")
errors `0x50`, `0x51` and `0x81` are only logged. For a generated card this
means: the card must mount as `DSK1:` partition 0 and its
`\SystemSD\VER_INFO\HDD_INFO.TXT` must pass check 1 and then check 2; the
launch record itself reads nothing from the card.

## What is not here

- Build A (`0x200200`) has one file, `ReleaseMain.skn`, stored
  uncompressed; it has no hive.
- `user.hv` (HKCU, 12 keys) has nothing about the SD card; its only path
  value is `Software\Microsoft\Automotive\AuiApp` `Path`.
- The hive cell layout is derived from these files (`tools/cehive.py`
  docstring); every link resolves and every key is reached (0 dangling), but
  it is not checked against a CE source.
