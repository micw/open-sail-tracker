# T-PCIE V1.2 with AXP2101 as an alternative tracker platform

Status: preliminary evaluation based on the published LILYGO schematic, component documentation, and prices observed or reported on 2026-09-20. No project hardware has been tested yet.

## Candidate configuration

The candidate consists of two boards:

- LILYGO T-PCIE V1.2 carrier, SKU Q416, with ESP32-WROVER, 16 MB flash, and AXP2101 PMIC;
- a T-PCIE-compatible modem daughterboard using the European SIMCom A7672E-FASE, including a SIM interface and GNSS support.

The exact AliExpress item must be checked before ordering. `A7672E-FASE` is also sold as a bare LCC/LGA modem. A bare modem cannot be inserted into the T-PCIE socket. The offer must contain the complete daughterboard with the matching card edge, mounting hole, LTE antenna connector, GNSS antenna connector, and the required GNSS circuitry.

GNSS is optional within the A7672 family. The seller's photographs and variant description must confirm that GNSS is fitted and connected; the module family name alone is insufficient.

## Indicative cost

The following prices are comparison points, not procurement guarantees:

| Item | Indicative price |
| --- | ---: |
| T-PCIE V1.2 AXP2101 carrier | EUR 18–20 |
| A7672E-FASE T-PCIE daughterboard with SIM interface, reported AliExpress price | EUR 19 |
| Candidate total before possible shipping | **EUR 37–39** |
| T-SIM7670G-S3 Standard H802 comparison price | approximately EUR 52 |

The EUR 19 A7672E offer was reported without a link and has not yet been independently verified. VAT inclusion, shipping, antennas, GNSS population, and whether the offer is a daughterboard rather than a bare modem remain open.

## Power architecture

Unlike the H802, the T-PCIE V1.2 has an AXP2101 PMIC connected to the ESP32 over I²C. The published schematic shows:

- an AXP2101 providing the ESP32 supply and controllable power rails;
- battery and USB power-path management;
- PMIC voltage, charging, fuel-gauge, interrupt, and power-button functions;
- a separate `V_MAIN` supply for the cellular daughterboard;
- ESP32 control of the modem power supply and power-key signals.

The AXP2101 system power-down voltage is configurable from 2.6 V to 3.3 V in 0.1 V steps. This is materially better than relying on the H802 battery protector's approximately 2.4 V emergency threshold. The maximum 3.3 V PMIC threshold is still lower than the desired normal shutdown voltage.

A proposed controlled shutdown sequence is:

1. detect a repeatedly confirmed battery voltage below an experimentally selected threshold, initially expected around 3.4–3.5 V under defined load;
2. stop GNSS and send a final low-battery status if the network remains usable;
3. shut the modem down through its documented command;
4. disable the modem `V_MAIN` rail;
5. request AXP2101 system shutdown;
6. retain 3.3 V as the PMIC emergency power-down threshold.

PMIC shutdown is not galvanic battery disconnection. The PMIC and wake circuitry retain a small current. Total shutdown current must be measured with the selected carrier and modem daughterboard. Wake sources also need verification: power button and USB/VBUS are expected candidates, while timed wake after a full PMIC shutdown must not be assumed.

## Compute and radio comparison

| Property | T-PCIE V1.2 candidate | Current H802 |
| --- | --- | --- |
| MCU | classic ESP32-WROVER | ESP32-S3 |
| Flash | 16 MB | 16 MB |
| Power manager | AXP2101 | no programmable PMIC |
| Cellular modem | A7672E-FASE, Europe | SIM7670G, global variant |
| Cellular class | LTE Cat 1 bis | LTE Cat 1 |
| GNSS | optional; must be verified on offered daughterboard | integrated and working |
| Construction | stacked carrier and modem boards | integrated board |
| Firmware status | not ported or tested | working proof of concept |

LTE Cat 1 bis, with nominal rates far above the tracker's requirements, is sufficient for position telemetry and firmware downloads. The European `E` radio variant is appropriate for the current German deployment but is less flexible than the global SIM7670G when used outside its supported regions.

## Advantages

- controlled PMIC shutdown instead of ESP32 deep sleep as the lowest-power software state;
- configurable 3.3 V emergency system threshold;
- PMIC battery measurement, fuel-gauge, charging, and interrupt facilities;
- separately controllable modem power;
- replaceable modem daughterboard;
- potentially lower acquisition price;
- LTE Cat 1 bis needs only one cellular receive chain.

## Disadvantages and risks

- larger and taller assembly;
- additional connector and mounting points exposed to shock, vibration, moisture, and corrosion;
- enclosure redesign required;
- older ESP32 rather than ESP32-S3;
- regional modem rather than global modem;
- GNSS is optional and seller descriptions can be ambiguous;
- new pin mapping, PMIC support, modem power sequencing, and modem command verification are required;
- actual shutdown current and wake behavior are unknown until measured;
- seller availability and exact daughterboard revision may change.

For a marine tracker, the stacked boards must be secured with screws and spacers and protected against movement and condensation. Price alone must not override mechanical reliability.

## Firmware-porting work

A board abstraction should separate common tracker logic from:

- UART and GPIO assignments;
- PMIC initialization and battery readings;
- modem rail and power-key sequencing;
- modem-specific network, socket, and GNSS commands;
- shutdown and wake behavior.

The current SIM7670G commands provide useful starting points, but every command and response format must be tested against the A7672E firmware. In particular, GNSS startup, active antenna supply, position format, socket behavior, voltage reporting, orderly power-off, and HTTP/TLS support need verification.

## Evaluation plan

Before selecting this platform:

1. verify the exact AliExpress listing and included parts;
2. verify European LTE bands against the intended operators;
3. confirm that GNSS is fitted and that an antenna is included;
4. measure LTE registration and UDP behavior with the project SIM;
5. compare GNSS time to first fix and reception with the H802;
6. measure active current, modem-off current, ESP32 deep-sleep current, and AXP2101 shutdown current;
7. test controlled shutdown at several loaded battery voltages;
8. test wake through the power button, USB, charger input, and any documented timer mechanism;
9. test behavior when the battery voltage recovers after load removal;
10. assess the stacked assembly in the intended enclosure.

## Sources

- [LILYGO T-PCIE product page](https://lilygo.cc/products/a-t-pcie)
- [LILYGO T-PCIE repository](https://github.com/Xinyuan-LilyGO/LilyGo-T-PCIE)
- [T-PCIE V1.2 schematic](https://github.com/Xinyuan-LilyGO/LilyGo-T-PCIE/blob/master/schematic/T-PCIE-V1.2.pdf)
- [SIMCom A7672X/A7670X hardware design](https://files.waveshare.com/wiki/A7670E-Cat-1-GNSS-HAT/A7672X_A7670X_Series_Hardware_Design_V1.03.pdf)
- [XPowersLib AXP2101 example](https://github.com/lewisxhe/XPowersLib/blob/master/examples/AXP2101_Example/AXP2101_Example.ino)
