# Connect-4 Mayhem

Three players, one public 7-column × 6-row board. Drop discs in turn; the first
player to connect four of their own discs wins. Each player also gets one
**pop token** to remove their own bottom disc and shift a whole column.
Whisper deals and form private
alliances, but only one player can win.

**Start with one human and two bots in one terminal.** You do not need to
control three players. All game code uses Python's standard library; no pip
dependencies. Linux and Python 3.8+ are required.

## Download and play

Extract the source archive and enter its folder:

```bash
tar -xzf connect4-mayhem.tgz
cd connect4-mayhem
./launch_game.sh
```

If Python is missing, Ubuntu/Debian users can install it with:

```bash
sudo apt update
sudo apt install -y python3
```

You are **player1 (X)**. Two independent bot processes play **player2 (O)** and
**player3 (@)**. When you see **YOUR TURN**, type `drop 4`, or simply `4`.
The bots then play automatically. You can also use `pop 4` once per game if
the bottom disc in column 4 is yours. Remaining pop tokens are shown below
the board (`X=1 O=1 @=1`). There is no clock: take time to think or chat.
The board scrolls after every move, so there is only one view to follow.

```text
    1 2 3 4 5 6 7
  | . . . . . . . |
  | . . . . . . . |
  | . . . . . . . |
  | . . . . . . . |
  | . . . X . . . |
  | . . O X @ . . |
  +---------------+
```

This is an illustrative board, not a screenshot of a recorded match.

Other starting commands:

```bash
./launch_game.sh --watch          # watch three bots; no typing needed
./launch_game.sh --seed 42        # repeatable bot choices
./launch_game.sh --humans         # three human clients in labeled tmux panes
```

`--humans` additionally needs tmux (`sudo apt install -y tmux`). Click a pane
to type, or use **Ctrl-b, then an arrow key** to switch. **Ctrl-b, then z** zooms
the selected pane. **Ctrl-b, then d** leaves the session and stops the match.
Finished panes remain visible until you leave, so you can read the result.
Run the launcher again for a fresh game. The launcher cleans up its own referee,
bots, and temporary socket on exit. `quit` or Ctrl-C leaves a solo game.

The default mode is a demo: each player is a separate process but shares your
Linux UID. Use the classroom mode below to meet the separate-user requirement.

## Rules (one minute)

1. Turns rotate **player1 → player2 → player3 → player1**.
2. On your turn, choose a column from 1 to 7. Your disc falls to the lowest
   empty square. Alternatively, spend your one pop token: `pop <column>` removes
   **your own bottom disc**, and every disc above it falls one square. A pop
   uses your turn. You cannot pop an empty column or another player's disc.
3. Four or more of **your own symbol** in a horizontal, vertical, or diagonal
   line wins immediately. Discs from allies do not combine into a winning line.
   After a pop, the whole board is checked: exactly one player with a winning
   line wins, **even if it is your opponent**. If two or three players have
   winning lines at once, the game is a draw. Several lines for the same player
   still count as just that player's win.
4. A drop into a full column is rejected without losing your turn. You may pop
   a full column if its bottom disc is yours and you still have your token.
   Invalid pops do not spend your token or turn. A completely full board with
   no winning line ends in a draw immediately, even if pop tokens remain.
5. Chat, whisper, and negotiate at any time, including outside your turn.
6. An alliance is a private two-player chat group, not a shared victory or a
   change to turn order. Offers require acceptance. You may leave at any time.
   Promises are not enforced: bluffing and betrayal are allowed.

There is no elimination, hidden board, or time limit.
If a player disconnects, the match is cancelled for everyone; it is not a win.
There is no joining or reconnecting after the match starts.

## Commands

| Command | What it does |
| --- | --- |
| `drop 4` or `4` | Drop your disc in column 4 |
| `pop 4` | Spend your one token to remove your bottom disc from column 4 |
| `say Block player3 in column 2!` | Public message |
| `/w player2 I'll block left if you block right` | Private message/deal offer |
| `alliance player2` | Privately invite player2 to an alliance |
| `alliance accept player1` | Accept player1's latest offer to you |
| `alliance say Let's block column 5` | Message only yourself and your partner |
| `alliance` | Show your current partner |
| `alliance leave` | End your alliance and cancel your pending invitations |
| `look` | Redisplay the public board |
| `help` | Show commands |
| `quit` | Leave and cancel the game |

Each player has at most one partner. A new invitation replaces the previous
pending invitation to its recipient. Alliance membership is announced only to
the two members. The third player receives no invitation or alliance chat.

**Bots choose random legal moves**, not clever moves. When they have a legal
pop, they choose it with 25% probability; otherwise, they drop in a random
non-full column. They never pop another player's disc or reuse a token.
They automatically
accept valid alliance offers and send an alliance greeting, so you can test
unicast offers and multicast chat alone. They do not understand promises or
change their strategy based on messages. Bot choices use separate seeds.

## Classroom mode: separate Linux users

```bash
sudo ./setup.sh
./launch_game.sh --class             # one human + two bots, each a distinct UID
./launch_game.sh --class --humans     # three humans, each a distinct UID
```

Setup creates the `connect4` group and four locked service accounts:
`c4-referee`, `c4-player1`, `c4-player2`, and `c4-player3`. It copies the game to
`/opt/connect4-mayhem`. On Debian/Ubuntu it installs missing Python/tmux
dependencies. On other Linux distributions, install them yourself first.
Accounts have no home directory, interactive login shell, or password to enter.
Existing unrelated accounts are not repurposed. Rerun setup after code changes.

The launcher asks for sudo and runs each process as its own account using
`runuser`. The referee reads the connecting process's real UID with Linux
`SO_PEERCRED`, rejecting a reused player UID or its own UID. Claimed names in
JSON are never used for Linux authentication. `player1`–`player3` are selectable
lobby slots; the launcher consistently maps them to their matching accounts.

The socket directory is owned by the referee, with mode `2750` and the shared
group. The socket inherits that group and has mode `0660`. Players can connect
but cannot replace the referee's socket. Demo sockets live in a private
temporary directory belonging to your current account.

### Three classmates using separate terminals

Use separate terminals or SSH sessions on the same Linux machine to keep
whispers private. The all-in-one pane layout is for testing; anyone looking at
all three panes can read those players' private messages.

After setup, an authorized operator starts the referee in one terminal:

```bash
sudo install -d -o c4-referee -g connect4 -m 2750 /tmp/connect4-class
sudo -u c4-referee python3 /opt/connect4-mayhem/server.py --socket /tmp/connect4-class/game.sock
```

Start one of these commands in each player's terminal:

```bash
sudo -u c4-player1 python3 /opt/connect4-mayhem/client.py --socket /tmp/connect4-class/game.sock --player player1
sudo -u c4-player2 python3 /opt/connect4-mayhem/client.py --socket /tmp/connect4-class/game.sock --player player2
sudo -u c4-player3 python3 /opt/connect4-mayhem/client.py --socket /tmp/connect4-class/game.sock --player player3
```

Add `--bot` to any client to automate it. These service accounts cannot log in
over SSH themselves; an authorized operator launches their processes. Existing
individual Linux accounts can alternatively be added to the `connect4` group,
log in again, then run the client directly without sudo. Keep the referee on
a different UID. The game itself communicates locally, not over the network.

## Small codebase

| File | Responsibility |
| --- | --- |
| **[`communication.py`](communication.py)** | **The entire communication library, in one file** |
| `server.py` | Board, gravity, wins, turns, alliances, validation, and message recipients |
| `client.py` | Text display, commands, and optional random-bot behavior |
| `launch_game.sh` | Referee + three clients, cleanup, optional tmux and separate users |
| `setup.sh` | Optional system installation for classroom mode |
| `tests/` | Rules, socket framing, privacy, multiplayer, and bot checks |

Only three Python source files are needed to run the game. No third-party game
framework, asynchronous framework, database, or graphics dependency is used.

### Communication primitive and concurrency

The primitive is a **UNIX-domain stream socket** (`AF_UNIX`, `SOCK_STREAM`).
Each player has a persistent bidirectional connection to the referee. A stream
does not preserve message boundaries, so every message is a UTF-8 JSON object
followed by a newline. The library reassembles split reads and separates
multiple messages that arrive together. Malformed input or messages exceeding
8 KiB close the connection.

The referee has an accept thread and one reader thread per connection. Readers
enqueue events; the single main server loop updates the board and alliances.
This prevents simultaneous board mutations. Each client receives messages in
a background thread while a keyboard thread waits for human input. Bots are
independent client processes using the same protocol. Players can send chat
and receive board updates concurrently even though disc drops take turns.

- **Broadcast:** the same public board and move announcements go to everyone.
- **Unicast:** whispers, alliance invitations, acknowledgements, and errors go
  to individual connections.
- **Multicast:** alliance messages go to exactly the two members. This is
  application-level multicast over their individual stream connections.

Player-to-player messages are routed through the referee. The game chooses
the recipients; all transport operations live in `communication.py`. There
are no named pipes or extra player communication channels. A per-socket lock
prevents concurrent writers from interleaving message bytes. Move numbers
prevent commands from an older board being applied to a later turn.

### Communication API

| Function | Behavior |
| --- | --- |
| `Server(path)` | Bind a new socket; the parent directory must already exist |
| `server.receive(timeout=None)` | Return `(connection_id, event)`, or `None` on timeout |
| `server.send(id, message)` | Send a dictionary to one connection; return success boolean |
| `server.multicast(ids, message)` | Send to selected connection IDs |
| `server.broadcast(message)` | Send to all current connections |
| `server.disconnect(id)` | Close one connection |
| `server.close()` | Close all sockets and remove the socket pathname |
| `Client(path)` | Connect to a referee |
| `client.send(message)` | Send a dictionary |
| `client.receive(timeout=None)` | Return a message or `None` on timeout |
| `client.close()` | Disconnect |

Server events are `{"kind":"connected","uid":...,"user":...}`,
`{"kind":"message","payload":{...}}`, and `{"kind":"disconnected"}`.
The library creates these envelopes; clients cannot supply trusted identity
events. Clients receive `{"type":"disconnected"}` when their socket closes.
`timeout=None` blocks; `timeout=0` polls. Constructors and client sends may
raise `OSError`; oversize outbound messages raise `ValueError`.

Example protocol messages:

```json
{"type":"join","player":"player1"}
{"type":"drop","column":4,"move":1}
{"type":"pop","column":4,"move":4}
{"type":"chat","channel":"private","target":"player2","text":"Block column 7?"}
{"type":"alliance","operation":"invite","target":"player2"}
{"type":"alliance","operation":"accept","target":"player1"}
{"type":"chat","channel":"alliance","text":"I'll block the left side."}
```

The server identifies senders from their connections. It does not trust a
client-supplied sender, board, turn, or alliance membership. The referee and
machine administrators are trusted; this is not a hardened public service.
Public `state` messages include `pops` (each player's remaining token count)
and `draw_reason`. The referee validates pop ownership, tokens, and turn/move
numbers; clients cannot grant themselves additional tokens.

## Verify and package

```bash
python3 -m unittest discover -s tests -v
bash -n launch_game.sh setup.sh
```

From the parent directory, package your source and documentation:

```bash
tar --exclude='connect4-mayhem/.git' --exclude='__pycache__' \
  --exclude='*.tgz' -czf connect4-mayhem.tgz connect4-mayhem
```

Before final class submission, add the required **PDF writeup with actual
gameplay screenshots** to this folder. Discuss the socket primitive, API,
concurrency, and the three delivery patterns. This README is not a substitute
for that PDF. The source archive alone is not the complete assignment submission.

## Troubleshooting / removal

- **Not your turn:** wait for `YOUR TURN`; chat remains available.
- **Full column:** choose another. It is still your turn.
- **Waiting for players:** all three slots must connect before starting.
- **Permission denied:** check socket-directory traversal and group membership,
  or use the default demo launcher.
- **Address already in use:** stop the old referee; don't remove a live socket.
- **Need to test alone:** omit `--humans`; the default mode is one human + bots.
- **Bot difficulty:** bots are deliberately random, so classmates provide the
  strategic challenge. Three-player turn order and bargaining need playtesting.
- **Incoming text while typing:** this is a plain scrolling terminal. Your
  command remains intact; `look` redisplays the board after chat.

The demo adds no users or installed game files. To remove classroom mode,
stop games, delete the four `c4-*` accounts created above with `sudo userdel
ACCOUNT`, delete the `connect4` group with `sudo groupdel connect4`, and remove
the installed files in `/opt/connect4-mayhem`.
