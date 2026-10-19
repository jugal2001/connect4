#!/usr/bin/env bash
# Usage: ./join_game.sh Alice [--socket PATH]
# Class mode: ./join_game.sh Alice --class --slot 1
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $# == 0 ]]; then echo 'Usage: ./join_game.sh My-name [--class --slot 1] [--socket PATH]' >&2; exit 1; fi
name=$1
shift
if [[ ${1:-} == --class ]]; then
    shift
    [[ ${1:-} == --slot && ${2:-} =~ ^[1-4]$ ]] || { echo 'Choose a different Linux account per terminal: --class --slot 1 (1–4)' >&2; exit 1; }
    slot=$2
    shift 2
    exec sudo -u "c4-player$slot" python3 -u /opt/connect4-mayhem/client.py "$name" --socket /tmp/connect4-class/game.sock "$@"
fi
exec python3 -u "$project_dir/client.py" "$name" "$@"
