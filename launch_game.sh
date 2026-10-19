#!/usr/bin/env bash
# One play script: host, join by name, or play immediately against two bots.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v python3 >/dev/null || { echo 'Install Python: sudo apt install python3' >&2; exit 1; }
if (( $# > 1 )); then echo 'Usage: ./launch_game.sh [NAME | --bots]' >&2; exit 1; fi
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    echo './launch_game.sh         Host as Host; wait 30s, then fill empty seats with bots.'
    echo './launch_game.sh Alice   Join the running lobby as Alice.'
    echo './launch_game.sh --bots  Play as Host against two bots immediately.'
    exit 0
fi
socket=$(python3 -c 'import communication; print(communication.default_socket())')
if (( $# == 1 )) && [[ $1 != --bots ]]; then
    [[ $1 != -* ]] || { echo 'Unknown option. Use --help.' >&2; exit 1; }
    [[ -S $socket ]] || { echo 'No lobby running. Start ./launch_game.sh in another terminal first.' >&2; exit 1; }
    exec python3 -u client.py "$1"
fi
[[ ! -e $socket ]] || { echo 'A game socket already exists. Join with ./launch_game.sh NAME, or stop the old host first.' >&2; exit 1; }
log=$(mktemp /tmp/connect4-host.XXXXXX)
server_pid=
cleanup() {
    if [[ -n $server_pid ]]; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    rm -f -- "$log"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
options=(--demo --bots)
if [[ ${1:-} == --bots ]]; then
    options+=(--solo)
    echo 'You are Host. Starting with two bots.'
else
    echo 'You are Host. Others have 30 seconds to join: ./launch_game.sh THEIR-NAME'
    echo 'Any empty seats will become bots when the timer expires.'
fi
python3 -u server.py "${options[@]}" > "$log" 2>&1 &
server_pid=$!
ready=false
for attempt in {1..100}; do
    kill -0 "$server_pid" 2>/dev/null || break
    # Check this referee's log, not just the shared socket pathname: another
    # host could have won a simultaneous start. Never join their game as Host.
    if grep -q '^Lobby open' "$log"; then ready=true; break; fi
    sleep 0.05
done
if ! $ready; then cat "$log" >&2; exit 1; fi
python3 -u client.py Host
