# Connect-4 Mayhem

Connect-4 for **three players** in the terminal, with every player on their
own machine (or a simulated one).

## Rules

- Players are `X`, `O` and `@` and take turns in a fixed, random order.
- On your turn, type a column number to drop a disc. It lands on the lowest
  empty square.
- Connect **four of your own discs** in a row, column or diagonal to win.
- Once per game you may **Pop**: remove your own disc from the bottom of a
  column, so everything above it falls one square. This can make or break a
  line for any player.
- Several players connecting four at once, or a full board, is a draw.
- If a player leaves or becomes unreachable, the match is cancelled.

```
    1 2 3 4 5 6 7
  | . . . . . . . |
  | . . . . . . . |
  | . . . O . . . |
  | . . @ X . . . |
  | . . O X X . . |
  | . @ O X @ . . |
  +---------------+
You: Player1 (X) | Order: Player2 -> Player1 -> Player3
YOUR TURN — drop <1-7>, or pop <1-7> using your token:
```

| Type this | To |
|---|---|
| `4` | Drop a disc into column 4 |
| `pop 4` | Use your Pop token on your own bottom disc in column 4 |
| `say TEXT` | Message everyone |
| `/w Player2 TEXT` | Whisper to one player |
| `look`, `help`, `quit` | Redisplay the board, list commands, leave |

## Quick start

On Ubuntu/Debian:

```bash
git clone https://github.com/jugal2001/connect4.git
cd connect4/project2
sudo ./simulate.sh demo
```

This opens four tmux panes: the referee and three players, each on its own
simulated machine and Linux user. The game starts right away. **Click a pane**
to play as that player. To finish, type `quit` in a player pane, then press
Enter to close the demo.

To see the distributed part in action, open a second terminal mid-game and
cut one player's network link:

```bash
sudo ./simulate.sh cut 2
```

About five seconds later the referee notices and cancels the match.

No sudo? Play against two bots instead (needs only Python 3):

```bash
./play.sh
```

## For reviewers

Feedback on security and robustness is the most useful. Some places to look:

- [`project2/communication.py`](project2/communication.py) is the whole
  network layer (about 230 lines).
- Can you join without a seat token, reuse one, or take someone else's seat?
- Can a misbehaving client freeze or crash the referee (malformed messages,
  floods, never reading)?
- Traffic is not encrypted; see [Known limits](#design-notes) for what I
  already know about.

## Playing across real machines

All commands run from `project2/`. Only Python 3 is required. One person
starts the referee:

```bash
python3 server.py
```

It prints one ready-to-paste command per player, with this machine's address
and a seat token already filled in:

```
python3 client.py Player1 --host 192.168.1.20 --token 6bf212d8f56d22f0
python3 client.py Player2 --host 192.168.1.20 --token e6dea474a782e971
python3 client.py Player3 --host 192.168.1.20 --token 5b9e8da20ac97e4b
```

Each player runs one of those lines in their own terminal. The match starts
when all three have joined. If the 120-second lobby expires first, bots take
the empty seats.

Referee options: `--port N` (default 5544), `--bind ADDRESS`, `--lobby SECONDS`,
`--bots` (start as soon as one player joins).

## What changed since Project 1

| Folder | Version |
|---|---|
| [`project2/`](project2/) | **Project 2/3 (this README):** distributed, over TCP |
| [`project1/`](project1/) | Project 1: one machine, UNIX stream sockets ([README](project1/README.md), git tag `project1`) |

| | Project 1 | Project 2/3 |
|---|---|---|
| Transport | UNIX stream socket (`AF_UNIX`), one machine | TCP (`AF_INET`), any reachable machine |
| Player identity | Kernel-reported UID (`SO_PEERCRED`) | One-time seat token issued by the referee |
| Failure detection | Kernel closes the socket when a process dies | Heartbeats: a silent peer is dropped after 6 s |
| Stalled receiver | A blocked `sendall` could freeze the referee | Sends time out after 6 s and the peer is dropped |
| Lobby | Fixed 30 s | Starts as soon as three players join (120 s limit) |

The game rules, message format (one JSON object per line) and library API are
otherwise unchanged, so the two `communication.py` files can be compared
directly.

## Simulating several machines on one host

[`simulate.sh`](project2/simulate.sh) builds four network namespaces, one for the referee
and one per player, joined by virtual ethernet links. Each namespace has its
own network stack and address, and each process runs as its own Linux user
(`c4-referee`, `c4-player1..3`). Players can reach the referee only over
TCP/IP and cannot reach each other.

```
c4-p1 (10.44.1.2) ----\
c4-p2 (10.44.2.2) ----- c4-ref (10.44.N.1 on the link to player N)
c4-p3 (10.44.3.2) ----/
```

One command sets everything up and opens the referee and the three players
in four tmux panes:

```bash
sudo ./simulate.sh demo
```

Click a pane to type as that player (or press Ctrl-B, then an arrow key).
The referee pane lists the in-game commands.

Dependencies: `python3`, `tmux`, `iproute2` (`ip`, `tc`) and `util-linux`
(`runuser`). On Debian/Ubuntu, `up` and `demo` install any that are missing.
`cut` and `delay` also need the `sch_netem` kernel module, which on some
Ubuntu kernels comes from the `linux-modules-extra-$(uname -r)` package.

The same thing by hand, in four terminals:

```bash
sudo ./simulate.sh up          # once: accounts, namespaces, links
sudo ./simulate.sh referee     # terminal 1
sudo ./simulate.sh player 1    # terminals 2-4, one per player
sudo ./simulate.sh player 2
sudo ./simulate.sh player 3
```

The script hands each player its seat token, so nothing needs to be copied.

Fault injection, from another terminal while a match is running:

```bash
sudo ./simulate.sh cut 2          # silently drop all packets on player 2's link
sudo ./simulate.sh delay 2 300    # or add 300 ms of delay in each direction
sudo ./simulate.sh heal 2         # restore the link
sudo ./simulate.sh down           # remove the namespaces when finished
```

`cut` drops packets without closing anything, like an unplugged cable. Neither
end receives a FIN or RST, so the failure is only found by the heartbeat:
about six seconds later the referee prints `Lost Player2.` and cancels the
match, and that player's client prints `Lost connection to the referee.`

`up` installs a copy of the game in `/opt/connect4-mayhem-net`, because the
game accounts cannot read a home directory. Rerun it after changing the source.

## Communications library

> **The communications library is [`project2/communication.py`](project2/communication.py).**

All communication goes through this one file; `server.py` and `client.py`
never open sockets themselves.

- **Transport:** TCP, default port 5544.
- **Framing:** one UTF-8 JSON object per line, at most 8 KiB.
- **Concurrency:** one reader thread per connection feeds a queue, so the game
  loop and the keyboard never block on the network. A per-connection lock
  keeps concurrent sends from interleaving.
- **Heartbeat:** each side sends `{"type": "ping"}` every 2 s. Pings are
  consumed inside the library. A peer that sends nothing for 6 s is reported
  as disconnected.
- **Send timeout:** a send that cannot complete within 6 s fails and the
  connection is closed, so a peer that stops reading cannot stall the sender.

### API

| Call | Returns | Description |
|---|---|---|
| **`Server(host, port=5544)`** | server | Listen and start accepting. Raises `OSError` if the port is taken. `server.port` holds the bound port. |
| `server.receive(timeout=None)` | `(connection_id, event)` or `None` | Next event. `event["kind"]` is `connected` (with `address`), `message` (with `payload`) or `disconnected`. |
| `server.send(connection_id, message)` | `True` / `False` | Unicast. `False` if the peer is gone or the send timed out. |
| `server.multicast(connection_ids, message)` | none | Send to the listed peers. |
| `server.broadcast(message)` | none | Send to every connected peer. |
| `server.disconnect(connection_id)` | none | Close one connection. |
| `server.close()` | none | Stop listening and close all connections. |
| **`Client(host, port=5544)`** | client | Connect and start the reader and heartbeat threads. Raises `OSError` on failure. |
| `client.send(message)` | none | Send one message (a dictionary). |
| `client.receive(timeout=None)` | message or `None` | Next message. `{"type": "disconnected"}` means the server closed the connection or went silent. |
| `client.close()` | none | Close the connection. |
| `local_address()` | IP string | This machine's address as other machines see it, for printing join commands. |

## Design notes

**Seat tokens.** Over TCP the referee sees only an IP address, so the kernel
can no longer vouch for who connected. At startup the referee generates three
random 64-bit tokens and prints them; whoever started the referee passes one
to each player. A join must present an unused token; it is compared in
constant time and removed once used. Tokens left over when the lobby closes
are discarded, and each bot is given a fresh one. `play.sh` and `simulate.sh`
generate the tokens themselves and pass them through the `C4_TOKENS` and
`C4_TOKEN` environment variables, which is why those modes need no copying.

**Detect and cancel.** The referee holds all game state and is the single
authority on turn order, so a lost player cannot be skipped fairly. On a
closed connection or a heartbeat timeout the referee broadcasts the
cancellation and exits. There is no reconnection.

**Known limits.**
- Traffic is not encrypted. Anyone on the network path can read whispers and
  tokens; wrapping the socket in TLS would be the next step.
- A token passed with `--token` is visible in `ps` to other users of that
  machine. Set `C4_TOKEN` instead where that matters.
- The referee is a single point of failure. If it dies, every client detects
  it by heartbeat and exits.
- The referee cannot verify the Linux user of a remote player. In the
  simulation the separate users are enforced by `simulate.sh`.

## Files

| File | Purpose |
|---|---|
| [`project2/communication.py`](project2/communication.py) | **The communications library** |
| [`project2/server.py`](project2/server.py) | The referee: board, rules, lobby, tokens, chat routing |
| [`project2/client.py`](project2/client.py) | Terminal interface for a player, and the bot |
| [`project2/play.sh`](project2/play.sh) | One-command game against two bots |
| [`project2/simulate.sh`](project2/simulate.sh) | Multi-machine simulation and fault injection |
| [`project2/tests/`](project2/tests/) | Library, game-rule and end-to-end tests |
| [`project1/`](project1/) | The Project 1 version, unchanged |

Run the tests from `project2/` with `python3 -m unittest discover -s tests`.
