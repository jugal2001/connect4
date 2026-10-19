#!/usr/bin/env bash
# One play script: demo modes or three separate Linux player accounts.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v python3 >/dev/null || { echo 'Install Python: sudo apt install python3' >&2; exit 1; }
class_player=
if [[ ${1:-} == --player ]]; then
    [[ $# == 2 && $2 =~ ^[123]$ ]] || { echo 'Usage: sudo ./launch_game.sh --player 1|2|3' >&2; exit 1; }
    [[ $EUID == 0 ]] || { echo 'Run with sudo so the launcher can switch Linux accounts.' >&2; exit 1; }
    command -v runuser >/dev/null || { echo 'Install runuser (the util-linux package) first.' >&2; exit 1; }
    class_player=$2
    for account in c4-referee c4-player1 c4-player2 c4-player3; do
        id "$account" >/dev/null 2>&1 || { echo 'Run sudo ./setup.sh first.' >&2; exit 1; }
        [[ $(id -gn "$account") == connect4 ]] || { echo "Account $account must belong to group connect4. Rerun setup." >&2; exit 1; }
    done
    [[ -f /opt/connect4-mayhem/server.py && -f /opt/connect4-mayhem/client.py ]] || { echo 'Run sudo ./setup.sh first.' >&2; exit 1; }
    cd /opt/connect4-mayhem
    set --
elif (( $# > 1 )); then
    echo 'Usage: ./launch_game.sh [NAME | --bots | --windows] or sudo ./launch_game.sh --player 1|2|3' >&2
    exit 1
fi
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    echo './launch_game.sh         Host as Host; wait 30s, then fill empty seats with bots.'
    echo './launch_game.sh Alice   Join the running lobby as Alice.'
    echo './launch_game.sh --bots  Play as Host against two bots immediately.'
    echo './launch_game.sh --windows  Open Player1, Player2, and Player3 in tmux panes.'
    echo 'sudo ./setup.sh             One-time setup for separate Linux accounts.'
    echo 'sudo ./launch_game.sh --player 1  Host and play as c4-player1.'
    echo 'sudo ./launch_game.sh --player 2  Join as c4-player2 (use 3 for c4-player3).'
    exit 0
fi
socket=$(python3 -c 'import communication; print(communication.default_socket())')
server_command=(python3 -u server.py)
client_command=(python3 -u client.py Host)
if [[ -n $class_player ]]; then
    socket=/run/connect4-mayhem/game.sock
    client_command=(runuser -u "c4-player$class_player" -- python3 -u client.py "Player$class_player" --socket "$socket")
    if [[ $class_player != 1 ]]; then
        [[ -S $socket ]] || { echo 'No lobby running. Start sudo ./launch_game.sh --player 1 first.' >&2; exit 1; }
        exec "${client_command[@]}"
    fi
    install -d -o c4-referee -g connect4 -m 2750 /run/connect4-mayhem
    server_command=(runuser -u c4-referee -- python3 -u server.py --socket "$socket")
fi
if [[ ${1:-} == --windows ]]; then
    command -v tmux >/dev/null || { echo 'Install tmux first: sudo apt install tmux' >&2; exit 1; }
fi
if (( $# == 1 )) && [[ $1 != --bots && $1 != --windows ]]; then
    [[ $1 != -* ]] || { echo 'Unknown option. Use --help.' >&2; exit 1; }
    [[ -S $socket ]] || { echo 'No lobby running. Start ./launch_game.sh in another terminal first.' >&2; exit 1; }
    exec python3 -u client.py "$1"
fi
[[ ! -e $socket ]] || { echo 'A game socket already exists. Join the running game or stop the old host first.' >&2; exit 1; }
log=$(mktemp /tmp/connect4-host.XXXXXX)
server_pid=
session=
cleanup() {
    if [[ -n $session ]]; then tmux kill-session -t "$session" 2>/dev/null || true; fi
    if [[ -n $server_pid ]]; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    rm -f -- "$log"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
options=(--demo)
if [[ -n $class_player ]]; then
    options=()
    echo 'You are Player1. Join from two other terminals within 30 seconds:'
    echo '  sudo ./launch_game.sh --player 2'
    echo '  sudo ./launch_game.sh --player 3'
elif [[ ${1:-} == --windows ]]; then
    echo 'Opening three players in tmux. The game starts after the 30-second lobby.'
elif [[ ${1:-} == --bots ]]; then
    options+=(--bots)
    echo 'You are Host. Starting with two bots.'
else
    echo 'You are Host. Others have 30 seconds to join: ./launch_game.sh THEIR-NAME'
    echo 'Any empty seats will become bots when the timer expires.'
fi
"${server_command[@]}" "${options[@]}" > "$log" 2>&1 &
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
if [[ ${1:-} == --windows ]]; then
    session="connect4-$$"
    first_pane=$(tmux new-session -d -P -F '#{pane_id}' -s "$session" -n Players -c "$PWD" "python3 -u client.py Player1; tmux kill-session -t $session")
    tmux set-option -t "$session" mouse on
    tmux split-window -t "$session:Players" -c "$PWD" "python3 -u client.py Player2; tmux kill-session -t $session"
    tmux split-window -t "$session:Players" -c "$PWD" "python3 -u client.py Player3; tmux kill-session -t $session"
    tmux select-layout -t "$session:Players" even-horizontal >/dev/null
    tmux select-pane -t "$first_pane"
    if [[ -n ${TMUX:-} ]]; then
        tmux switch-client -t "$session"
        wait "$server_pid"
    else
        tmux attach-session -t "$session"
    fi
    exit 0
fi
"${client_command[@]}"
