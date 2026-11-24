# Power and ACC state machine (`PowerMonitor.dll`)

Status: **static read of the EU 2011 kernel (build B), not observed at
runtime**. Every VA below is derived from the ROM headers with
`tools/cerom.py` (build B image start `0x3e00200`, `va_base 0x88000000`);
instructions are little-endian SH-4 (`tools/sh4dis.py`). Method, counts and
controls: EXP-2026-11-22-M8.H53-powermonitor-static.md.

## Where it lives

| Item | Value |
| --- | --- |
| Module | `PowerMonitor.dll`, `vbase=0x039d0000`, `vsize=0xe000`, entry `0x039d53d0` |
| Exported stream driver | `POW_Init 0x039d540c`, `POW_Deinit 0x039d54b4`, `POW_IOControl 0x039d5e64`, `POW_PowerUp/Down 0x039d7340` (+ stubs) |
| Code section | `rva=0x1000`, `vsize=0x85f8`, file `0x04267200`, VA `0x039d1000` (uncompressed; C-2128) |
| Function table | 290 `.pdata` records, `0x039d4708`–`0x039d84xx` (`tools/pdata.py table`) |
| Main C++ vtable | `0x039d1c10`, **derived** by walking back from the literal pool holding `SysDisable` (`0x039d56f4`); not a fitted address |

`POW_Init` calls `0x039d5578` → `0x039d55e8`, which runs `InitEvents`
(vt+`0x348`, `0x039d57bc`) → `NotifySystemEXE` (vt+`0x34c`, `0x039d58f8`) →
`StartThreads` (vt+`0x350`, `0x039d6d2c`), in that order. `InitEvents` creates
five unnamed events and the named manual-reset event `NOTIFY_ACC_OFF_EVENT`
at `0x039d21bc` (literal load at `0x039d5974`, handle stored at object+`0x2c`).

## Inputs

| Input | Where it enters | Evidence |
| --- | --- | --- |
| ACC / IGN status on `CAN1:` | `CCanDriverIF::Init 0x039d4ae4` logs `bAccStatus[%d] bIgnStatus[%d]`; `CanCallAcc 0x039d4960` → `IOCTL_GPIO_ACCESS_BOLERO_ACC 0x80202060`; `CanCallIgn 0x039d49d0` → `IOCTL_CAN_IGN_CHG 0x8020205c`; `CanCallAccDet 0x039d4a40` → `IOCTL_CAN_ACCDET_NOTICE 0x80202064` | strings `0x039d1420`–`0x039d15c8`, pools `0x039d49b8`/`0x039d4a28`/`0x039d4a94` |
| CAN change events upward | event names `EVT_POW_NOTIFY_ACC_CHG 0x039d1638`, `EVT_POW_NOTIFY_IGN_CHG 0x039d1668` | UTF-16LE strings in sec0 |
| ACC-off interrupt | `AccOffDetectThread 0x039d5a7c`: interrupt id **17** (`mov #17,r5` at `0x039d5a92`), `InterruptInitialize`-style call, `WaitForSingleObject(event@+4, INFINITE)`; `WAIT_OBJECT_0` → `AccOffProc` via vt+`0x344` at `0x039d5ade` | log strings `0x039d2254`, `0x039d2288` |
| Backup / power-loss interrupt | `BackupDetectThread 0x039d5b30`: interrupt id **16** (`0x039d5b78`), mutex `MUTEX_MCT_WRITEFILE` (`0x039d2490`), mutex wait `0x1388` = 5000 ms (`0x039d5bce`), then callback vt+`0x314` | log strings `0x039d2364`, `0x039d238c`, `0x039d2430` |
| Video/line monitor | `LineMonitorDetectThread 0x039d4f08` on `VIN1:`, interrupt id **50** (`0x039d4f6c`), 50 ms poll | log strings `0x039d1a48`, `0x039d19d0` |
| Host commands | `POW_IOControl 0x039d5e64`: `0x80132000` sets flag +`0x34`; `0x80132004` → vt+`0x304`; `0x8013200c` sets event +`0x0c` (system reset); `0x80132010` → vt+`0x354`; `0x80132014` → vt+`0x358` | pool `0x039d5f34`–`0x039d5f48` |

## State diagram (observed transitions)

"State" below is the value of object fields and the thread that owns the wait;
it is not a named enum in the binary.

| Present state | Input | Next state | Code (VA) |
| --- | --- | --- | --- |
| INIT | `POW_Init` | events created, named `NOTIFY_ACC_OFF_EVENT` registered | `0x039d540c` → `0x039d55e8` → `0x039d57bc` / `0x039d58f8` |
| INIT | `StartThreads` | RUN: ACC-off, backup, reset, HW, operation and WDT threads live | `0x039d6d2c` |
| RUN (flag +`0x38` = 0) | ACC-off interrupt 17 | ACC_OFF_FIRST | `0x039d5a7c` → vt+`0x344` |
| ACC_OFF_FIRST | first entry: flag +`0x38` 0→1; log `Pow Off 1st Detect!!!`; `SetEvent(NOTIFY_ACC_OFF_EVENT)` | WAIT_APP_SHUTDOWN | `0x039d56f4`, log `0x039d217c`, set at `0x039d5728` |
| WAIT_APP_SHUTDOWN | application layer signals event at object+`0x30` within **40000 ms** (`0x9c40`) | SHUTDOWN_COMPLETE → HW_SHUTDOWN | wait `0x039d573e`, log `0x039d2050` |
| WAIT_APP_SHUTDOWN | timeout after 40000 ms | FORCE_OFF → HW_SHUTDOWN | log `0x039d20b8` |
| ACC_OFF (flag +`0x38` ≠ 0) | second ACC-off / `IOCTL 0x8013200c` → `SystemResetThread` | ACC_OFF_SECOND (no second notify, no wait) | log `0x039d1fb4`; reset path `0x039d5ca8` |
| ACC_OFF_FIRST | flag +`0x38` = 0 but +`0x34` ≠ 1 | SKIP_NOTIFY ("Acc Off Not Notify SystemEXE...") | `0x039d571c`–`0x039d5754` |
| HW_SHUTDOWN | event at object+`0x10` signalled | ordered flush/disable list (below) | `0x039d5d14` |
| BACKUP | backup interrupt 16, mutex free within 5000 ms | MCT write callback, log `BackUp Detect!!!!` | `0x039d5b30` |
| SYSTEM_RESET | `POW_IOControl 0x8013200c` | `AccOffProc(reason=4)` | `0x039d5eec` → `0x039d5ca8` |

`AccOffProc` also calls `SysDisable` (vt+`0x308`, `0x039d5f5c`) before the
notification and `PowerOFF_Sequence` (vt+`0x320`, `0x039d6428`) after it.
`SysDisable` is guarded by flag +`0x40` (log `System Disable Proc Already`,
`0x039d26c8`) and runs `VideoMute` (`VIN1:`, `IOCTL_VIN_DISABLE 0x80062024`),
`Mute Force On` and `KeyDisable` (`KEP1:`, `ERR_DTAL_IOCTL_KEP_SET_NOTIFY_KEY
0x801f200c`). `PowerOFF_Sequence` is guarded by flag +`0x3c` (log
`System Shutodown Proc Already`, `0x039d2bf8`) and ends in
`KernelIoControl(IOCTL_HAL_POWER_SEQUENSE 0x01013000)` at `0x039d6494`.

## Shutdown save / flush list (in call order)

`HWControlThread 0x039d5d14` calls, after its wait and with no dependence on
the reason for the shutdown:

| # | Step (vtable) | Implementation | Driver / IOCTL |
| --- | --- | --- | --- |
| 1 | Bolero ACC off (vt+`0x330`) | `0x039d6750` | `GPI1:`, `IOCTL_GPIO_ACCESS_BOLERO_ACC 0x80092004` |
| 2 | I²C disable (vt+`0x32c`) | `0x039d6630` | `I2C1:`, `0x8005200c` (C-6421) |
| 3 | Disk shutdown / cache flush (vt+`0x328`) | `0x039d6510` | `SDC1:`, `IOCTL_SDC_SHUTDOWN 0x8003200c` |
| 4 | SRM commit disable (vt+`0x334`) | `0x039d6858` | `SRM1:`, `IOCTL_SRM_ENABLE_COMMIT 0x80142004` |
| 5 | FLM disable (vt+`0x338`) | `0x039d696c` | `FLM1:`, `IOCTL_FLM_ALL_DISABLE 0x8021200c` |
| 6 | FMD write disable (vt+`0x33c`) | `0x039d6a7c` | `FMD1:`, `IOCTL_FMD_WRITE_DISABLE 0x80112014` |

`OperationControlThread 0x039d5dc8` additionally waits up to 5000 ms
(`0x1388` at `0x039d5e0e`) for another module to set the flag at object+`0x44`
before the final `KernelIoControl(0x01013000)` with code 3.

## Timeouts

| Timeout | Ticks/ms | Site |
| --- | --- | --- |
| Application-layer shutdown after ACC-off | `0x9c40` = 40000 ms | pool `0x039d57a4`, load `0x039d573c` |
| Backup mutex (`MUTEX_MCT_WRITEFILE`) | `0x1388` = 5000 ms | `0x039d5bce` |
| Operation-control module wait | `0x1388` = 5000 ms | `0x039d5e0e` |
| Video line poll | `0x32` = 50 ms | `0x039d4fb0` |

## Watchdog and software reset (M8.H67, static)

Build B's watchdog is a **software** monitor in `PowerMonitor.dll`, not a
periodic write to an on-chip WDT register. `StartThreads` (`0x039d6d2c`)
creates the `C.WdtMonitor` object through `C.WdtMonitor::Init 0x039d71ac`
→ `Start 0x039d71d8`, which creates `EVENT_WDT_STOP` (string `0x039d4038`) and
`EVENT_WDT_START` (string `0x039d40c8`) and starts a thread through
`0x039d7340`. The monitor thread `WdtClearThread 0x039d706c` compares a
return value with the literal `0x0102` at `0x039d7192`; when equal it calls
`KernelIoControl(0x01013048)` (pool `0x039d719c`, load `0x039d70ee`), and on
non-equal returns waits `0x0bb8` ms (3000, load `0x039d715e`). `vt+0x000` is
`WdtStart 0x039d6f90` (pool `0x039d1c10`); the `125<<2 = 500` immediate at
`0x039d7018` has unknown units. `vt+0x2f8` is `Init 0x039d55e8`, which calls
monitor setup `0x039d6fc4` at `0x039d57d6`.

The four candidate WDT register pages (`0xffffff80/84/88`, `0xfff80000`) have
**zero** literal words in the `PowerMonitor.dll` code section (`wdt_scan.py
--check`); `0xfff80000` belongs to the display unit (C-6920) and is named by
`IOLIB.dll`, not this module. The kernel's only timer literal in the scoped
range is TMU0 (`nk.exe 0x88004d00` → `0xffd80000`). Method, counts and
controls: EXP-2026-11-24-M8.H67-watchdog-reset.md.

The reset request is an OAL KernelIoControl, not a WDT write:
`POW_IOControl 0x039d5e64` (export #3) compares IOCTL `0x8013200c` (pool
`0x039d5f3c`, load `0x039d5e92`) → `SystemResetThread 0x039d5ca8` →
`AccOffProc (0x039d56f4, reason 4)` via `vt+0x344` (pool `0x039d5cf6`) →
`PowerOFF_Sequence 0x039d6428` → `KernelIoControl 0x039d6494` with
`IOCTL_HAL_POWER_SEQUENSE 0x01013000` (pool `0x039d6500`, load `0x039d64a4`),
logging `KernelIoControl[IOCTL_HAL_POWER_SEQUENSE]` at `0x039d2cc4`.
No micon frame is visible in this module.

## What is **not** established

- **No flash-write instruction was found in the ACC-off path of this module.**
  The observable path is ACC-off → `NOTIFY_ACC_OFF_EVENT` → application layer,
  and then a cache flush and write-disable sequence. The save itself is in
  another module (`SystemEXE.exe` sends `POW1:`, string at `0x017f7c`;
  C-5351 and C-8200 describe the AppLaunch/SystemEXE side). This is a
  module-scope negative, not a claim that no data is saved.
- The callback invoked by `BackupDetectThread` through vt+`0x314` (`0x039d6204`
  only chains BT/OneSeg resets) is a different method; the owner of the
  `MCT_WRITEFILE` write remains **UNKNOWN** (it is not in this module's
  exported API).
- Runtime ordering, real CAN frames, and the effect on an L4/QEMU boot were
  not measured (M8.H54 is the persistence loop at L4).

## Reproduction

```bash
cd /home/marek/projekty/OSM2Leaf
python3 tools/powermonitor_scan.py --selftest
python3 tools/powermonitor_scan.py archive/head256.img --image-start 0x3e00200 --check
# expected: selftest PASS 5/5; --check PASS, 14/14 strings, 9/9 xrefs,
#           23 methods, 19/19 IOCTLs, 5/5 immediates, 1/1 pool
```
