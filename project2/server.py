#!/usr/bin/env python3
"""The referee: three-player Connect-4 over TCP, with seat tokens and a timed lobby."""

import argparse
import hmac
import os
from pathlib import Path
import random
import re
import secrets
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


def run(args):
    transport = communication.Server(args.bind, args.port)
    addresses = {}  # connection ID -> peer IP address
    players = {}    # display name -> connection ID
    # TCP cannot tell us who connected, so each seat needs a one-time token.
    # A launcher may supply them in C4_TOKENS; otherwise they are printed below.
    preset = os.environ.get("C4_TOKENS")
    tokens = preset.split(",") if preset else [secrets.token_hex(8) for _ in range(PLAYER_COUNT)]
    if len(set(tokens)) != PLAYER_COUNT or not all(tokens):
        raise ValueError("C4_TOKENS must hold three different comma-separated tokens.")
    bot_tokens = set()
    game = None
    rng = random.Random()
    deadline = time.monotonic() + args.lobby
    lobby_open = True
    bot_processes = []
    roster = []
    bot_deadline = None

    def reply(connection_id, text, kind="info"):
        transport.send(connection_id, {"type": kind, "text": text})

    def lobby_view():
        return {"type": "lobby", "names": list(players),
                "seconds": max(0, int(deadline - time.monotonic() + 0.999)) if lobby_open else 0,
                "open": lobby_open, "capacity": PLAYER_COUNT}

    def seat_token(token):
        return next((t for t in tokens if isinstance(token, str)
                     and hmac.compare_digest(t.encode(), token.encode())), None)

    print(f"Referee listening on {args.bind}:{transport.port}. Lobby open for {args.lobby:g} seconds.", flush=True)
    if not preset:
        host = communication.local_address() if args.bind == "0.0.0.0" else args.bind
        port = "" if transport.port == communication.DEFAULT_PORT else f" --port {transport.port}"
        print("One command per player (each token works once; change the names freely):", flush=True)
        for number, token in enumerate(tokens, 1):
            print(f"  python3 client.py Player{number} --host {host}{port} --token {token}", flush=True)
    try:
        while True:
            now = time.monotonic()
            if lobby_open and (now >= deadline or len(players) == PLAYER_COUNT
                               or (args.bots and players)):
                lobby_open = False
                if not players:
                    print("Lobby closed: nobody joined.", flush=True)
                    return
                roster = list(players)
                # Unused player tokens expire; each bot gets a fresh one.
                tokens[:] = [secrets.token_hex(8) for _ in range(PLAYER_COUNT - len(players))]
                bot_tokens.update(tokens)
                # Bots are real client processes using the same TCP protocol.
                for number, token in enumerate(tokens, 1):
                    roster.append(f"Bot{number}")
                    command = [sys.executable, "-u", str(Path(__file__).with_name("client.py")),
                               f"Bot{number}", "--bot", "--port", str(transport.port),
                               "--host", "127.0.0.1" if args.bind == "0.0.0.0" else args.bind]
                    bot_processes.append(subprocess.Popen(
                        command, env={**os.environ, "C4_TOKEN": token}, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                bot_deadline = now + 5
                transport.broadcast(lobby_view())
            if not lobby_open and not game:
                if len(players) == PLAYER_COUNT:
                    game = Game(roster, rng)
                    print(f"Players: {game.symbols}; turn order: {game.order}", flush=True)
                    transport.broadcast(game.state())
                elif now >= bot_deadline or any(p.poll() is not None for p in bot_processes):
                    transport.broadcast({"type": "end", "text": "Could not fill all bot seats. Restart the referee."})
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
                    addresses[connection_id] = event["address"]
                    transport.send(connection_id, lobby_view())
                continue
            player = next((p for p, c in players.items() if c == connection_id), None)
            if kind == "disconnected":
                # Reported for a closed connection and for a heartbeat timeout.
                addresses.pop(connection_id, None)
                if player:
                    del players[player]
                    print(f"Lost {player}.", flush=True)
                    if not lobby_open:
                        transport.broadcast({"type": "end", "text": f"Match cancelled: {player} disconnected or became unreachable."})
                        return
                    transport.broadcast(lobby_view())
                continue
            if connection_id not in addresses:
                continue
            message = event["payload"]
            action = message.get("type")
            try:
                if action == "join" and not player:
                    name = message.get("name")
                    token = seat_token(message.get("token"))
                    is_bot = token in bot_tokens
                    if token is None:
                        error = "Invalid or already used seat token."
                    elif not valid_name(name):
                        error = "Use 1–20 letters, digits, underscores or hyphens; start with a letter."
                    elif name.lower().startswith("bot") and not is_bot:
                        error = "Names beginning with Bot are reserved for automatic bots."
                    elif name.casefold() in {p.casefold() for p in players}:
                        error = "That name is already taken. Choose another."
                    else:
                        error = None
                    if error:
                        reply(connection_id, error, "error")
                        transport.disconnect(connection_id)
                        continue
                    tokens.remove(token)
                    players[name] = connection_id
                    print(f"{name} joined from {addresses[connection_id]}.", flush=True)
                    reply(connection_id, f"Joined as {name}.")
                    transport.broadcast(lobby_view())
                    continue
                if not player:
                    raise ValueError("Join the lobby first.")
                if action in ("drop", "pop"):
                    if not game:
                        raise ValueError("Wait until the lobby closes and the game starts.")
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
        # Let cleanup finish even if a stop signal arrives while we are
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
    parser.add_argument("--bind", default="0.0.0.0", help="address to listen on (default: all interfaces)")
    parser.add_argument("--port", type=int, default=communication.DEFAULT_PORT)
    parser.add_argument("--lobby", type=float, default=120, help="seconds to wait for players (default 120)")
    parser.add_argument("--bots", action="store_true", help="start as soon as one player joins; bots take the other seats")
    args = parser.parse_args()
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nReferee stopped.")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Cannot run referee: {error}\n")


if __name__ == "__main__":
    main()
