#!/usr/bin/env python3
"""Three-player free-for-all Connect-4, with a timed lobby and optional separate bot processes."""

import argparse
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import sys
import time

import communication

ROWS, COLS = 6, 7
PLAYER_COUNT = 3


class Game:
    def __init__(self, names, rng):
        shuffled = list(names)
        if len(shuffled) != PLAYER_COUNT or len(set(shuffled)) != PLAYER_COUNT:
            raise ValueError("Exactly three different players are required.")
        rng.shuffle(shuffled)
        self.order = shuffled
        self.symbols = dict(zip(shuffled, ("X", "O", "@")))
        self.board = [["." for _ in range(COLS)] for _ in range(ROWS)]
        self.turn = 0
        self.move = 1
        self.winner = None
        self.draw = False
        self.draw_reason = None
        self.pops = {name: 1 for name in names}

    def validate_turn(self, player, column):
        if self.winner or self.draw:
            raise ValueError("The game has finished.")
        if player != self.order[self.turn]:
            raise ValueError(f"It is {self.order[self.turn]}'s turn.")
        if type(column) is not int or not 1 <= column <= COLS:
            raise ValueError("Choose a column from 1 to 7.")

    def drop(self, player, column):
        self.validate_turn(player, column)
        col = column - 1
        if self.board[0][col] != ".":
            raise ValueError("That column is full. Choose another.")
        row = next(r for r in range(ROWS - 1, -1, -1) if self.board[r][col] == ".")
        self.board[row][col] = self.symbols[player]
        self.finish_turn()

    def pop(self, player, column):
        self.validate_turn(player, column)
        col = column - 1
        if not self.pops[player]:
            raise ValueError("You already used your pop token.")
        if self.board[-1][col] != self.symbols[player]:
            raise ValueError("You can only pop your own bottom disc.")
        for row in range(ROWS - 1, 0, -1):
            self.board[row][col] = self.board[row - 1][col]
        self.board[0][col] = "."
        self.pops[player] -= 1
        self.finish_turn()

    def finish_turn(self):
        winning_symbols = set()
        for row in range(ROWS):
            for col in range(COLS):
                symbol = self.board[row][col]
                if symbol == ".":
                    continue
                for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                    if all(0 <= row + i * dr < ROWS and 0 <= col + i * dc < COLS
                           and self.board[row + i * dr][col + i * dc] == symbol
                           for i in range(4)):
                        winning_symbols.add(symbol)
        if len(winning_symbols) == 1:
            symbol = winning_symbols.pop()
            self.winner = next(p for p, disc in self.symbols.items() if disc == symbol)
        elif len(winning_symbols) > 1:
            self.draw = True
            self.draw_reason = "Multiple players connected four at once."
        elif all(cell != "." for cell in self.board[0]):
            self.draw = True
            self.draw_reason = "The board is full."
        if not self.winner and not self.draw:
            self.turn = (self.turn + 1) % PLAYER_COUNT
            self.move += 1

    def state(self):
        return {"type": "state", "board": self.board, "turn": self.order[self.turn],
                "move": self.move, "winner": self.winner, "draw": self.draw,
                "pops": self.pops, "draw_reason": self.draw_reason,
                "symbols": self.symbols, "order": self.order}


def valid_name(name):
    return isinstance(name, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,19}", name) is not None


def run(args, lobby_seconds=30):
    transport = communication.Server(args.socket)
    identities = {}
    players = {}  # display name -> connection ID (Linux UID is checked separately)
    game = None
    rng = random.Random()
    deadline = time.monotonic() + lobby_seconds
    lobby_open = True
    expected_bots = set()  # reserved names for the clients we launch
    bot_processes = []
    roster = []
    bot_deadline = None

    def reply(connection_id, text, kind="info"):
        transport.send(connection_id, {"type": kind, "text": text})

    def lobby_view():
        return {"type": "lobby", "names": list(players),
                "seconds": 0 if args.bots else max(0, int(deadline - time.monotonic() + 0.999)),
                "bots": args.demo, "open": lobby_open, "capacity": PLAYER_COUNT}

    print(f"Lobby open for {lobby_seconds:g} seconds: {args.socket}", flush=True)
    print("Join in another terminal: ./launch_game.sh My-name", flush=True)
    print("DEMO: shared UIDs allowed" if args.demo else "CLASS: three distinct player UIDs required", flush=True)
    try:
        while True:
            now = time.monotonic()
            if lobby_open and (now >= deadline or (args.bots and players)):
                lobby_open = False
                if len(players) < PLAYER_COUNT and (not args.demo or not players):
                    reason = "At least one human must join." if args.demo else "Three players must join."
                    transport.broadcast({"type": "end", "text": f"Lobby closed: {reason} Restart the server to try again."})
                    print(reason, flush=True)
                    return
                roster = list(players)
                # Bots are real client processes using the same socket protocol.
                for number in range(1, PLAYER_COUNT + 1 - len(players)):
                    name = f"Bot{number}"
                    expected_bots.add(name)
                    roster.append(name)
                    command = [sys.executable, "-u", str(Path(__file__).with_name("client.py")), name,
                               "--socket", args.socket, "--bot"]
                    bot_processes.append(subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                bot_deadline = now + 5
                transport.broadcast(lobby_view())
            if not lobby_open and not game:
                if len(players) == PLAYER_COUNT:
                    game = Game(roster, rng)
                    print(f"Players: {game.symbols}; turn order: {game.order}", flush=True)
                    transport.broadcast(game.state())
                elif now >= bot_deadline or any(p.poll() is not None for p in bot_processes):
                    transport.broadcast({"type": "end", "text": "Could not fill all bot seats. Restart the server."})
                    return

            event_pair = transport.receive(timeout=0.1)
            if not event_pair:
                continue
            connection_id, event = event_pair
            kind = event["kind"]
            if kind == "connected":
                if game:
                    reply(connection_id, "A match is already running.", "error")
                    transport.disconnect(connection_id)
                else:
                    identities[connection_id] = event
                    transport.send(connection_id, lobby_view())
                continue
            player = next((p for p, c in players.items() if c == connection_id), None)
            if kind == "disconnected":
                identities.pop(connection_id, None)
                if player:
                    del players[player]
                    if not lobby_open:
                        transport.broadcast({"type": "end", "text": f"Match cancelled: {player} disconnected."})
                        return
                    transport.broadcast(lobby_view())
                continue
            if connection_id not in identities:
                continue
            message = event["payload"]
            action = message.get("type")
            try:
                if action == "join" and not player:
                    name = message.get("name")
                    is_fill_bot = isinstance(name, str) and name in expected_bots
                    error = None
                    if not lobby_open and not is_fill_bot:
                        error = "The joining period has ended."
                    elif args.bots and players and not is_fill_bot:
                        error = "Solo mode has one human and two bots."
                    elif not valid_name(name):
                        error = "Use 1–20 letters, digits, underscores or hyphens; start with a letter."
                    elif name.lower().startswith("bot") and not is_fill_bot:
                        error = "Names beginning with Bot are reserved for automatic bots."
                    elif len(players) == PLAYER_COUNT:
                        error = "The lobby is full (three players)."
                    elif name.casefold() in {p.casefold() for p in players}:
                        error = "That name is already taken. Choose another."
                    else:
                        uid = identities[connection_id]["uid"]
                        occupied = {identities[c]["uid"] for c in players.values()}
                        if not args.demo and (uid == os.getuid() or uid in occupied):
                            error = "Each player needs a distinct Linux user, separate from the referee."
                    if error:
                        reply(connection_id, error, "error")
                        transport.disconnect(connection_id)
                        continue
                    players[name] = connection_id
                    print(f"{name}: {identities[connection_id]['user']} (UID {identities[connection_id]['uid']})", flush=True)
                    reply(connection_id, f"Joined as {name}.")
                    transport.broadcast(lobby_view())
                    continue
                if not player:
                    raise ValueError("Join the lobby first.")
                if action in ("drop", "pop"):
                    if not game:
                        raise ValueError("Wait until the joining period ends and the game starts.")
                    if message.get("move") != game.move:
                        raise ValueError("That command used an older board. Type look and try again.")
                    if action == "pop":
                        game.pop(player, message.get("column"))
                        description = "popped their bottom disc from"
                    else:
                        game.drop(player, message.get("column"))
                        description = "dropped in"
                    transport.broadcast({"type": "info", "text": f"{player} ({game.symbols[player]}) {description} column {message['column']}."})
                    transport.broadcast(game.state())
                    if game.winner or game.draw:
                        result = (f"{game.winner} ({game.symbols[game.winner]}) wins! Four connected!"
                                  if game.winner else f"Draw! {game.draw_reason}")
                        transport.broadcast({"type": "end", "text": result})
                        print(result, flush=True)
                        return
                elif action == "look":
                    transport.send(connection_id, game.state() if game else lobby_view())
                elif action == "chat":
                    text = message.get("text")
                    if not isinstance(text, str) or not text.strip() or len(text) > 300 or not text.isprintable():
                        raise ValueError("Messages must contain 1–300 printable characters.")
                    channel = message.get("channel")
                    chat = {"type": "chat", "sender": player, "channel": channel, "text": text}
                    if channel == "all":
                        transport.broadcast(chat)
                    elif channel == "private":
                        target = message.get("target")
                        target = next((p for p in players if isinstance(target, str) and p.casefold() == target.casefold()), None)
                        if target is None or target == player:
                            raise ValueError("Whisper to another connected player by name.")
                        transport.send(players[target], chat)
                        reply(connection_id, f"Whisper to {target}: {text}")
                    else:
                        raise ValueError("Unknown chat channel.")
                else:
                    raise ValueError("Unknown command. Type help.")
            except ValueError as error:
                reply(connection_id, str(error), "error")
    finally:
        # Let cleanup finish even if the launcher sends a stop while we are
        # already closing a completed match and its bot processes.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        transport.close()
        for process in bot_processes:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", default=communication.default_socket())
    parser.add_argument("--demo", action="store_true", help="allow shared Linux UIDs for testing")
    parser.add_argument("--bots", action="store_true", help="start immediately with two bots (demo only)")
    args = parser.parse_args()
    if args.bots and not args.demo:
        parser.error("Use --demo --bots for same-account bot testing.")
    if args.socket == communication.default_socket():
        Path(args.socket).parent.mkdir(mode=0o700, exist_ok=True)
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nReferee stopped.")
    except OSError as error:
        parser.exit(1, f"Cannot run referee: {error}\n")


if __name__ == "__main__":
    main()
