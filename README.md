# Connect-4 Mayhem — random 2v2

Four players, two randomly assigned teams, one public 7×6 board. Teammates
share a disc symbol and a victory. Each player also has one **pop token**.
There are no alliance invitations or individual victories.

Only Linux and Python 3.8+ are needed. The game uses Python's standard library;
no pip packages or tmux are required. **All socket communication lives in
[`communication.py`](communication.py).**

## One script to host, join, or play with bots

Extract the archive and enter the folder:

```bash
tar -xzf connect4-mayhem.tgz
cd connect4-mayhem
```

Only Python is needed (`sudo apt install python3` on Ubuntu/Debian).

**Play immediately against three bots:**

```bash
./launch_game.sh --bots
```

You automatically join as **Host**. Three separate bot processes fill the
other seats immediately; there is no 30-second wait and no second terminal
needed. Teams are random, so one bot is your teammate and two are opponents.

**Host a game for friends:**

```bash
./launch_game.sh
```

You automatically join as **Host** in that terminal. The game waits 30 seconds
for up to three other people. They join from their own terminals using the
**same script**, with their name:

```bash
./launch_game.sh Alice
./launch_game.sh Bob
./launch_game.sh Cara
```

When the timer expires, all empty seats become bots: Host alone gets three
bots; Host plus Alice gets two; three humans get one; four humans get none.
The game waits the full joining period even if all four seats fill early.
Late joins, a fifth player, and duplicate names are rejected. You cannot
replace a bot or reconnect after the game begins.

Names use 1–20 letters, digits, underscores or hyphens, starting with a letter.
Names are unique ignoring case. `Host` is already taken by the host; names
beginning with `Bot` are reserved for automatic bots. Names are game nicknames,
not Linux account logins or passwords.

Type `drop 4` (or just `4`) when the board says **YOUR TURN**. `pop 4` spends
your personal pop token. `team MESSAGE` talks privately to your teammate.
Bots choose random legal moves, including occasional pops; they don't follow
instructions sent through chat.

Run `./launch_game.sh --help` for a short command reminder. There is no separate
joining script. The host's launcher starts the referee in the background,
shows the host's client in the foreground, and cleans up the referee and bots
when the match finishes or the host exits. `quit` or Ctrl-C leaves the game.
Leaving any client cancels the match for everyone. A guest's launcher never
owns or stops the referee directly. Start the launcher again for a new game.

The single-script demo uses your current Linux account for all processes.
Use the same Linux account in the other terminals to reach its private socket,
`/tmp/connect4-mayhem-<UID>/game.sock`. See classroom mode below to use distinct
Linux users. The launcher refuses to overwrite an existing game socket. After
a forced kill (SIGKILL), a stale socket may need removing once you have verified
that its old referee is gone.

For advanced testing, the underlying Python entry points remain available:

```bash
# Referee only; you must separately join a named client:
python3 server.py --demo --bots --lobby-seconds 5 --seed 42
# Another terminal:
python3 client.py Alice
```

These server flags are deliberately not part of the simple launcher. The seed
controls team assignment and bot seeds; reproducing a match also requires the
same joining order and player actions. For parallel games use `--socket PATH`
on both Python commands, with an existing socket parent directory.

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

The one-script demo shares your Linux UID for convenient local testing. The
assignment's strict, separate-user mode uses the Python entry points directly.
`setup.sh` is an optional installation tool, not another play/launch script.

```bash
sudo ./setup.sh
sudo install -d -o c4-referee -g connect4 -m 2750 /tmp/connect4-class
sudo -u c4-referee python3 /opt/connect4-mayhem/server.py --socket /tmp/connect4-class/game.sock --lobby-seconds 120
```

Join four clients in separate terminals during that joining period:

```bash
sudo -u c4-player1 python3 /opt/connect4-mayhem/client.py Alice --socket /tmp/connect4-class/game.sock
sudo -u c4-player2 python3 /opt/connect4-mayhem/client.py Bob --socket /tmp/connect4-class/game.sock
sudo -u c4-player3 python3 /opt/connect4-mayhem/client.py Cara --socket /tmp/connect4-class/game.sock
sudo -u c4-player4 python3 /opt/connect4-mayhem/client.py Dan --socket /tmp/connect4-class/game.sock
```

Setup creates group `connect4`, `c4-referee`, and `c4-player1` through
`c4-player4`, then installs the game in `/opt/connect4-mayhem`. These locked
service accounts have no interactive login shell or home directory. An
authorized operator uses sudo to start each process; the nickname is independent
of its Linux user. Rerun setup after changing source files.

The referee verifies actual Linux UIDs with `SO_PEERCRED`; four different
player UIDs are required, all different from the referee. Shared group access
and directory mode `2750` let players connect without replacing the socket.
The socket has mode `0660`. Existing human Linux accounts can instead join
if they belong to `connect4` and log in again after group changes. They run
the same client command directly without sudo, under their own Linux accounts.

Automatic bot filling is a demo feature because server-spawned bots share the
referee's UID. Strict mode requires four joined clients; an underfilled lobby
cancels. To test strict mode with a bot, add `--bot` to any of the four separate
client commands above. It will run under that account, preserving separate UIDs.
SSH can provide terminals on the same machine; the game itself uses local
sockets, and the locked service accounts cannot log in over SSH themselves.

## Files and communication API

| File | Responsibility |
| --- | --- |
| **`communication.py`** | **Single-file transport library: sockets, JSON framing, threads, queues, peer credentials** |
| `server.py` | Timed lobby, bot-process lifecycle, random teams, board, rules, routing |
| `client.py` | Named human client or random bot; text display and command parsing |
| `launch_game.sh` | Single play script: host, join by name, or immediate three-bot mode |
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
bash -n launch_game.sh setup.sh
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
