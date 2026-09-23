# H802 firmware

Firmware proof of concept for the LILYGO T-SIM7670G-S3 Standard (H802).

## Current behavior

- uses the H802 pin assignment without an additional board library;
- starts the SIM7670G modem and waits for LTE registration;
- configures APN `iotde.telefonica.com`;
- enables the integrated GNSS receiver in multi-constellation mode and powers the active GNSS antenna through SIM7670G GPIO1 as defined by LILYGO's `LILYGO_SIM7670G_S3_STAN` profile;
- reads position, speed, course, satellites, and HDOP through `AT+CGNSSINFO`;
- sends a 26-byte position packet every second as `NON POST /v1/position`;
- sends a 58-byte status packet at boot and every ten seconds as `CON POST /v1/status`;
- samples RSSI through `AT+CSQ` for every status packet;
- resolves `sailtracker.wyraz.de` through the modem with `AT+CDNSGIP` and caches the IPv4 address;
- uses CoAP over UDP to the resolved address on port `39001`;
- represents an unknown position with `INT32_MIN` and validity flags;
- measures battery voltage through the GPIO8 voltage divider and keeps the separately queried `AT+CBC` modem-supply value out of the battery field;
- tracks the lowest battery sample between status packets;
- includes a device ID, random boot ID, and shared packet sequence number;
- reopens the modem UDP socket and resolves the hostname again after a send failure;
- tracks continuously for regatta use until 30 measurement cycles at or below 3.4 V have confirmed an empty/reserve battery state, then enters an indefinite minimum-power state.

## Low-battery shutdown

The firmware uses only the ESP32 GPIO8 battery ADC for the local protection decision. `AT+CBC` is retained as a separately logged modem-supply diagnostic and is never substituted for an invalid ADC value. A low reading must be observed in 30 measurement cycles before shutdown; readings at or above 3.45 V clear the confirmation counter.

Once low battery is confirmed, the firmware:

1. disables GNSS and its active antenna supply;
2. closes the UDP socket and modem network service;
3. requests an orderly modem shutdown with `AT+CPOF`;
4. waits ten seconds and verifies that the modem no longer responds, without applying a potentially ambiguous `PWRKEY` pulse;
5. ends the modem UART and places connected ESP32 pins in non-driving states;
6. enables the H802 converter's power-save mode through GPIO42;
7. holds the relevant control outputs low, powers down unused RTC memory, and enters ESP32 deep sleep without a wake-up source.

The board remains asleep until it is reset or power-cycled. If the battery path was previously latched off after deep discharge, a brief ESP-USB connection may still be required to reactivate it before battery-only operation.

The wire format is defined in [PROTOCOL.md](../PROTOCOL.md).
The power path and battery measurements are documented in [H802-POWER.md](../docs/hardware/H802-POWER.md).

## Build and flash

```bash
pio run
pio run -t upload --upload-port /dev/ttyACM0
pio device monitor --port /dev/ttyACM0 --baud 115200
```

`/dev/ttyACM0` is the ESP32 USB port in the current development setup. The user needs write access through the `uucp` group or an appropriate udev rule or ACL.

## Current limitations

- no encryption or sender authentication;
- no local buffer or backfill;
- confirmable status messages are not retransmitted yet;
- the firmware does not parse the status ACK yet;
- detailed radio measurements still use sentinel values;
- short LTE voltage dips are not guaranteed to be captured by the current periodic ADC sampling;
- `modem_supply_mv`, battery measurement validity, and the local battery state are logged locally but not yet added to the wire protocol;
- the 3.4 V shutdown threshold and 30-cycle confirmation policy still require validation with the target MJ1 cell and cold-temperature tests;
- no watchdog or complete recovery state machine;
- blocking AT commands;
- server hostname and APN are compiled into the firmware;
