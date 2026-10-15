#!/usr/bin/env bash
# Builds the image, starts a container, checks /api/status, then runs one real ping scan through the API.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME=visualnmap-smoke
PORT=18765
URL="http://127.0.0.1:$PORT"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "==> Building image"
docker build -q -t visualnmap:smoke . >/dev/null
cleanup
echo "==> Starting container"
docker run -d --name "$NAME" --cap-add NET_RAW --cap-add NET_ADMIN -p "127.0.0.1:$PORT:8765" visualnmap:smoke >/dev/null

for _ in $(seq 1 30); do
  curl -fsS "$URL/api/status" >/dev/null 2>&1 && break
  sleep 1
done

STATUS=$(curl -fsS "$URL/api/status")
echo "status: $STATUS"
python3 -c 'import json,sys; s=json.loads(sys.argv[1]); assert s["is_root"] and s["can_raw"] and s["nmap_found"] and s["in_container"], s' "$STATUS"

curl -fsS "$URL/" | grep -q '<div id="root">' || { echo "frontend not served" >&2; exit 1; }

GATEWAY=$(docker exec "$NAME" python -c '
import socket, struct
for line in open("/proc/net/route").readlines()[1:]:
    f = line.split()
    if f[1] == "00000000":
        print(socket.inet_ntoa(struct.pack("<L", int(f[2], 16))))
        break
')
echo "==> Ping-scanning the container gateway $GATEWAY"
SCAN_ID=$(curl -fsS -X POST -H 'Content-Type: application/json' \
  -d "{\"target\": \"$GATEWAY\", \"profile_id\": \"find_devices\"}" "$URL/api/scans" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["scan_id"])')

for _ in $(seq 1 60); do
  SCAN_STATUS=$(curl -fsS "$URL/api/scans/$SCAN_ID" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  [ "$SCAN_STATUS" != "running" ] && break
  sleep 1
done
echo "scan status: $SCAN_STATUS"
[ "$SCAN_STATUS" = "completed" ] || { docker logs "$NAME" >&2; exit 1; }
echo "SMOKE TEST PASSED"
