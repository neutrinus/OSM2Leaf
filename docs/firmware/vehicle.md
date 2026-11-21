# Vehicle screens and CAN signals (EU 2011, build A)

Static map of what reaches the SH-4 from the vehicle and what the drive
computer shows: the signal table, the consumers, and the drive-computer
formulas. Read-only knowledge (M1.43); nothing here is sent to a car and
nothing was run on hardware.

Status tags: **VERIFIED** (a command reproduces it), **OBSERVED** (seen in
strings/assembly, not executed), **HYPOTHESIS** (a reading, not proven).
Every VA is EU 2011 (build A) unless marked `B`; addresses come from
`tools/cerom.py` (`sections`, `exports`, `imports`, `va2file`) and are never
fitted deltas. SH-4 code is little-endian.

## 1. Modules

| Module | ROM | Code (bytes) | Role |
| --- | --- | --- | --- |
| `CAN.dll` | B (`0x3e00200`) | 91 666 | CAN stream driver; opens `UAT3:` (C-6413/C-6416) and runs the `MCAN`/`VCAN` managers |
| `Vehicle.exe` | A | 405 386 | VCAN message dispatcher: subscribes to 17 vehicle frames, keeps the backups and the logging key strings |
| `VehicleCCWrapper.dll` | A | 5 437 | IPC shim `VCL_WRAP_*` between the CC screens and `Vehicle.exe` |
| `VehicleMainCC.dll` | A | 28 442 | vehicle settings screen (COM control) |
| `DriveComputerCC.dll` | A | 65 020 | drive computer: electric economy, reachable distance, consumption, trip |
| `EvTimerCC.dll` | A | 80 502 | charge timer / climate timer screen |
| `EvNoticeCC.dll` | A | 295 863 | EV notice/popup host (charging, autonomy) |
| `HvacCC.dll` | A | 35 267 | climate screen (driver/outside temperature, fan) |
| `ComfortCC.dll` | A | 37 750 | light/wiper comfort settings |

Code size is the sum of the uncompressed executable `vsize`s
(`tools/cerom.py sections`).

## 2. Transport

`CAN.dll` (build B) exports `CAN_Open`, `CAN_Read`, `CAN_Write`,
`CAN_IOControl`, `CAN_Seek`, `CAN_Init`, `CAN_Deinit`, `CAN_PowerUp`,
`CAN_PowerDown`; its strings name an `MCAN` manager (powertrain) and a `VCAN`
manager (vehicle body), with baud-rate and `GDIC_DOCAN2`/`GDIC_MCAN2` debug
strings. It is a stream driver on `UAT3:` (C-6413): **the SH-4 is not the CAN
node** — the VCAN sub-microcontroller is, and the SH-4 sees decoded frames
(C-6416). No module imports `CAN.dll` directly (its clients reach it through
`CreateFile("CAN1:")`, as `Vehicle.exe`, `DiagnosisCC.dll` and `Consult.exe`
do).

## 3. Signal table

`Vehicle.exe` subscribes to 17 vehicle frames through
`VPRB_CallbackVcanMgr`; the id/name list is the block of `"N - NAME [0xID]"`
strings at VAs `0x02217f`…`0x0223ff` (sec0). The per-frame `Set …` handlers
below map a payload field to a named value. **Id and name** are VERIFIED (the
literal strings). **Unit** is quoted from a format/scale literal with its VA
when the module carries one (VERIFIED); `unknown` means the payload field is
decoded but no unit literal exists in the modules read (OBSERVED field name
only, scale not established). **Consumer** is the module whose exported
COM property or screen label names the value (OBSERVED from the property
tables; no call was executed).

| CAN id | Frame (name string) | Signal / setter | Unit · scale | Consumer |
| --- | --- | --- | --- | --- |
| `0x180` | `ECM_TorqueControl_RN1` | `RawSensor`, `MeanEffectiveTorque` | torque — unknown | `Vehicle.exe` (log) |
| `0x260` | `VCM_HMI_GeneralData4` | `TractionMTR_Consumption_Power_StatusDisplay` | power status — unknown | `DriveComputerCC` (economy bar) |
| `0x280` | `CLUSTER_BasicInfo_1` | `VehicleSpeed_CLUSTER` (copy) | km/h · `0.1[km/h]` (`0x0249dc`), also `1[km/h]` | speedometer, drive computer |
| `0x354` | `Brake_GeneralData` | `ABSMalfunction`, `ABSinRegulation` | flag | `Vehicle.exe` |
| `0x355` | `CLUSTER_BasicInfo_2` | `MarketInformation` | enum (market code) | `Vehicle.exe` |
| `0x35D` | `BCM_SystemControl` | `FrontWipingRequest`, `CloseActiveBrakeSwitch_BCM` | flag (1 bit) | wiper/brake, `ComfortCC` |
| `0x421` | `ATCVT_to_MMI_RN1` | `ATCVT_RangeIndication` | enum (gear range) | cluster |
| `0x50D` | `VCM_HMI_GeneralData1` | `BAT_LampRequest`, `CAUTION_LampRequest`, `SLOW_LampRequest`, `CauseOfSLOW_Lamp` | flag (1 bit) | warning lamps |
| `0x510` | `VCM_HMI_GeneralData2` | `AC_Consumption`, `Others_Consumption`, `VCM_BLBCHK_Status`, `ECO_Meter2`, `TractionMotor_Consumption` | consumption — unknown | `DriveComputerCC` |
| `0x54A` | `Aircon_GeneralStatus1_ITM` | `temperature unit`, `outside temperature`, `driver temperature` | °C/°F · 0.5 °C step, integer °F | `HvacCC` |
| `0x54B` | `Aircon_GeneralStatus2_ITM` | `Status of A/C system`, `Status of A/C` | flag | `HvacCC` |
| `0x5B3` | `VCM_HMI_GeneralData3` | `HiVolt_Battery_Temp`, `HiVoltBattery_Deterioration rate`, `HiVoltBattery_Real_Capacity` | temp unknown; capacity unknown | `EvNoticeCC` (battery) |
| `0x5C0` | `LBCMSG5` | `Cell_Voltage`, `Degradation_Internal_Resistance_Coefficient`, `Integrated_Current`, `Temperature`, `Temperature_Wakeup_Phase`, `High_or_Low_Voltage_Times`, `Swich_Flag` | raw (lithium-battery controller history) | `Vehicle.exe` (log) |
| `0x5C5` | `CLUSTER_GeneralStatus` | `DistanceTotalizer` (odometer) | km/m · `0.001[km]` (`0x024e00`), `0.1[m]` (`0x025db4`) | odometer, maintenance |
| `0x5EB` | `VCM_ChargeHistoryData1` | `Charge_Data_No`, `Charge_Execution_Counter`, `Charge_Cycle_Counter`, `Charge_History_Data1…8` | raw (charging history) | `EvNoticeCC` charge history |
| `0x60D` | `BCM_GeneralStatus7` | `FlashingIndicatorStatus`, `LowBeamStatus`, `HighBeamStatus`, `RearDefrostStatus` | flag | `ComfortCC`, lamps |
| `0x625` | `USM_GeneralStatus` | ultrasonic / proximity status | raw | `Vehicle.exe` |

Scaled values with a visible unit (VERIFIED by the literal at the VA):

- vehicle speed — `0.1[km/h]` at `0x0249dc`, and a separate `1[km/h]` literal
  (`(1[km/h])`) at `0x025772`; the diagnostic dump prints
  `Speed [%d (* 0.01 (km/h))]` (`0x025d70`) for a finer 0.01 km/h value and
  `Speed [%10d (* 0.1 (km/h))]` for the bus value;
- odometer — `0.001[km]` at `0x024e00`, displayed as `Odmeter [%10d (* 0.1
  (m))]` (`0x025db4`);
- acceleration — `0.01[G]` at `0x024a66`;
- heading — `Direction [%10d (* 0.1 (deg))]`;
- latitude/longitude — `1/512 sec` (`/ 512 (sec)`).

Temperature has no multiply constant: the unit is a mode, and the value is a
half-degree count. `TempUnit=C,DrTemp=26.0` / `TempUnit=C,DrTemp=25.5` and
`TempUnit=F,DrTemp=76` / `TempUnit=F,DrTemp=75` (log format strings at
`0x018d4e` … `0x018c7e`) show °C printed with one decimal (a 0.5 °C step) and
°F as an integer, i.e. the rounding is chosen by the unit at format time.

## 4. The drive computer

`DriveComputerCC.dll` exposes one COM control, `DriveComputerCC.DrvComCtrl`
(CLSID `{20CA86F4-…}`), with these properties (name strings in sec3, VA in
parentheses):

| Property | VA | Meaning |
| --- | --- | --- |
| `ElectricEconomyInst` | `0x025250e8` | instantaneous economy (the meter bar) |
| `ElectricEconomyAvgGraph` | `0x0252513c` | 30-slot history for the bar graph |
| `ElectricEconomyAvgValue` | `0x02525160` | the numeric average economy shown on screen |
| `ReachableDistance` | `0x02525184` | remaining range |
| `ElectricEconomyHistory` | `0x025251a4` | stored trip history |
| `FuelEconomyAvg` | `0x025251dc` | the fuel-economy variant (US/other markets) |

Its change notifications name the same set (`NotifyDrvcomChangeEleInst`,
`…EleAvg`, `…ReachableDist`, `…MoterConsumption`, `…AcConsumption`,
`…OthersConsumption`, `…AcStatusFluctuation`, `…Staus`). The EV screen that
displays them is `InfoBarCC.dll` / `EvNoticeCC.dll`: labels
`INF_EECONOMY_ECONOMY` (economy screen), `INF_ECOMSUMPTION_ELECTRIC_USAGE`
(consumption breakdown), `INF_AUTONOMY_DRIVING_RANGE_MAP` (range map), plus
`POP_EV_INF_EECONOMY_AVG_RESET_*` (reset the average).

### Numeric path

The economy value is held in `Vehicle.exe` as an integer:
`VCL_DrvComBackUpInfo->electric_economy_avg` and
`…electric_economy_history[%d]` are `%d`, and `…avg_calc_consume` /
`…avg_calc_mileage` are the running sums (format strings at `0x011c7a`
(`electric_economy_avg`) and `0x011c64` (`history[%d]`), `0x011bb8`
(`avg_calc_consume`)). So the value the display receives is an integer, not
a finer float.

The display scaling happens in `DriveComputerCC.dll` in
`fn 0x02518f58` (EU 2011; function start confirmed by
`tools/nk_decomp.py pdata`), a float formatter that prints with `%2.1f` (the
module's only `%f` format string is `%2.1f` at `0x02511ed0`). It is the
formatter reached from the drive-computer getter table at `0x02511c50` /
`0x02511d6c` (its pointer sits by `0x02518da0`, `0x02518e7c`, `0x02519160`…
in the code-pointer table at `0x02511d6c`). Inside that function:

- `0x02519072` — `fdiv FR6,FR4` (halfword `0xf463`): the incoming value is
  divided by the property scale factor, producing the value that is printed;
  **this is the VA where the energy-economy value is scaled for display**;
- `0x02519080` — `fmul FR6,FR4` (halfword `0xf462`): a second factor (unit
  conversion) applied in the metric/imperial branch;
- `0x0251909c` loads the double constant `99.9` from `0x02519148` (loaded once
  by `mov.l @(disp,pc)`; the only such load of this pool word), a display
  clamp;
- `0x02519138` holds the double `1.6093` (km→mile) in the same pool; it is
  **not** referenced by `fn 0x02518f58` (a full halfword scan for
  `mov.l @(disp,pc)` targeting it finds no load), so the mile conversion is
  applied by a sibling formatter, not here.

Consequence for the task's question: because `electric_economy_avg` arrives
as an integer (`%d`) and is converted to float only at display time
(`float FPUL,FR0` at `0x02518fe4`/`0x02519000`), the one-decimal `%2.1f`
display is **derived from an integer**, i.e. the coarse value arrives already
rounded and the display adds no finer data. A finer economy display would need
a change in `Vehicle.exe`'s stored value (the `%d` backup fields), not only a
UI change. This is the "coarse arrives rounded" branch, marked HYPOTHESIS
pending an execution check (L3/L4).

## 5. Climate and comfort

- `HvacCC.dll` COM properties: `DriverTemperatureInteger`,
  `DriverTemperatureFloat`, `FanSpeed`, `TemperatureUnit` (sec3 VAs
  `0x0253cf54`, `0x0253cf88`, `0x0253cfc4`, `0x0253cff0`). Input frames
  `0x54A`/`0x54B` (`Aircon_GeneralStatus1/2_ITM`).
- `ComfortCC.dll` properties `IsLightSensitivity`, `LightSensitivity`,
  `IsLightOffDelay`, `LightOffDelay`, `IsWiperInterval`, `WiperInterval`;
  inputs `0x60D` (`FlashingIndicatorStatus`, `HighBeamStatus`…) and `0x35D`
  (`FrontWipingRequest`).
- `EvTimerCC.dll` charge/climate timer: properties `StartTime`, `WeekInfo`,
  `EndTime`, `StopCapacity` (notification names `NotifyChargeUpdateStartTime`,
  `…WeekInfo`, `…EndTime`, `…StopCapacity`).

## 6. What could be changed

- A finer economy display (`ElectricEconomyAvgValue`) needs the stored
  `electric_economy_avg` widened from the `%d` integer in `Vehicle.exe`
  (`0x011c7a`) and a matching formatter change in `DriveComputerCC`
  (`fn 0x02518f58`), not just a UI edit.
- The display clamp `99.9` (`0x02519148`) and the divide/multiply in
  `fn 0x02518f58` are constants — a data/code patch, not a screen setting.
- Decoding a new CAN frame is a `Vehicle.exe` change: it hard-codes the 17
  ids at `0x02217f`…`0x0223ff` and one `Set …` handler per field; the wire
  itself is decoded by the VCAN microcontroller (C-6416), so a new frame must
  be enabled there first.

## 7. Differences between builds

Only EU 2011 build A was analysed here. `CAN.dll` lives in build B
(`0x3e00200`); the US/EU2014 screens are a separate comparison (M1.36/M1.37)
and are not in this page.
