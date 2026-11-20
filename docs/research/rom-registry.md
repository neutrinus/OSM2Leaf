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

## What is not here

- Build A (`0x200200`) has one file, `ReleaseMain.skn`, stored
  uncompressed; it has no hive.
- `user.hv` (HKCU, 12 keys) has nothing about the SD card; its only path
  value is `Software\Microsoft\Automotive\AuiApp` `Path`.
- The hive cell layout is derived from these files (`tools/cehive.py`
  docstring); every link resolves and every key is reached (0 dangling), but
  it is not checked against a CE source.
