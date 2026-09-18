# Open Sail Tracker

Kostengünstiges Live-Tracking-System für kleine Segelregatten mit GNSS- und LTE-Trackern auf Basis des LILYGO T-SIM7670G-S3 Standard (H802).

Das Projekt ist unabhängig und derzeit kein offizielles Angebot eines Bootsbauers oder einer Klassenvereinigung.

## Status

Der erste CoAP-Durchstich ist funktionsfähig:

- kleine Positionsmeldung alle fünf Sekunden
- großes Statuspaket alle 60 Sekunden
- CoAP über UDP an `sailtracker.wyraz.de:39001`
- Python-Backend dekodiert und protokolliert beide Pakettypen
- Kubernetes-Deployment und Docker-Image sind funktionsfähig
- dekodierte Telemetrie kann vollständig in VictoriaMetrics geschrieben werden
- Firmware wurde auf dem H802 gebaut, geflasht und über LTE Ende-zu-Ende getestet

Die aktuelle Teststufe ist absichtlich noch unverschlüsselt und nicht authentisiert. Sie darf nicht produktiv eingesetzt werden. Verschlüsselte und authentisierte Backend-Kommunikation ist der erste Punkt im [Backlog](backlog.md).

Die maßgebliche technische Definition steht in [PROTOCOL.md](PROTOCOL.md).

## Repository-Struktur

- `firmware/` – ESP32-S3-/SIM7670G-Trackerfirmware mit PlatformIO und Arduino
- `backend/` – Python-CoAP-Listener, Tests und Dockerfile
- `protocol/` – ergänzende Protokoll- und Testdokumentation
- `deploy/` – systemd-Unit und Helm-Chart
- `docs/` – Architekturentscheidungen und Projektdokumentation
- `tools/` – Diagnose- und Entwicklungswerkzeuge
- `.github/workflows/` – CI und Veröffentlichung des Backend-Images

Firmware, Backend, Webanwendung und mechanische Konstruktion bleiben in einem Monorepository, damit Protokoll- und Schnittstellenänderungen gemeinsam versioniert werden können.

## Backend lokal testen

```bash
PYTHONPATH=backend/src python -m unittest discover -s backend/tests -v
docker build -t open-sail-tracker-backend:local backend
docker run --rm -p 39001:39001/udp open-sail-tracker-backend:local
```

## Firmware bauen und flashen

```bash
cd firmware
pio run
pio run -t upload --upload-port /dev/ttyACM0
```

## Repository

```text
git@github.com:micw/open-sail-tracker.git
```
