# Connect-4 Mayhem — three players, no teams

A small Linux terminal game for **three individual players** on a 7×6 board.
Each player has a distinct symbol (`X`, `O`, or `@`) and one **Pop token**.
Connect four of your own discs to win. There are no teams, alliances, or shared
victories. The referee randomly selects the initial turn order.

Only Linux and Python 3.8+ are needed. No pip packages, tmux, or graphics
framework. **All socket communication is in [`communication.py`](communication.py).**

## Download and play

```bash
tar -xzf connect4-mayhem.tgz
cd connect4-mayhem
```

If Python is missing on Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y python3
```

There is **one play script** for hosting, joining, and bot mode.

### Play alone against two bots

```bash
./launch_game.sh --bots
```

You join as **Host**. Two independent bot processes fill the other seats
immediately; no second terminal or joining delay is needed. When the display
says **YOUR TURN**, type `drop 4`, or simply `4`. Bots make random legal drops
and occasionally use a legal pop. Bots do not respond to chat.

### Play with classmates

The host runs:

```bash
./launch_game.sh
```

The host automatically joins as **Host**. Two other players have 30 seconds to
join from their own terminals using the same script:

```bash
./launch_game.sh Alice
./launch_game.sh Bob
```

When the timer expires, empty seats become bots:

| Humans who joined, including Host | Bots added |
| --- | --- |
| 1 | 2 |
| 2 | 1 |
| 3 | 0 |

The normal lobby waits the full 30 seconds even if all seats fill early. A
fourth player, duplicate name, or late join is rejected. No mid-match joining
or reconnection. Run `./launch_game.sh --help` for the command reminder.

Names use 1–20 letters, digits, underscores or hyphens and start with a letter.
They are unique ignoring case. `Host` is taken by the host; names starting
with `Bot` are reserved. Names are display nicknames, not Linux credentials.

The simple launcher uses your current Linux account for all processes. Use
that same account in the other demo terminals. The socket is
`/tmp/connect4-mayhem-<UID>/game.sock`. See classroom mode below for genuinely
different Linux users, as required by the assignment.

The launcher starts a referee in the background and the host's client in the
foreground. It cleans up the referee and bots when the host exits or the match
finishes. `quit` or Ctrl-C leaves; any player's disconnection cancels the match
for everyone. A guest's launcher does not directly own or stop the referee.
Start the launcher again for a fresh match. An existing socket is never
silently replaced. After SIGKILL, remove a stale socket only after confirming
that its referee is no longer running.

## Rules

1. The referee shuffles the three players into a fixed turn order and assigns
   `X`, `O`, and `@`. Turns cycle through those players throughout the match.
2. `drop 4` places your disc in the lowest empty square in column 4. A bare
   column number is shorthand for `drop`.
3. Four or more **of your own symbol** horizontally, vertically, or diagonally
   wins immediately. Opponents' discs never contribute to your winning line.
4. Each player gets **one Pop token**. On your turn, `pop 4` removes column 4's
   bottom disc **only if it is yours**. Every disc above falls one square.
   Popping consumes your token and your turn.
5. After any move, the whole board is checked. A pop may give an opponent a
   win. If exactly one player has winning lines, that player wins. If multiple
   players have winning lines at once, the game is a draw. Multiple lines for
   one player still count as that single player's victory.
6. Invalid actions use neither your turn nor token. Full columns reject drops
   but may allow a pop. A completely full board without a winner is an immediate
   draw, even if unused Pop tokens remain.

No elimination, timer after the lobby, swapping, energy, or special roles.
The display shows all discs, each player's symbol, turn order, and remaining
Pop tokens. A disconnection cancels the match rather than awarding a victory.

## Commands

| Command | Effect |
| --- | --- |
| `drop 4` or `4` | Drop your disc into column 4 |
| `pop 4` | Remove your own bottom disc using your one Pop token |
| `say Block column 3!` | Public chat to all players |
| `/w Alice Watch Bob's diagonal` | Private whisper to one named player |
| `look` | Redisplay the board or current lobby roster and remaining time |
| `help` | Show commands |
| `quit` | Leave and cancel the match |

Whispers resolve names ignoring case. Public chat and whispers work both in
the lobby and during other players' turns. There is no team/alliance chat.
Players can negotiate or bluff, but promises have no effect on the rules.
An incoming message may appear while you're typing in this scrolling terminal;
your command remains intact, and `look` redraws the board. Lobby time is shown
on joins, departures, and `look`, not as a continuously ticking display.

## Classroom mode: three separate Linux player users

The easy launcher is a **demo** sharing your UID. Strict separate-user mode
uses the same Python files directly. `setup.sh` is an optional installation
tool, not a second play script.

```bash
sudo ./setup.sh
sudo install -d -o c4-referee -g connect4 -m 2750 /tmp/connect4-class
sudo -u c4-referee python3 /opt/connect4-mayhem/server.py --socket /tmp/connect4-class/game.sock
```

Prepare three terminals first, then join these clients within 30 seconds:

```bash
sudo -u c4-player1 python3 /opt/connect4-mayhem/client.py Alice --socket /tmp/connect4-class/game.sock
sudo -u c4-player2 python3 /opt/connect4-mayhem/client.py Bob --socket /tmp/connect4-class/game.sock
sudo -u c4-player3 python3 /opt/connect4-mayhem/client.py Cara --socket /tmp/connect4-class/game.sock
```

Setup creates group `connect4` and four locked accounts: `c4-referee` plus
`c4-player1`–`c4-player3`. It installs the code in `/opt/connect4-mayhem`. Rerun
setup after source changes. Upgrading does not delete an old `c4-player4` account;
it is simply unused. Accounts have no home directories or interactive shells.
An authorized operator uses sudo to start their processes.

The referee uses Linux `SO_PEERCRED` to verify each real connecting UID. It
rejects its own UID and a second player using an already joined UID. Nicknames
don't bypass this check. Socket directory mode `2750` and socket mode `0660`
give the shared group access without permission to replace the referee socket.

Automatic bot filling is a demo feature: those children share the referee's
UID. Strict mode requires three joined clients and cancels an underfilled lobby.
You can append `--bot` to any of the separate-account client commands above to
run an automated player under that account and retain distinct UIDs.

## Does this meet the assignment?

**The game design and implementation fit the technical requirements.** The
assignment allows any strategic text game; Werewolves roles and teams are not
required. Its wording allows **multicast or broadcast**. This version has
broadcast and direct player-to-player whispers; gameplay does not need multicast.

| Requirement | How this project addresses it |
| --- | --- |
| Strategy and text gameplay | Blocking, planning lines, and deciding when to Pop |
| Each player has a process and Linux user | Independent clients; distinct UIDs enforced in classroom mode |
| All communication in a single library file | `communication.py` |
| Primitive beyond named pipes | UNIX-domain stream sockets |
| Non-trivial message delivery | Unicast whispers and replies; broadcast board, chat, and results |
| Concurrency | Accept/reader threads, independent clients, concurrent chat and input |
| Source and README with file descriptions/API | Included in the source archive |
| PDF writeup with gameplay screenshots | **Still needs to be added for submission** |
| Understanding the primitive/library | You must be able to explain framing, sockets, queues, and threads |

Before submitting, run a complete classroom-mode game under three actual
player UIDs, create the PDF with real gameplay screenshots, and rebuild the
`.tgz`. The automated tests check UID rejection but do not replace an end-to-end
classroom-mode test. The archive alone is not yet a complete submission.

## Files and communication API

| File | Responsibility |
| --- | --- |
| **`communication.py`** | **Entire transport library: sockets, framing, threads, queues, peer UIDs** |
| `server.py` | Lobby, bot lifecycle, three-player rules, board, validation, routing |
| `client.py` | Named human client or bot, command parsing, terminal display |
| `launch_game.sh` | One script to host, join, or play against two bots |
| `setup.sh` | Optional separate-user system installation |
| `tests/` | Rules, stream framing, lobby, bots, privacy, and integration checks |

Only three Python files are required at runtime. Bots are independent clients;
the referee doesn't play their moves for them.

The primitive is a **UNIX stream socket** (`AF_UNIX`, `SOCK_STREAM`). Each
message is a UTF-8 JSON dictionary followed by a newline. The library handles
fragmented messages and multiple messages in a single stream read. Malformed
input or messages larger than 8 KiB close the connection. Each socket has a
write lock to prevent interleaving message bytes.

An accept thread and a reader thread per server connection enqueue events.
One main server loop changes game state. Client receiver threads run while a
keyboard thread waits for input. Chat remains concurrent even though game
moves take turns. Monotonic time controls the lobby deadline.

- **Unicast:** private whispers, acknowledgements, errors, and `look` replies.
- **Broadcast:** public board, roster, moves, chat, and results.
- **Multicast API:** retained as a general library utility, but unused by this
  game's rules. There are no team channels.

All player-to-player messages are relayed through the referee using this
library. The sender is determined by its connection, not client-supplied text.

| API | Behavior |
| --- | --- |
| `default_socket()` | Per-Linux-user demo socket pathname |
| `Server(path)` | Bind a new socket in an existing parent directory |
| `server.receive(timeout=None)` | `(connection_id, event)` or `None` on timeout |
| `server.send(id, message)` | Unicast a dictionary; return success boolean |
| `server.multicast(ids, message)` | Send to selected connection IDs |
| `server.broadcast(message)` | Send to all connections |
| `server.disconnect(id)` | Close one connection |
| `server.close()` | Close sockets and remove the bound pathname |
| `Client(path)` | Connect to the referee |
| `client.send(message)` | Send a dictionary |
| `client.receive(timeout=None)` | Receive a dictionary or `None` on timeout |
| `client.close()` | Disconnect |

Server events use `kind`: `connected` (kernel UID/user), `message` (payload),
or `disconnected`. Clients receive `{"type":"disconnected"}` on EOF.
`timeout=None` blocks; zero polls. Constructors and client sends may raise
`OSError`; oversized sends raise `ValueError`.

Example application messages:

```json
{"type":"join","name":"Alice"}
{"type":"drop","column":4,"move":1}
{"type":"pop","column":4,"move":4}
{"type":"chat","channel":"private","target":"Bob","text":"Watch column 3."}
{"type":"chat","channel":"all","text":"Good luck!"}
```

Public state includes `board`, `symbols`, `order`, `turn`, `move`, `pops`,
`winner` (a player's name), `draw`, and `draw_reason`. Lobby messages include
names, capacity (3), time remaining, bot-fill setting, and whether joining is
open. Stale move numbers are rejected. Names reserved for server-created bots can join after the lobby closes.
This classroom game trusts the local players; bot names are not authenticated.

## Verify and package

```bash
python3 -m unittest discover -s tests -v
bash -n launch_game.sh setup.sh
```

From the parent directory, after adding your PDF writeup:

```bash
tar --exclude='connect4-mayhem/.git' --exclude='__pycache__' \
  --exclude='*.tgz' -czf connect4-mayhem.tgz connect4-mayhem
```

The PDF should explain the game, communication primitive, API, concurrency,
and unicast/broadcast behavior, and include gameplay screenshots. The README
does not replace the PDF.

To uninstall classroom mode, stop games, delete the three player accounts and
referee account with `sudo userdel ACCOUNT`, delete group `connect4` with
`sudo groupdel connect4`, then remove `/opt/connect4-mayhem`. The demo creates
no Linux accounts or installed game files.
