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

1. samples GPIO8 before every five-second transmission cycle;
2. averages 32 calibrated millivolt readings and applies the divider factor;
3. asks the modem for `AT+CBC` before each 60-second status packet;
4. selects the ESP32 ADC value when valid, otherwise the modem value;
5. tracks the lowest selected sample since the previous successful status packet;
6. sends `battery_mv` and `battery_min_mv` in the status packet.

A production status packet after the diagnostic changes reported:

```text
battery_mv:     3778 mV
battery_min_mv: 3778 mV
```

The current minimum tracking samples around five-second application cycles. It does not yet guarantee capture of the shortest LTE current peak because modem transmission and AT-command handling are blocking. Capturing peak sag requires an asynchronous ADC task, continuous ADC mode, or external measurement equipment.

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
