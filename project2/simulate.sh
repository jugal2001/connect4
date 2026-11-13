#!/usr/bin/env bash
# Simulate four machines on one host: a referee and three players, each in its
# own network namespace, each process running as its own Linux user.
#
#   c4-p1 (10.44.1.2) ----\
#   c4-p2 (10.44.2.2) ----- c4-ref (10.44.N.1 on the link to player N)
#   c4-p3 (10.44.3.2) ----/
#
# Every link is a veth pair, so players reach the referee only over TCP/IP and
# cannot reach each other at all.
set -euo pipefail
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
app=/opt/connect4-mayhem-net
token_file=/run/connect4-sim.tokens  # root-only; stands in for handing out tokens

usage() {
    cat >&2 <<'EOF'
sudo ./simulate.sh demo                  set up and open all four machines in tmux panes
sudo ./simulate.sh up                    create accounts, namespaces and links
sudo ./simulate.sh referee [OPTIONS]     run the referee (options go to server.py)
sudo ./simulate.sh player N [NAME]       run player N (1-3)
sudo ./simulate.sh cut N                 silently drop all traffic to and from player N
sudo ./simulate.sh delay N MS            add MS milliseconds of delay each way
sudo ./simulate.sh heal N                restore player N's link
sudo ./simulate.sh down                  remove the namespaces
EOF
    exit 1
}
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
command=${1:-}
n=${2:-}
case $command in
    player|cut|delay|heal) [[ $n =~ ^[123]$ ]] || usage ;;
esac

# Apply netem options to both ends of player N's link; no options clears them.
shape() {
    local namespace device
    for end in "c4-ref c4link$n" "c4-p$n eth0"; do
        read -r namespace device <<<"$end"
        if (( $# )); then
            tc -n "$namespace" qdisc replace dev "$device" root netem "$@"
        else
            tc -n "$namespace" qdisc del dev "$device" root 2>/dev/null || true
        fi
    done
}

case $command in
up)
    missing=()
    for tool in python3 tmux ip tc runuser; do
        command -v "$tool" >/dev/null || missing+=("$tool")
    done
    if (( ${#missing[@]} )); then
        command -v apt-get >/dev/null || { echo "Install these first: ${missing[*]}" >&2; exit 1; }
        apt-get install -y python3 tmux iproute2 util-linux
    fi
    modprobe sch_netem 2>/dev/null ||
        echo "Note: cut and delay need the sch_netem module (linux-modules-extra-$(uname -r))." >&2
    "$0" down
    getent group connect4 >/dev/null || groupadd --system connect4
    for account in c4-referee c4-player1 c4-player2 c4-player3; do
        id "$account" >/dev/null 2>&1 ||
            useradd --system --no-create-home --gid connect4 --shell /usr/sbin/nologin "$account"
    done
    # The game accounts cannot read a home directory, so run from a copy.
    install -d -m 755 "$app"
    install -m 644 "$src"/communication.py "$src"/server.py "$src"/client.py "$app"/
    ip netns add c4-ref
    ip -n c4-ref link set lo up  # bots connect to the referee over loopback
    for n in 1 2 3; do
        ip netns add "c4-p$n"
        ip link add "c4link$n" netns c4-ref type veth peer name eth0 netns "c4-p$n"
        ip -n c4-ref addr add "10.44.$n.1/24" dev "c4link$n"
        ip -n "c4-p$n" addr add "10.44.$n.2/24" dev eth0
        ip -n c4-ref link set "c4link$n" up
        ip -n "c4-p$n" link set eth0 up
    done
    echo 'Ready. Start the referee, then each player in its own terminal.'
    ;;
referee)
    (umask 077; python3 -c 'import secrets; print(",".join(secrets.token_hex(8) for _ in range(3)))' > "$token_file")
    C4_TOKENS=$(<"$token_file") exec ip netns exec c4-ref runuser -u c4-referee -- python3 -u "$app/server.py" "${@:2}"
    ;;
player)
    [[ -r $token_file ]] || { echo 'Start the referee first.' >&2; exit 1; }
    C4_TOKEN=$(cut -d, -f"$n" "$token_file") exec ip netns exec "c4-p$n" runuser -u "c4-player$n" -- \
        python3 -u "$app/client.py" "${3:-Player$n}" --host "10.44.$n.1"
    ;;
tips)
    cat <<'EOF'
HOW TO PLAY  (click a player pane to type in it)
  4              drop a disc in column 4
  pop 4          remove your own bottom disc (once)
  say TEXT       message everyone
  /w NAME TEXT   whisper to one player
  look / help / quit
Break a link from another terminal:
  sudo ./simulate.sh cut 2     (undo: heal 2)

EOF
    ;;
demo)
    "$0" up
    session=c4sim
    self=$(printf '%q' "$src/simulate.sh")
    # Keep each pane open after its process exits so the result stays visible.
    after="; read -rp 'Finished. Press Enter to close the demo. '; tmux kill-session -t $session"
    tmux kill-session -t "$session" 2>/dev/null || true
    tmux new-session -d -s "$session" "$self tips; $self referee$after"
    tmux set-option -t "$session" mouse on
    for n in 1 2 3; do
        # The short sleep lets the referee write the tokens and start listening.
        tmux split-window -t "$session" "sleep 1; $self player $n$after"
        tmux select-layout -t "$session" tiled >/dev/null
    done
    exec tmux attach-session -t "$session"
    ;;
cut)
    shape loss 100%
    ;;
delay)
    [[ ${3:-} =~ ^[0-9]+$ ]] || usage
    shape delay "${3}ms"
    ;;
heal)
    shape
    ;;
down)
    for namespace in c4-p1 c4-p2 c4-p3 c4-ref; do
        ip netns del "$namespace" 2>/dev/null || true
    done
    rm -f "$token_file"
    ;;
*)
    usage
    ;;
esac
