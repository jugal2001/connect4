# Connect-4 Mayhem — random 2v2

Four players, two randomly assigned teams, one public 7×6 board. Teammates
share a disc symbol and a victory. Each player also has one **pop token**.
There are no alliance invitations or individual victories.

Only Linux and Python 3.8+ are needed. The game uses Python's standard library;
no pip packages or tmux are required. **All socket communication lives in
[`communication.py`](communication.py).**

## Start a game and join by name

From a downloaded archive:

```bash
tar -xzf connect4-mayhem.tgz
cd connect4-mayhem
```

If necessary, install Python on Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y python3
```

**Terminal 1 — start a lobby with automatic bots:**

```bash
./launch_game.sh --bots
```

**Terminal 2 — join during the initial 30 seconds:**

```bash
cd /path/to/connect4-mayhem
./join_game.sh My-name
```

The equivalent Python command is:

```bash
python3 client.py My-name
```

If you are the only person who joins, the server starts **three separate bot
processes** when the 30 seconds expire. You then control only your own player
and see the whole board in one terminal. Two humans get two bots; three humans
get one bot; four humans get none. No one joining means the lobby closes
without starting bots.

**Four-human game:**

```bash
# Terminal 1: referee
./launch_game.sh

# Each player uses their own terminal during the 30-second joining period:
./join_game.sh Alice
./join_game.sh Bob
./join_game.sh Cara
./join_game.sh Dan
```

Without `--bots`, fewer than four players at the deadline cancels the lobby.
Even when four players join early, teams are assigned only when the joining
period ends. A fifth player, a duplicate name, or a late join is rejected.
You cannot replace bots or reconnect after a match starts.

Names use 1–20 letters, digits, underscores or hyphens, starting with a letter.
Names are unique ignoring case. Names beginning with `Bot` are reserved for
server-created bots. **The name is a game nickname, not a Linux login or a
password.** The default demo permits all clients to run under your current
Linux account; use classroom mode below for separate Linux users.

Useful options:

```bash
./launch_game.sh --bots --lobby-seconds 60      # more time to open terminals
./launch_game.sh --bots --seed 42              # reproducible random choices
./launch_game.sh --bots --lobby-seconds 5 --bot-delay 0.2
```

The seed controls teams and bot seeds. Reproducing a match also requires the
same joining order and player actions. Bots make random legal moves, including
occasional pops. They do not understand team-chat instructions or plan strategy.
Your teammate may be a bot; team assignments are public and fixed for the match.

The default socket is `/tmp/connect4-mayhem-<your Linux UID>/game.sock`. Run the
launcher and named client as the same Linux user for the demo. To run another
simultaneous game, supply an explicit socket path with an existing parent:

```bash
mkdir -m 700 /tmp/my-other-connect4-game
./launch_game.sh --bots --socket /tmp/my-other-connect4-game/game.sock
# In another terminal:
./join_game.sh Alice --socket /tmp/my-other-connect4-game/game.sock
```

The referee owns its spawned bots and stops them when the match ends, it is
interrupted with Ctrl-C, or a player disconnects. `quit` exits the client and
cancels the match. Start the referee again for another 30-second lobby. An
existing socket is never silently replaced. Do not remove one belonging to a
running game. A forced kill (SIGKILL) can leave a stale socket requiring removal
once you have verified the old referee is gone.

## Rules

1. After the lobby closes, the referee shuffles the four players into teams
   **X** and **O**, with exactly two players on each team.
2. Turns alternate **X teammate 1 → O teammate 1 → X teammate 2 → O teammate 2**.
   Everyone gets their own turn; teammates cannot move on each other's behalf.
3. `drop 4` drops your team's disc into the lowest empty square in column 4.
   Both teammates' discs combine into the same winning lines.
4. Four or more Xs or Os in a horizontal, vertical, or diagonal line wins for
   **both members of that team**, regardless of who placed the last disc.
5. Each player has one personal pop token. `pop 4` removes the bottom disc of
   column 4 **if it belongs to your team**, even if your teammate placed it.
   All discs above fall one square. Popping uses your turn and your token;
   your teammate retains their own token.
6. After a pop, exactly one team with a winning line wins, even if it is the
   opposing team. If both teams get winning lines at once, it is a draw.
7. Invalid actions spend neither turn nor token. A full column cannot accept
   a drop but may be popped. A completely full board with no winning line is
   an immediate draw, even if pop tokens remain.

There is no time limit after the lobby. The display shows team membership,
turn order, each person's remaining pop token, and **YOUR TURN** when you can
act. Disconnection cancels the match, rather than awarding a victory.

## Commands

| Command | Meaning |
| --- | --- |
| `drop 4` or `4` | Drop your team's disc in column 4 |
| `pop 4` | Spend your token to remove your team's bottom disc |
| `team Block column 3` | Private team chat to you and your teammate |
| `say Good luck!` | Public chat |
| `/w Alice Hi` | Whisper privately to a named player (case-insensitive name) |
| `look` | Redisplay the board, or current lobby roster and remaining time |
| `help` | Show commands |
| `quit` | Leave and cancel the match |

Public chat and whispers work during the lobby. Team chat becomes available
once teams are assigned. Chat remains available outside your turn. The client
is a plain scrolling terminal; incoming text may appear while you type. Your
command still works, and `look` redraws the board. The lobby displays remaining
time on joins, departures, and `look`; it is not a continuously ticking timer.

## Classroom mode: separate Linux users

The default bot demo intentionally shares your Linux UID so one person can
run it without administrator access. For the assignment's separate-user mode:

```bash
sudo ./setup.sh
./launch_game.sh --class
```

Within 30 seconds, run one command in each of four terminals:

```bash
./join_game.sh Alice --class --slot 1
./join_game.sh Bob   --class --slot 2
./join_game.sh Cara  --class --slot 3
./join_game.sh Dan   --class --slot 4
```

Use a different slot per terminal. `--slot` selects a real Linux account;
`Alice` is the independent display name. For more joining time, use
`./launch_game.sh --class --lobby-seconds 120` (the `--class` flag comes first).

Setup creates group `connect4`, referee account `c4-referee`, and four player
accounts `c4-player1` through `c4-player4`. It installs sources and scripts in
`/opt/connect4-mayhem`. Accounts are locked, with no interactive login shells
or home directories. Sudo starts the processes; there are no game passwords.
Existing unrelated accounts are not repurposed. Rerun setup after code changes.

The referee runs under its own UID and validates client UIDs using Linux
`SO_PEERCRED`. It rejects its own UID and any second player using an already
joined UID, regardless of claimed nickname. Socket-directory mode `2750` and
socket mode `0660` let players connect without replacing the referee's socket.

**Automatic bot filling is a demo feature:** its child processes share the
referee's UID and therefore cannot satisfy strict mode's distinct-user rule.
The server rejects `--bots` without `--demo`. You can manually run a bot under
any of the four separate accounts while retaining strict mode:

```bash
./join_game.sh Computer --class --slot 2 --bot
```

Existing human Linux accounts can instead join strict mode if they belong to
`connect4` (log in again after group changes). Each human runs:

```bash
python3 /opt/connect4-mayhem/client.py Alice --socket /tmp/connect4-class/game.sock
```

Keep the referee on a different account. SSH may provide terminals on the same
Linux machine; the game itself uses local sockets, not network transport.
Service accounts cannot log in over SSH directly. The sudo join commands are
for an authorized operator starting those accounts' processes.

## Files and communication API

| File | Responsibility |
| --- | --- |
| **`communication.py`** | **Single-file transport library: sockets, JSON framing, threads, queues, peer credentials** |
| `server.py` | Timed lobby, bot-process lifecycle, random teams, board, rules, routing |
| `client.py` | Named human client or random bot; text display and command parsing |
| `launch_game.sh` | Start the demo or strict referee |
| `join_game.sh` | Join by display name, optionally under a class account |
| `setup.sh` | Optional separate-user installation |
| `tests/` | Rules, framing, lobby, naming, bot fill, privacy, and integration checks |

Only three runtime Python files; no third-party packages or graphical tools.
All inter-user messages go through `communication.py`. Spawning a bot starts
another independent client process; the server does not play moves for it.

The primitive is a **UNIX stream socket** (`AF_UNIX`, `SOCK_STREAM`), not a
named pipe. Each message is one UTF-8 JSON dictionary followed by a newline.
The library handles fragmented/coalesced stream reads and rejects malformed
messages or messages over 8 KiB. Each socket has a write lock to prevent
interleaving bytes. The referee has an accept thread and a reader thread per
connection. Those threads enqueue events; only the main loop mutates game state.
Clients receive messages while their keyboard thread waits for input. The
lobby deadline uses a monotonic clock. The server remains responsive to all
players' chat even though drops/pops take turns.

- **Broadcast:** public board, teams, lobby, moves, and results.
- **Unicast:** private whispers, confirmations, errors, and `look` replies.
- **Multicast:** team chat delivered to exactly the two assigned teammates.

Multicast is application-level delivery across two stream connections. Team
membership and sender identity come from server state, never client claims.
Whispers between players are relayed through the referee. No separate IPC
channel carries player messages.

| API | Behavior |
| --- | --- |
| `default_socket()` | Per-Linux-user demo socket pathname |
| `Server(path)` | Bind a new socket in an existing directory |
| `server.receive(timeout=None)` | `(connection_id, event)` or `None` on timeout |
| `server.send(id, message)` | Unicast a dictionary; return success boolean |
| `server.multicast(ids, message)` | Send to listed connection IDs |
| `server.broadcast(message)` | Send to all current connections |
| `server.disconnect(id)` | Close a connection |
| `server.close()` | Close connections and remove the bound socket |
| `Client(path)` | Connect to a referee |
| `client.send(message)` | Send a dictionary |
| `client.receive(timeout=None)` | Receive a dictionary or `None` on timeout |
| `client.close()` | Disconnect |

Server events are `connected` (with kernel UID/user), `message` (with a payload),
and `disconnected`, wrapped in a `kind` field. Clients receive a
`{"type":"disconnected"}` message on EOF. `timeout=None` blocks; zero polls.
Constructors and client sends may raise `OSError`; oversize sends raise
`ValueError`. The server owns connections until `close()`.

Example protocol messages:

```json
{"type":"join","name":"Alice"}
{"type":"drop","column":4,"move":1}
{"type":"pop","column":4,"move":5}
{"type":"chat","channel":"team","text":"Block left."}
{"type":"chat","channel":"private","target":"Bob","text":"Hello!"}
```

The public `state` includes `board`, `teams`, `symbols`, `order`, `turn`,
`move`, `pops`, `winner` (team symbol), `draw`, and `draw_reason`. `lobby`
messages include names, time remaining, whether bot fill is enabled, and
whether joining is open. Old move numbers are rejected. Automatic bots receive
private, per-process joining tokens so only the server's expected bots can
fill reserved seats after the public joining period ends.

The referee and machine administrators are trusted. This is a classroom
program, not a hardened public service or an encrypted messaging system.

## Tests and submission

```bash
python3 -m unittest discover -s tests -v
bash -n launch_game.sh join_game.sh setup.sh
```

From the parent directory, create a source archive:

```bash
tar --exclude='connect4-mayhem/.git' --exclude='__pycache__' \
  --exclude='*.tgz' -czf connect4-mayhem.tgz connect4-mayhem
```

The final class submission still needs your **PDF writeup with actual gameplay
screenshots**. Include it before packaging. Explain the communication primitive,
API, concurrency, and delivery patterns; the README does not replace that PDF.

To uninstall classroom mode, stop games, delete the five `c4-*` accounts above
using `sudo userdel ACCOUNT`, delete group `connect4` using `sudo groupdel
connect4`, and remove `/opt/connect4-mayhem`. The demo installs no accounts.
