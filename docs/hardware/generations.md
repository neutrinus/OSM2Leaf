# Hardware of the three Leaf generations (static evidence from our images)

Status: **static only.** Every cell below is a string, module name, VA or count
printed by a command on a card image we hold, or `unknown`. Nothing here was
measured on a bench or in a car. The primary target stays the ZE0 2011 unit;
the other columns serve the long-term goal "run any of them in QEMU".

Record: [`EXP-2026-11-22-M8.G1`](../experiments/EXP-2026-11-22-M8.G1-generations.md)
(C-6940–C-6949). Related: [`head-unit.md`](head-unit.md) (ZE0 2011 only),
[`image-versions.md`](../research/image-versions.md),
EXP-2026-11-20-M1.36 (module census of four cards).

## Samples

| Column | Cards / firmware heads used | Head SHA-256 (first 12) |
| --- | --- | --- |
| ZE0 | `LEAF_2011-2012_QSD-309-101_navi158_eu.img` (EU 2011), `LEAF_2011-2012_US.img` (US 2011); heads `archive/head256.img`, `archive/us256.img` | `92aa525d0db2`, `70d945d823f9` |
| AZE0 | `LEAF_2014_EU_QSD-357-101.img`, `ENV200_2016_EU_QSD-390-100.img`; heads `archive/eu2014-256.img`, `archive/eu2016-256.img` | `30da3dce5c63`, `208b4fdbe5b4` |
| ZE1 | **No ZE1 / Leaf 2 image held.** The post-2016 image referenced in the task, `ENV200_2019_25920-6WX1C-EUR.img` (e-NV200, QY8x, `CLA-NAVI06-01`, C-123/C-1028), is not a Leaf 2 and is no longer on the image server (HTTP 404 on 2026-11-22; index lists only the four images above). | — |

The 2016 card is an e-NV200, but its firmware (`X212ECNI.063`, `CLA-NAVI05-01`)
is the AZE0 family, so it is used as a later X212 data point, not as ZE1.

## Per-generation table

Evidence is given as `string` / `module` / `load=VA` where the command printed
it; `unknown` means no command used here printed a value. "load=…" is the
`load=` field of `tools/cerom.py … modules` for the stated build (A `0x200200`,
B `0x3e00200`, C `0x5200200`).

| Row | ZE0 — 2011–2012, `X210` | AZE0 — 2013–2017, `X212` | ZE1 / Leaf 2 — 2018+ |
| --- | --- | --- | --- |
| **CPU / SoC** | SH-4A little endian: ROMHDR `usCPUType 0x000001a6` (A and B, EU+US 2011). BSP string `R0P7772A00020S` (`strings -a … \| grep R0P7772`, in `SdCardLch.pdb` path); platform `CETUS_SH4` in PDB paths. Header string `FX210ECNI.158` (EU, file `0x200015`), `X210NBNI.147` (US, `0x200016`). Exact part unknown; SH-NaviJ family is a hypothesis in `head-unit.md`. | Same CPU/BSP platform name: `usCPUType 0x000001a6` (A and B, 2014+2016), `R0P7772A00020S`, `CETUS_SH4`. Header `X212ECNI.100` (2014, file `0x200014`), `X212ECNI.063` (2016, `0x200014`). X212 is a platform *revision marker*, not a different BSP name. | `unknown` (no ZE1 image; see Samples) |
| **RAM size and map (ROMHDR)** | Build B: `ulRAMStart 0x89e40000`, `ulRAMEnd 0x8e600000` ⇒ 0x04bc0000 = 75,235,328 B (71.75 MiB) CE window; DRAM mapped `0x88000000`–`0x8e600000` = 102 MiB. Build A: `physfirst 0x8cae1000`, `physlast 0x8e233c88` (EU) / `0x8e2788e0` (US), `ulRAMEnd 0x8cae1000`. `ulFSRamPercent 0x00000028`. | Build B: `ulRAMStart 0x8a640000`, `ulRAMEnd 0x8e600000` ⇒ 0x03fc0000 = 66,846,720 B (63.75 MiB) CE window; same 102 MiB DRAM ceiling, CE window starts **0x800000 (8 MiB) higher**. Build A: `physfirst 0x8cae1000`, `physlast 0x8e3d51b8` (2014) / `0x8e3d8150` (2016). `ulFSRamPercent 0x00000028`. | `unknown` (no ZE1 image) |
| **NOR/NAND flash + driver** | `FMD1:` device string (UTF-16LE, all heads); registry `Drivers\BuiltIn\Flash  Dll (SZ) = flash.dll`, `Prefix (SZ) = FMD`, `Index 0x1` (decoded EU2011 `default.hv`). Kernel B/C: `FlashManager.dll` `load=0x885e7000`, `fmmdrv.dll` `load=0x885f5000`. Geometry (8 MiB NOR, 135 blocks) comes from LeafSDTools via `head-unit.md`, not from these heads. | `FMD1:` present. Kernel B: `FlashManager.dll` `load=0x88655000`, `FlashManager2.dll` `load=0x88663000`, `fmmdrv.dll` `load=0x88672000` (2014). Kernel C 2014 and B/C 2016: `fmmdrv_05.dll` `load=0x88627000`, `fmmdrv_07.dll` `load=0x88631000` (C, 2014) instead of plain `fmmdrv.dll`. NOR vs NAND geometry `unknown` (registry hives of 2014/2016 are compressed and `nk_decomp.py files` fails with `UnmappedAccess … 0x00000000..0x00000002`). | `unknown` (no ZE1 image) |
| **Display** | 800 × 480, 16 bpp (`head-unit.md`, VERIFIED from registry); `System\GDI\Drivers  Display (SZ) = ddddifull.dll` (EU2011 decoded hive), `Clarion\DriverSettings\Display  LCDTable 0x3`; `lcddrv.dll` on `SCI3:` (head-unit.md). Module `ddddifull.dll` `load=0x88443000` (B). No DirectDraw module. | Resolution `unknown` (no `800`/`480` string in the heads; 2014/2016 hive not decodable). `ddddifull.dll` still present (`load=0x884a1000`, B 2014) **plus DirectDraw** `ddraw.dll` `load=0x8835f000`, `ddcore.dll`, `ddhel.dll` in kernel B. `Bolero.dll`/`BOLERODLL.dll` (2011) dropped; `Celavidll.dll`/`CelaviDrv.dll` added in A. | `unknown` (no ZE1 image) |
| **Audio** | `Audio.exe` (A, `load=0x8d64e000`), `Speech.exe` (`load=0x8cf83000`), `wavessi1.dll`/`wavessi2.dll`, `anwdrv.dll` (`load=0x884c4000`, B) on `SCI1:`; SSI `0xffe00000` and `DspDrv.dll`/`MuteDrv.dll`/`BeepDrv.dll` in `head-unit.md`. | Same module set; `Audio.exe` size 328,704 B (2014) vs 213,504 B (2011, M1.36). `wavessi1.dll` `load=0x8870b000`, `anwdrv.dll` `load=0x88524000` (B 2014). Codec/hardware decoder `unknown`. | `unknown` (no ZE1 image) |
| **Bluetooth** | `BT_FW.dll` `load=0x886f1000` (B), `BT_MGR.dll` (A), `BT_ENG.dll`, `BT_Modem.dll`; `SCI8:` HSCIF string (all heads), `BT_FW.dll` 34,816 B (M1.36). | Same modules: `BT_FW.dll` `load=0x8876d000` (B 2014), 34,816 B; `BT_MGR.dll` 385,024 B vs 383,488 B (M1.36). `SCI8:` present. Radio chip `unknown`. | `unknown` (no ZE1 image) |
| **CAN sub-microcontroller** | `CAN.dll` (`load=0x88505000`, B) opens `UAT3:` — string present in the whole head and in the extracted `CAN.dll` code section. `serial_uat.dll` `load=0x88665000`. `VCanUpdateCC.dll` in decoded EU2011 registry. Baud literals 230400/19200/2400 (`head-unit.md`). | `CAN.dll` present (`load=0x88568000`, B 2014) but **`UAT3:` string absent** from the whole head and from the extracted/uncompressed `CAN.dll` code; the compressed `.data` section fails to decode. Port is therefore `unknown`. `serial_uat.dll` `load=0x886e2000`. | `unknown` (no ZE1 image) |
| **USB host** | `UsbOhci.dll` (`load=0x8d4a9000` A / `0x886c1000` C), `usbd.dll`, `usbhid.dll`, `Usb.exe`, `UsbAudioCC.dll`; OHCI registers `0xffe70400` from `head-unit.md`. No EHCI module. `USB Disk` string absent. | Still OHCI: `UsbOhci.dll` `load=0x8d5ba000` (A) / `0x886e6000` (C). Adds `UsbConMngCC.dll` (`load=0x9117e000`, A) and mass storage `usbdisk6.dll`/`usbmsc.dll` in kernel C; `USB Disk` string present. No EHCI module. | `unknown` (no ZE1 image) |
| **Telematics** | `Telema.exe` (`load=0x8fad4000`, A) with 21 `Telema*` modules (`cerom.py … modules \| awk '{print $2}' \| grep -i '^Telema' \| wc -l` → 21); `COM3:`/`COM4:`/`COM8:` strings (TCU USB serial and BT DUN). | `Telema.exe` (`load=0x8fde1000`, A) with the same base set **plus** `TelemaCCIpcSender.dll`, `TelemaListCC.dll`, `TelemaSrchCC.dll`; `COM3:`/`COM4:`/`COM8:` present. | `unknown` (no ZE1 image) |
| **Camera** | `CameraCC.dll` (`load=0x8d68b000`, A), `VIN.dll` (`load=0x8869d000`, B); wiring not in firmware (`head-unit.md`). | `CameraCC.dll` (`load=0x8d7c5000`, A; 75,264 B vs 71,680 B in M1.36), `VIN.dll` (`load=0x88719000`, B). | `unknown` (no ZE1 image) |
| **Wi-Fi** | `unknown` — no Wi-Fi/WLAN/802.11/WPA module or meaningful string; only generic `ndis.dll`, `dhcp.dll`, `ppp.dll`, `tapi.dll`, `tcpstk.dll` in A. | `unknown` — same generic network modules, no Wi-Fi driver or string. | `unknown` (no ZE1 image) |
| **OS version / build** | Windows CE 5.0 (`WINCE500` in PDB paths; `Booting Windows CE version %d.%2.2d for (%s)` string), SH-4, ROMHDR `usCPUType 0x000001a6`. Build workspace `10eNavi_ProductTestNK\…\CETUS_SH4_SHIP_Release` (`TestMode.pdb`); date string `2011-05-17` in head. | Windows CE 5.0 (`WINCE500`, explicit `Microsoft Windows CE.NET` string), SH-4, `usCPUType 0x000001a6`. Build workspace `10EV_EU\WINCE500\CETUS_SH4`, date strings `2012-07-23`, `Jun 26 2014`. | `unknown` (no ZE1 image) |

## Falsifier result

The task's falsifier asks whether EU2014 names **the same BSP string and RAM
window** as EU2011. Measured: the BSP string `R0P7772A00020S` and the platform
name `CETUS_SH4` **are identical**, but the ROMHDR RAM window is **not** —
`ulRAMStart` moves from `0x89e40000` to `0x8a640000` (+8 MiB) and the header
string changes from `FX210ECNI.158`/`X210NBNI.147` to `X212ECNI.100`. The
falsifier is therefore **not met as a whole**: AZE0 is a revision *inside the
same CETUS BSP family*, with a shifted RAM map and modified flash/graphics
drivers, not a verbatim board with added modules only.

## What would be needed for a real ZE1 column

A 2018+ Leaf 2 / ZE1 EU (or US) navigation SD card image — its first ~256 MiB
is enough to read ROMHDR, module lists and header strings with the same
commands. The 2019 e-NV200 QY8x image is a different engine family
(`CLA-NAVI06-01` / `X08-03-00` / ZENRIN, C-123/C-1028), is not a Leaf unit, and
is no longer downloadable from `https://files.viaaq.eu/sd-images/` (404 on
2026-11-22). No architecture can be asserted for it from bytes we hold, so the
ZE1 column stops at `unknown`.
