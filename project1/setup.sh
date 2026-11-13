#!/usr/bin/env bash
# Install dependencies and separate Linux accounts for multiplayer games.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ $EUID == 0 ]] || { echo 'Run: sudo ./setup.sh' >&2; exit 1; }
[[ $(uname -s) == Linux ]] || { echo 'Linux is required.' >&2; exit 1; }
if ! command -v python3 >/dev/null || ! command -v tmux >/dev/null; then
    if command -v apt-get >/dev/null; then
        apt-get update
        apt-get install -y python3 tmux
    else
        echo 'Install python3 and tmux using your package manager, then rerun setup.' >&2
        exit 1
    fi
fi
getent group connect4 >/dev/null || groupadd --system connect4
for account in c4-referee c4-player1 c4-player2 c4-player3; do
    if id "$account" >/dev/null 2>&1; then
        [[ $(id -gn "$account") == connect4 ]] || { echo "Existing $account is not a game account." >&2; exit 1; }
    else
        useradd --system --no-create-home --gid connect4 --shell /usr/sbin/nologin "$account"
    fi
done
install -d -m 755 /opt/connect4-mayhem
for file in communication.py server.py client.py README.md; do
    install -m 644 "$project_dir/$file" "/opt/connect4-mayhem/$file"
done
install -m 755 "$project_dir/launch_game.sh" /opt/connect4-mayhem/launch_game.sh
# Remove the obsolete play entry point when upgrading an older installation.
rm -f /opt/connect4-mayhem/join_game.sh
echo 'Installed. In three terminals, run:'
echo '  sudo ./launch_game.sh --player 1   # starts the referee and Player1'
echo '  sudo ./launch_game.sh --player 2   # joins as Player2'
echo '  sudo ./launch_game.sh --player 3   # joins as Player3'
echo 'Start Player1 first, then join the others within 30 seconds.'
