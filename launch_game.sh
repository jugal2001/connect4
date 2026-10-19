#!/usr/bin/env bash
# Start the referee. Players join from their own terminals during the lobby.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --class ]]; then
    shift
    if [[ $EUID != 0 ]]; then exec sudo -- bash "$project_dir/launch_game.sh" --class "$@"; fi
    [[ -r /opt/connect4-mayhem/server.py ]] || { echo 'Run sudo ./setup.sh first.' >&2; exit 1; }
    install -d -o c4-referee -g connect4 -m 2750 /tmp/connect4-class
    echo 'Join from other terminals: ./join_game.sh Alice --class --slot 1 (slots 1–4)'
    exec runuser -u c4-referee -- python3 -u /opt/connect4-mayhem/server.py --socket /tmp/connect4-class/game.sock "$@"
fi
command -v python3 >/dev/null || { echo 'Install Python: sudo apt install python3' >&2; exit 1; }
echo 'Join from a NEW terminal within 30 seconds: ./join_game.sh My-name'
echo 'Use --bots to fill remaining seats with bots; --lobby-seconds N changes the wait.'
exec python3 -u "$project_dir/server.py" --demo "$@"
