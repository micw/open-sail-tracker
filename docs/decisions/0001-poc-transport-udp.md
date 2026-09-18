# ADR 0001: Plain UDP für den ersten Durchstich

- Status: angenommen für den PoC
- Datum: 18. September 2026

## Entscheidung

Der erste Ende-zu-Ende-Durchstich verwendet Plain UDP über den normalen öffentlichen Mobilfunkzugang. Der Tracker sendet alle fünf Sekunden ein festes 26-Byte-Positionspaket an `vpsprod2.wyraz.de:39001/UDP`.

Es gibt zunächst keine Verschlüsselung, Authentisierung, Empfangsbestätigung oder Nachlieferung. Das Paket enthält keine SIM-Kennung und keine Namen. Transportverluste werden anhand von `boot_id` und `seq` sichtbar.

## Gründe

- minimaler Modem- und Protokollaufwand
- direkter SIM7670G-Socket über `AT+NETOPEN`, `AT+CIPOPEN` und `AT+CIPSEND`
- kein PPPoS, Broker, TLS- oder HTTP-Stack für den ersten Test
- verlorene Livepositionen blockieren spätere Positionen nicht
- Daten des begrenzten PoC werden nicht als geheim eingestuft

## Verifikation

Der Durchstich wurde am 18. September 2026 nachgewiesen:

1. Host-Smoke-Test an UDP/39001 erfolgreich.
2. ASCII-Datagramm direkt über den SIM7670G-AT-Port erfolgreich; beobachtete Mobilfunk-Quelladresse `46.114.226.20`.
3. PoC-Firmware auf den H802 geflasht.
4. Binäre Pakete mit `device_id=4c939764`, fortlaufender Sequenz und wechselnder `boot_id` nach Neustart im Abstand von ungefähr fünf Sekunden empfangen und dekodiert.
5. GNSS war aktiv, hatte am Testplatz im Gebäude aber noch keinen Fix. Die Pakete enthielten korrekt `POSITION_KNOWN=0`, `GNSS_ON=1` und beide Koordinaten als `INT32_MIN`.

## Konsequenzen

Der öffentliche UDP-Port akzeptiert auch fremde und gefälschte Datagramme. Vor einem produktiven Einsatz sind mindestens Rate-Limit, Monitoring, Geräteauthentisierung und Replay-Schutz neu zu entscheiden. Die Version 1 wird nicht nachträglich als sicher bezeichnet.
