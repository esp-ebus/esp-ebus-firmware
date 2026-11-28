<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Device Commands

`<device-ip>` is a placeholder for the adapter address (e.g. `192.168.1.9`).
All examples target the `esp32-c3-internal` build.

## Firmware update

```bash
# OTA update via espota
python3 tools/espota.py \
  -i <device-ip> \
  -p 3232 \
  -f .pio/build/esp32-c3-internal/firmware.bin \
  --debug \
  --progress

# Firmware upload via HTTP
curl -X POST \
  -H "Content-Type: application/octet-stream" \
  --data-binary @.pio/build/esp32-c3-internal/firmware.bin \
  http://<device-ip>/api/v1/upgrade/upload
```

## Command set upload

Command JSON schema: [`doc/command-schema.md`](command-schema.md).

```bash
# Command set upload (commands.json below is just an example — use your own)
curl -X POST \
  -H "Content-Type: application/json" \
  --data-binary @commands.json \
  http://<device-ip>/api/v1/app/commands/upload
```

## Health + diagnostics (GET)

```bash
curl http://<device-ip>/api/v1/health
curl http://<device-ip>/api/v1/metrics
curl http://<device-ip>/api/v1/system/heap
curl http://<device-ip>/api/v1/system/tasks
curl http://<device-ip>/api/v1/devices
curl http://<device-ip>/api/v1/app/values
curl http://<device-ip>/api/v1/app/logs
```

## Force a poll (POST, JSON)

Enqueues an immediate bus read for the key; the fresh value is
published when the read completes. Errors: `400` (malformed body or
passive command), `404` unknown key, `503` bus queue full.

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"key":"01"}' \
  http://<device-ip>/api/v1/app/values/read
```

## Write a value (POST, JSON)

Scalar `value` for single-field commands, object `value` for
multi-field ones (all non-`ign` fields required; `ign`/`ign_*` fillers
auto-pad with 0). Full rules: [`doc/api.md`](api.md). Command schema:
[`doc/command-schema.md`](command-schema.md). `503` means the bus queue
is full — nothing was sent; a newer write for the same key supersedes
an earlier pending one.

```bash
# single-field
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"key":"42","value":55}' \
  http://<device-ip>/api/v1/app/values/write

# multi-field — one-shot full payload, never a partial update
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"key":"42","value":{"value":55}}' \
  http://<device-ip>/api/v1/app/values/write
```

## Bus device scan (POST, empty body)

```bash
curl -X POST \
  http://<device-ip>/api/v1/devices/scan
```

## Breaker + metrics reset (POST, empty body)

```bash
curl -X POST \
  http://<device-ip>/api/v1/metrics/breaker/reset

curl -X POST \
  http://<device-ip>/api/v1/metrics/reset
```

## WiFi scan (POST, empty body)

```bash
curl -X POST \
  http://<device-ip>/api/v1/network/wifi/scan
```

## Restart (POST, empty body)

```bash
curl -X POST \
  http://<device-ip>/restart
```
