# H802 firmware

Firmware proof of concept for the LILYGO T-SIM7670G-S3 Standard (H802).

## Current behavior

- uses the H802 pin assignment without an additional board library;
- starts the SIM7670G modem and waits for LTE registration;
- configures APN `iotde.telefonica.com`;
- enables the integrated GNSS receiver and active GNSS antenna supply;
- reads position, speed, course, satellites, and HDOP through `AT+CGNSSINFO`;
- sends a 26-byte position packet every second as `NON POST /v1/position`;
- sends a 58-byte status packet at boot and every ten seconds as `CON POST /v1/status`;
- samples RSSI through `AT+CSQ` for every status packet;
- resolves `sailtracker.wyraz.de` through the modem with `AT+CDNSGIP` and caches the IPv4 address;
- uses CoAP over UDP to the resolved address on port `39001`;
- represents an unknown position with `INT32_MIN` and validity flags;
- measures battery voltage through the GPIO8 voltage divider, with `AT+CBC` as a fallback;
- tracks the lowest battery sample between status packets;
- includes a device ID, random boot ID, and shared packet sequence number;
- reopens the modem UDP socket and resolves the hostname again after a send failure.

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
- no watchdog or complete recovery state machine;
- blocking AT commands;
- server hostname and APN are compiled into the firmware;
