# Connect-4 Mayhem

A terminal game for **three players**, each with their own symbol: `X`, `O`, or
`@`. Connect four of your discs horizontally, vertically, or diagonally on a
7×6 board. Each player also gets one **Pop token** to remove their own bottom
disc and shift a column. Everyone plays for themselves.

## Rules

1. Turn order is randomly chosen at the start and stays fixed. The display
   shows your symbol, whose turn it is, and everyone's remaining Pop tokens.
2. Drop a disc into a column from `1` to `7`. It lands in the lowest empty
   square. You cannot drop into a full column.
3. Connect at least four of **your own discs** horizontally, vertically, or
   diagonally to win.
4. Once per game, use `pop COLUMN` on your turn to remove the bottom disc of
   that column **if it belongs to you**. All discs above it fall one square.
   This spends your turn and your Pop token.
5. A Pop can give an opponent a win. If several players get winning lines at
   once, the game is a draw. A full board without a winner is also a draw,
   even if players have unused Pop tokens.
6. Invalid moves cost neither your turn nor your token. There is no turn timer.

If any player leaves or disconnects, the match is cancelled for everyone.
Start the launcher again to play a new match.

**Hint:** Three-player games can hit a dead end when everyone keeps
blocking each other. The key is to use your **Pop ability creatively**:
shift a column to break an opponent's line, bring your discs into alignment,
or set up a surprise diagonal. Check what the falling discs will do for
all three players before you Pop.

## Quick start: play against bots

On Ubuntu/Debian with Git installed, clone the repo and run:

```bash
git clone https://github.com/jugal2001/connect4.git connect4-mayhem
cd connect4-mayhem
sudo ./setup.sh
./launch_game.sh --bots
```

Setup installs the dependencies and creates the game accounts. The last command starts a game
against two bots. Run all commands from the game folder.

You join as **Host**, and the game starts immediately with two bots. When you
see **YOUR TURN**, enter a column number from `1` to `7` to drop a disc.
Bots look for wins, block threats, and build their own lines. They can use
Pop tokens but do not respond to chat.

For another match, run `./launch_game.sh --bots` again.

## In-game commands

Enter these commands in the game terminal. Drops and Pops only work on your turn;
chat is available in the lobby and throughout the match.

| Command | What it does |
| --- | --- |
| `drop 4` or `4` | Drop your disc into column 4 |
| `pop 4` | Spend your Pop token to remove your bottom disc in column 4 |
| `say Watch column 3!` | Send a message to everyone |
| `/w Alice Watch Bob's diagonal` | Send a private message to Alice; names ignore case |
| `look` | Show the board again, or the lobby roster and remaining time |
| `help` | Show the in-game commands |
| `quit` | Leave and cancel the match |

You can negotiate or bluff through chat, but there are no formal teams or
shared victories. Messages may appear while you type; your input is still
accepted. Use `look` if you need a fresh board view. **Ctrl-C** also exits.

## Other ways to play

### Play in separate terminals

All players must be on the **same Linux machine**. For this launcher mode,
use the **same Linux account** in each terminal. To use separate accounts,
follow the setup further below.

The host starts the game:

```bash
./launch_game.sh
```

The host joins as **Host**. Two other players join from separate terminals within
30 seconds, choosing different names:

```bash
./launch_game.sh Alice
./launch_game.sh Bob
```

The lobby waits the full 30 seconds, even when all three seats are filled.
Empty seats become bots. Late joins and reconnects are not supported.

Names must start with a letter and contain 1–20 letters, digits, underscores,
or hyphens. Names are unique ignoring case. `Host` is already taken, and names
starting with `Bot` are reserved.

### Open three players in one terminal

```bash
./launch_game.sh --windows
```

This opens three human clients in side-by-side tmux panes as **Player1**,
**Player2**, and **Player3**. They join automatically; play starts after the
30-second lobby. Use a wide terminal.

- Click a pane, or press **Ctrl-B**, release, then an **arrow key** to switch players.
- Press **Ctrl-B**, then **Z** to zoom the selected pane or restore the layout.
- Type `quit` in any pane to end the match and close the game session.
- When launched from outside tmux, detaching with **Ctrl-B**, then **D** also stops the game.

For a reminder of launcher options, run `./launch_game.sh --help`.

### Play under separate Linux accounts

After setup, open three terminals on the same Linux machine in the game folder.
In the first, start the game as Player1:

```bash
sudo ./launch_game.sh --player 1
```

In the other two terminals, join within 30 seconds:

```bash
sudo ./launch_game.sh --player 2
sudo ./launch_game.sh --player 3
```

Player1 starts the referee automatically, so no fourth terminal is needed.
Each client runs as its own Linux account (`c4-player1`, `c4-player2`, or
`c4-player3`), and the referee runs as `c4-referee`. The launcher handles the
shared socket and account switching. These commands require sudo access;
you do not need to log into the game accounts or set passwords for them.

All three players must join; this mode does not fill empty seats with bots.
Leaving cancels the match. To play again, run Player1's command first, then
join with Players 2 and 3.

Setup installs a copy in `/opt/connect4-mayhem`. Rerun `sudo ./setup.sh` after
source changes to update the copy used by this mode.

## Troubleshooting

- **No lobby running:** start `./launch_game.sh` in the host terminal first,
  then join within 30 seconds using the same Linux account. For separate-account
  mode, start `sudo ./launch_game.sh --player 1` before Players 2 and 3 join.
- **A game socket already exists:** join the existing lobby with
  `./launch_game.sh NAME`, or stop the old host before starting another game.
  After a forced shutdown, a socket may remain at
  `/tmp/connect4-mayhem-<UID>/game.sock` (demo) or
  `/run/connect4-mayhem/game.sock` (separate accounts). Remove it only after
  confirming the old referee has stopped.
- **Lobby closed or match already running:** wait for the next game. Players
  cannot join or reconnect after play starts.
- **tmux missing:** install it with `sudo apt install tmux`, or use separate
  terminals or bot mode.

## How it works

[`communication.py`](communication.py) handles all messages using local UNIX
stream sockets. Messages are newline-delimited JSON, limited to 8 KiB. Reader
threads feed queues so clients can receive updates while waiting for keyboard
input; write locks keep simultaneous sends from mixing message bytes. The
referee relays private whispers to one player and broadcasts public chat,
board updates, and results. Separate-account mode checks actual Linux user IDs
with `SO_PEERCRED`.

[`server.py`](server.py) owns the board, validates moves, checks wins and draws,
and updates game state in one main loop. [`client.py`](client.py) handles the
terminal interface and bot decisions. Each human or bot is a separate client
process. Bots evaluate legal drops and Pops for immediate wins, opponent
threats, and usable four-disc lines; randomness breaks equal scores. They do
not search several turns ahead.

## Communications library

> **The communications library is [`communication.py`](communication.py), in the top level of this repository.**
> `setup.sh` also installs a copy at `/opt/connect4-mayhem/communication.py`, which is used by the separate-Linux-account mode.

All interprocess communication in the game goes through this one file. `server.py` and `client.py` never open sockets themselves.

**Transport:** local UNIX stream sockets (`AF_UNIX`, `SOCK_STREAM`).
**Messages:** one JSON object per line (newline-delimited), at most 8 KiB each.
**Socket address:** `/tmp/connect4-mayhem-<UID>/game.sock` in the shared-account mode, `/run/connect4-mayhem/game.sock` in the separate-account mode.
**Identity:** on every connection the server reads the peer's Linux UID from the kernel (`SO_PEERCRED`), so a client cannot claim to be someone else.

### API

| Call | Returns | Description |
|---|---|---|
| `default_socket()` | path string | Default per-user socket address |
| **`Server(path)`** | server object | Binds and listens on the socket and starts accepting clients. Raises `OSError` if the path is in use. |
| `server.receive(timeout=None)` | `(connection_id, event)` or `None` | Next event. `event["kind"]` is `connected` (with `uid` and `user`), `message` (with `payload`), or `disconnected`. `None` means the timeout expired. |
| `server.send(connection_id, message)` | `True` / `False` | Unicast to one client. `False` if that client has gone away. |
| `server.multicast(connection_ids, message)` | none | Send to the listed clients only. |
| `server.broadcast(message)` | none | Send to every connected client. |
| `server.disconnect(connection_id)` | none | Close one client's connection. |
| `server.close()` | none | Stop accepting, close all connections, remove the socket file. |
| **`Client(path)`** | client object | Connects to the server and starts a reader thread. Raises `OSError` on failure. |
| `client.send(message)` | none | Send one message (a dictionary) to the server. |
| `client.receive(timeout=None)` | message dict or `None` | Next message. `{"type": "disconnected"}` means the server went away. `None` means the timeout expired. |
| `client.close()` | none | Close the connection. |

Messages are plain Python dictionaries. Each connection has a reader thread that places incoming messages on a queue, so the game can keep receiving while it waits for keyboard input.

## Files

| File | Purpose |
|---|---|
| [`communication.py`](communication.py) | **The communications library** (the API above) |
| [`server.py`](server.py) | The referee: owns the board, validates moves, checks wins and draws, and runs the lobby |
| [`client.py`](client.py) | The terminal interface for a player, and the bot logic |
| [`launch_game.sh`](launch_game.sh) | Launcher for all play modes (`--bots`, `--windows`, `--player N`) |
| [`setup.sh`](setup.sh) | Installs dependencies, creates the game accounts, and installs a copy in `/opt/connect4-mayhem` |
| [`tests/test_communication.py`](tests/test_communication.py) | Tests for the communications library |
| [`tests/test_game.py`](tests/test_game.py) | Tests for the game rules and bot logic |
| [`tests/test_integration.py`](tests/test_integration.py) | End-to-end tests over real sockets (lobby timing, privacy, bot fill) |

Run the tests from the repository root with `python3 -m unittest discover -s tests`.