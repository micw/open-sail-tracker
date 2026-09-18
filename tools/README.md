# Development tools

## Legacy raw-UDP receiver

[`udp_receiver.py`](udp_receiver.py) decodes the 26-byte position payload when it is sent directly as a UDP datagram. It was used for the first modem-to-server transport test and is retained as a diagnostic tool.

```bash
python3 tools/udp_receiver.py --port 39001
```

It is not compatible with the current CoAP envelope. Use the backend in [`backend/`](../backend/) for the current protocol.

## Test server

UDP port `39001` is open persistently on `vpsprod2.wyraz.de`. The current listener is the regular service `open-sail-tracker-backend.service`:

```bash
systemctl status open-sail-tracker-backend.service
journalctl -u open-sail-tracker-backend.service -f
```

The retired transient service `openskifftracker-udp-poc.service` is no longer used.
