#!/usr/bin/env bash
# Default: one human and two bots, all shown in ONE terminal.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mode=demo
humans=false
watch=false
seed=()
original_args=("$@")
while (($#)); do
    case "$1" in
        --class) mode=class ;;
        --demo) mode=demo ;;
        --humans) humans=true ;;
        --watch) watch=true ;;
        --seed)
            [[ ${2:-} =~ ^[0-9]+$ ]] || { echo '--seed needs a nonnegative integer.' >&2; exit 1; }
            seed=(--seed "$2"); shift ;;
        -h|--help)
            cat <<'EOF'
Usage: ./launch_game.sh [--class] [--humans | --watch] [--seed N]
  Default     You are player1; two random bots play player2 and player3.
  --watch     Watch three bots play, with one board in your terminal.
  --humans    Open three labeled tmux panes for three human players.
  --class     Use three distinct Linux player users (needs sudo ./setup.sh).
  --seed N    Repeatable bot choices for testing.
No flags are needed to start playing. Type drop 4, or just 4, on your turn.
EOF
            exit 0 ;;
        *) echo "Unknown option: $1. Use --help." >&2; exit 1 ;;
    esac
    shift
done
if $humans && $watch; then echo 'Choose either --humans or --watch.' >&2; exit 1; fi
if [[ $mode == class && $EUID != 0 ]]; then
    exec sudo -- bash "$project_dir/launch_game.sh" "${original_args[@]}"
fi
command -v python3 >/dev/null || { echo 'Install Python: sudo apt install python3' >&2; exit 1; }
if $humans; then
    command -v tmux >/dev/null || { echo 'Install tmux: sudo apt install tmux' >&2; exit 1; }
fi
if [[ $mode == class ]]; then
    project_dir=/opt/connect4-mayhem
    [[ -r $project_dir/client.py ]] || { echo 'Run sudo ./setup.sh first.' >&2; exit 1; }
    for account in c4-referee c4-player1 c4-player2 c4-player3; do
        id "$account" >/dev/null 2>&1 || { echo "Missing $account. Run sudo ./setup.sh." >&2; exit 1; }
    done
fi

runtime=$(mktemp -d /tmp/connect4-mayhem.XXXXXX)
socket=$runtime/game.sock
session=connect4-${runtime##*.}
mux=(tmux -L connect4-mayhem)
pids=()
cleanup() {
    if $humans; then "${mux[@]}" kill-session -t "=$session" 2>/dev/null || true; fi
    for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
    for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null || true; done
    rm -f -- "$socket" "$runtime/referee.log" "$runtime/player2.log" "$runtime/player3.log"
    rmdir -- "$runtime" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ $mode == class ]]; then
    chown c4-referee:connect4 "$runtime"
    chmod 2750 "$runtime"
fi
server=(python3 -u "$project_dir/server.py" --socket "$socket")
if [[ $mode == class ]]; then
    server=(runuser -u c4-referee -- "${server[@]}")
else
    server+=(--demo)
fi
"${server[@]}" > "$runtime/referee.log" 2>&1 &
pids+=("$!")
ready=false
for attempt in {1..100}; do
    if [[ -S $socket ]]; then ready=true; break; fi
    kill -0 "${pids[0]}" 2>/dev/null || break
    sleep 0.05
done
if ! $ready; then cat "$runtime/referee.log" >&2; exit 1; fi

for number in 2 3 1; do
    client=(python3 -u "$project_dir/client.py" --socket "$socket" --player "player$number")
    if ((${#seed[@]})); then client+=(--seed "$((10#${seed[1]} + number))"); fi
    if ! $humans && { ((number != 1)) || $watch; }; then client+=(--bot); fi
    if [[ $mode == class ]]; then client=(runuser -u "c4-player$number" -- "${client[@]}"); fi
    if $humans; then
        printf -v command '%q ' "${client[@]}"
        if ((number == 2)); then
            pane=$("${mux[@]}" new-session -d -s "$session" -n players -x 180 -y 32 -P -F '#{pane_id}')
            "${mux[@]}" set-option -t "$session" remain-on-exit on
            "${mux[@]}" set-option -t "$session" mouse on
            "${mux[@]}" set-option -t "$session" pane-border-status top
            "${mux[@]}" set-option -t "$session" pane-border-format ' #{pane_title} '
        else
            pane=$("${mux[@]}" split-window -d -t "$pane" -P -F '#{pane_id}')
        fi
        "${mux[@]}" select-pane -t "$pane" -T "player$number"
        "${mux[@]}" send-keys -t "$pane" "exec $command" Enter
        "${mux[@]}" select-layout -t "$session" even-horizontal >/dev/null
    elif ((number != 1)); then
        "${client[@]}" > "$runtime/player$number.log" 2>&1 &
        pids+=("$!")
    else
        if $watch; then
            echo 'Watching three random bots on one board.'
        else
            echo 'One board, three players. You are X; bots are O and @.'
        fi
        "${client[@]}"
    fi
done
if $humans; then
    # Put player1 at the left, followed by player2 and player3.
    "${mux[@]}" swap-pane -s "$pane" -t "$session:players.0"
    "${mux[@]}" swap-pane -s "$session:players.1" -t "$session:players.2"
    "${mux[@]}" select-pane -t "$session:players.0"
    echo 'Click a pane. Ctrl-b z zooms. Ctrl-b d exits and stops this match.'
    "${mux[@]}" attach-session -t "$session"
fi
