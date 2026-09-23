# H802 power and battery hardware

Status: verified from the H802 schematic, LILYGO reference firmware, and measurements on the project board on 2026-09-18.

## Board variant

The board is the LILYGO T-SIM7670G-S3 Standard, hardware identifier H802, using the `LILYGO_SIM7670G_S3_STAN` pin definition. Results from other LILYGO modem boards do not automatically apply to this variant.

## No AXP power-management IC

The H802 schematic contains no AXP192, AXP2101, or other AXP-family PMIC. An AXP driver is therefore not applicable to this board. The QWIIC I²C bus on GPIO3/GPIO2 is exposed for peripherals but is not the battery-management interface.

The board has no hardware coulomb counter and cannot directly measure remaining charge in mAh. State of charge must initially be estimated from battery voltage and a battery-specific discharge curve.

## Power-path components

The schematic identifies these relevant components:

- `CN3165`: single-cell lithium battery charger;
- `SGM41101-430M46YTDI6G/TR`: battery protection device;
- `TPS63020DSJR`: main buck-boost converter producing the board supply;
- `SY8089A1AAC`: 3.3 V regulator;
- `XC6206P182MR` and `SGM38121`: additional low-voltage rails;
- discrete resistor dividers for battery and solar-voltage ADC inputs.

Published electrical limits and protection thresholds:

- USB/VBUS input: 4.5–5.5 V;
- solar input: 5–6 V;
- maximum USB/solar charge current: 500 mA;
- nominal single-cell battery voltage: 3.7 V;
- documented battery socket range: 3.4–4.3 V;
- protection over-voltage threshold: 4.30 V;
- protection under-voltage threshold: 2.4 V;
- over-charge current protection: 3.6 A;
- over-discharge current protection: 4.6 A;
- short-circuit threshold: twice 4.6 A.

The solar JST connector is a charger input, not a general battery connector and not a standalone board supply. An external battery connected to `VBAT` bypasses the mechanical battery switch.

## Confirmed level-shifter deep-sleep issue

[LILYGO issue #529](https://github.com/Xinyuan-LILYGO/LilyGo-Modem-Series/issues/529) documents a hardware defect or unsuitable component choice in the SIM7670G-S3 Standard level-conversion path. After the modem has been initialized and powered down, the complete board draws approximately 1 mA in LILYGO's own repeated measurement; approximately 140 µA is reached only when the modem is physically disconnected. The maintainer explicitly states that the problem cannot be repaired in software.

LILYGO identifies the level-conversion device at board position `U8` as the source. The documented repair requires removing the battery holder and replacing `U8` with an `RS0108YTQC20` using hot-air rework. This is an advanced board repair and should not be attempted without suitable equipment and experience. The project board measures approximately 2.15 mA with both the project shutdown sequence and LILYGO's unchanged `DeepSleep` example, which is consistent with the same class of hardware issue even though its exact current is higher than the approximately 1 mA reported by LILYGO.

The top marking observed on the project board appears to read `S0208` with a second line similar to `1618`. This matches the shared LILYGO Standard-series schematic, which specifies `RS0208YTQC20` at position `U8`; the second line is likely a lot or date code rather than the device type. Issue #529 explicitly instructs replacing this `RS0208` family device with `RS0108YTQC20`. The observed marking therefore strongly identifies the project board as carrying the component population implicated by LILYGO.

The previously published H802 average of 147 µA was measured with a VICTOR 8246A. In issue #529, the maintainer states that these earlier results have been overturned and need to be retested. Therefore 147 µA must no longer be treated as a guaranteed current for an unrepaired production board.

An additional test explicitly drove GPIO42 low and held it throughout deep sleep to force the board converter's power-save mode. The current remained approximately 2 mA. Raising the supply toward 4.2 V also changed current only in proportion to voltage while input power stayed near 8.3 mW. These tests further isolate the level-conversion path from firmware sequencing and converter-mode configuration.

The issue does not describe `U8` as completely non-functional. It is more precise to classify the condition as a hardware nonconformity, excessive leakage, or unsuitable component population: digital communication may continue to work while the advertised board-level deep-sleep current is missed. In a direct response to the project report, LILYGO confirmed that using `RS0208YTQC20` instead of `RS0108YTQC20` is a known production issue and that boards carrying `RS0208` are affected. The chip marking is the stated identification method; current purchases from the official LILYGO store are reported to ship with `RS0108`. LILYGO also confirmed that replacement with `RS0108YTQC20` is the complete fix and directed affected customers to the place of purchase for replacement.

No board-level rework will be attempted on the project unit. Written confirmation has now been obtained from LILYGO; the next step is a warranty claim to the retailer with the manufacturer response, measurement data, photographs, and issue #529 as evidence. The battery holder and `U8` must remain untouched so the board stays in its delivered condition for the claim.

## No software-controlled full shutdown or VBUS detection

The LILYGO issue tracker contains two directly relevant questions on closely related non-PMIC boards:

- [Issue #420: detect battery versus VBUS power](https://github.com/Xinyuan-LILYGO/LilyGo-Modem-Series/issues/420): LILYGO states that the board has no built-in method or PMIC register for reading VBUS presence. The proposed solution is an external resistor divider from VBUS to an ESP32 input.
- [Issue #472: cut all power until VBUS returns](https://github.com/Xinyuan-LILYGO/LilyGo-Modem-Series/issues/472): LILYGO states that the existing hardware cannot fully shut itself down from software and remain off until 5 V returns. The suggested solution is external switching hardware.
- [Issue #484: wake immediately when USB is connected](https://github.com/Xinyuan-LILYGO/LilyGo-Modem-Series/issues/484): LILYGO states that there is no native USB-plug wake function. Immediate wake requires routing divided VBUS to a suitable RTC-capable GPIO; otherwise firmware must wake periodically and poll.

These issues discuss other LILYGO modem-board revisions, but their conclusions agree with the H802 schematic: the H802 has no programmable PMIC, no charger-status register available to the ESP32, and no software-controlled switch that disconnects the complete board from the cell. GPIO42 only controls the main converter's power-save mode. `AT+CPOF` powers down the modem but does not disconnect the board, and the mechanical battery switch cannot be operated by firmware.

The H802 does expose a divided solar-input measurement on GPIO18, but this indicates the solar connector rather than USB VBUS and does not provide a full-board power latch. Battery voltage or a rising-voltage heuristic is not a reliable substitute for explicit external-power detection.

The approximately 2.4 V battery-protection cutoff is the only built-in state that approaches a latched full shutdown and is reactivated by an applied charging source. It is an emergency cell-protection threshold, not a software-selectable operating cutoff. Deliberately discharging an MJ1 below its 2.50 V loaded limit to reach this state is not an acceptable normal strategy, especially because the project test observed repeated LTE attempts and voltage dips before latching.

Therefore the requirement "shut down at a safe threshold and remain fully off until charging starts" needs additional hardware on H802: a low-leakage load switch or latching power circuit with VBUS/charger wake, an external undervoltage supervisor, or a different carrier with a suitable PMIC. A normal relay is not ideal for a battery tracker unless it is a latching type; its coil consumption would otherwise defeat the low-power goal.

## GNSS antenna power control

The active GNSS antenna must be powered through a GPIO of the SIM7670G modem before enabling the GNSS engine. For the H802 `LILYGO_SIM7670G_S3_STAN` profile, both the pinned LILYGO reference source used by this project and the current upstream `utilities.h` define modem GPIO1 with active-high level:

```text
AT+CGDRT=1,1
AT+CGSETV=1,1
AT+CGNSSPWR=1
AT+CGNSSMODE=15
```

[LILYGO issue #477](https://github.com/Xinyuan-LILYGO/LilyGo-Modem-Series/issues/477) reports a superficially similar no-fix problem on a unit identified as P/N `S2-10D1Y-Z32W4`, but its successful workaround uses modem GPIO4. This conflicts with LILYGO's `LILYGO_SIM7670G_S3_STAN` definition and may represent a different hardware or modem revision. The project board has repeatedly produced valid `AT+CGNSSINFO` fixes with 15–32 satellites while using GPIO1, so GPIO1 remains the verified setting for this board. GPIO4 must not be driven without first confirming the exact hardware revision.

The tracker deliberately uses `AT+CGNSSINFO` polling rather than continuous NMEA streaming because LTE and GNSS share the modem UART. The maintainer response in issue #477 confirms that both polling and NMEA output are valid when antenna power is enabled. To avoid stale continuous NMEA output interfering with AT responses, firmware startup first sends `AT+CGNSSTST=0` and disables GNSS, performs LTE initialization, and then enables antenna power, GNSS, and multi-constellation mode. `AT+SIMCOMATI` is logged during startup so the modem firmware revision can be captured during a diagnostic serial run.

## ESP32 battery measurement

Battery voltage is connected through a nominal 100 kΩ / 100 kΩ divider to ESP32-S3 GPIO8. The measured ADC voltage is therefore multiplied by two:

```text
battery_mv = average(analogReadMilliVolts(GPIO8)) * 2
```

Firmware configuration:

- 12-bit ADC resolution;
- 11 dB attenuation;
- 32 samples per reading;
- approximately 2 ms between samples;
- accepted result range: 2500–5000 mV.

An invalid reading uses the protocol sentinel `UINT16_MAX`.

A live measurement while ESP-USB was connected produced:

```text
ESP32 GPIO8 ADC: 3776 mV
```

The result is plausible for the installed single-cell battery. It still requires comparison with a multimeter and a battery-only measurement, because LILYGO warns that battery readings can be unreliable while USB power is connected.

## SIM7670G measurement

The board also routes the battery/power rail to SIM7670G GPIO8 through a separate divider. The modem exposes this as:

```text
AT+CBC
+CBC: 3.563V
```

During the same diagnostic run:

```text
ESP32 GPIO8 ADC: 3776 mV
SIM7670G AT+CBC: 3563 mV
Difference:        213 mV
```

`AT+CBC` is documented by SIMCom as the module power-supply voltage. It is useful as a plausibility and brownout indicator, but it is not interchangeable with the battery-terminal measurement. The firmware therefore uses the ESP32 ADC as the primary battery value and only falls back to `AT+CBC` when the ADC result is invalid.

## Firmware behavior

The tracker now:

1. samples GPIO8 before every one-second transmission cycle;
2. averages 32 calibrated millivolt readings and applies the divider factor;
3. asks the modem for `AT+CBC` before each ten-second status packet;
4. selects the ESP32 ADC value when valid, otherwise the modem value;
5. tracks the lowest selected sample since the previous successful status packet;
6. sends `battery_mv` and `battery_min_mv` in the status packet.

A production status packet after the diagnostic changes reported:

```text
battery_mv:     3778 mV
battery_min_mv: 3778 mV
```

The current minimum tracking samples around one-second application cycles. It does not yet guarantee capture of the shortest LTE current peak because modem transmission and AT-command handling are blocking. Capturing peak sag requires an asynchronous ADC task, continuous ADC mode, or external measurement equipment.

## Remaining verification

When testing battery behavior further:

1. measure the battery directly with a calibrated multimeter;
2. compare it with GPIO8 while ESP-USB is connected;
3. disconnect ESP-USB and repeat while powered only from the battery;
4. compare both measurements with `AT+CBC` at idle and during LTE transmission;
5. characterize the voltage curve from full charge to the chosen shutdown threshold;
6. calibrate the ADC divider factor if the board shows a systematic offset;
7. decide whether four coarse battery states are more honest than a percentage display.

Do not infer remaining capacity directly from one loaded voltage sample. LTE bursts, temperature, battery chemistry, cell age, and recovery after load all affect the reading.
