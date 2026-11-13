#!/usr/bin/env bash
# Play one game against two bots on this machine: ./play.sh [NAME]
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export C4_TOKENS=$(python3 -c 'import secrets; print(",".join(secrets.token_hex(8) for _ in range(3)))')
python3 server.py --bots --bind 127.0.0.1 >/dev/null &
trap 'kill $! 2>/dev/null || true' EXIT
sleep 0.5  # let the referee start listening
C4_TOKEN=${C4_TOKENS%%,*} python3 client.py "${1:-Player}"
