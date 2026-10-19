#!/usr/bin/env python3
"""A scrolling text client, or a tactical bot when started with --bot."""

import argparse
from copy import deepcopy
import queue
import random
import threading
import time

import communication
from server import Game

HELP = """drop 4                 Drop your own disc (a bare number also works).
pop 4                  Remove your own bottom disc; one token per player.
say MESSAGE            Talk to everyone.
/w Alice MESSAGE       Whisper to a player by name.
look / help / quit     Redisplay board or lobby / commands / exit.
Each player has a unique symbol. Connect four of your own discs to win.
"""


def show_board(state, player):
    symbols = state["symbols"]
    print("\n    1 2 3 4 5 6 7")
    for row in state["board"]:
        print("  | " + " ".join(row) + " |")
    print("  +---------------+")
    print("Players: " + "  ".join(f"{name}={symbol}" for name, symbol in symbols.items()))
    print(f"You: {player} ({symbols[player]}) | Order: {' -> '.join(state['order'])}")
    print("Pop tokens: " + "  ".join(f"{p}={tokens}" for p, tokens in state["pops"].items()))
    if not state["winner"] and not state["draw"]:
        if state["turn"] == player:
            print("YOUR TURN — drop <1-7>, or pop <1-7> using your token:", flush=True)
        else:
            print(f"Waiting for {state['turn']} ({symbols[state['turn']]}). You can still chat.", flush=True)


def parse_command(line, move):
    parts = line.strip().split(maxsplit=1)
    if not parts:
        return None
    command = parts[0].lower()
    text = parts[1] if len(parts) == 2 else ""
    if command.isdigit():
        command, text = "drop", command
    if command in ("drop", "pop"):
        if move is None:
            raise ValueError("Wait for the lobby to close and the game to start.")
        try:
            column = int(text)
        except ValueError:
            raise ValueError(f"Use {command} followed by a column number, such as {command} 4.") from None
        return {"type": command, "column": column, "move": move}
    if command == "say":
        return {"type": "chat", "channel": "all", "text": text}
    if command == "/w":
        target, separator, body = text.partition(" ")
        if not separator:
            raise ValueError("Use: /w Alice your message")
        return {"type": "chat", "channel": "private", "target": target, "text": body}
    if command == "look":
        return {"type": "look"}
    raise ValueError("Unknown command. Type help.")


def bot_moves(game, player):
    """List legal drops and pops for one player."""
    moves = [("drop", col + 1) for col, cell in enumerate(game.board[0]) if cell == "."]
    if game.pops[player]:
        moves += [("pop", col + 1) for col, cell in enumerate(game.board[-1])
                  if cell == game.symbols[player]]
    return moves


def try_bot_move(game, player, action):
    """Use the real game rules on a copy, leaving the live board untouched."""
    trial = deepcopy(game)
    trial.turn = trial.order.index(player)
    command, column = action
    getattr(trial, command)(player, column)
    return trial


def line_score(game, player):
    """Value usable four-cell lines, not a column's distance from the center.

    Mixed-symbol lines cannot win without a Pop, so don't reward building them.
    Empty squares with space underneath need more setup than playable squares.
    """
    board = game.board
    symbol = game.symbols[player]
    rows, cols = len(board), len(board[0])
    score = 0.0
    for row in range(rows):
        for col in range(cols):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                if not (0 <= row + 3 * dr < rows and 0 <= col + 3 * dc < cols):
                    continue
                cells = [(row + i * dr, col + i * dc) for i in range(4)]
                values = [board[r][c] for r, c in cells]
                count = values.count(symbol)
                if not count or any(value not in (symbol, ".") for value in values):
                    continue
                support = sum(board[below][c] == "."
                              for r, c in cells if board[r][c] == "."
                              for below in range(r + 1, rows))
                score += (0, 1, 12, 80, 10000)[count] / (1 + support)
    return score


def winning_moves(game, player):
    return sum(try_bot_move(game, player, action).winner == player
               for action in bot_moves(game, player))


def choose_bot_move(state, player, rng):
    """Take wins, avoid immediate losses, then build threats and usable lines.

    Threat checks include Pops and the support a drop gives an enemy's diagonal
    or horizontal line. This is a one-move tactical evaluation, not a full search.
    Randomness only breaks ties between equally scored actions.
    """
    game = Game(state["order"], random.Random(0))
    game.order = list(state["order"])
    game.symbols = dict(state["symbols"])
    game.board = deepcopy(state["board"])
    game.pops = dict(state["pops"])
    moves = bot_moves(game, player)
    outcomes = [(action, try_bot_move(game, player, action)) for action in moves]

    winning = [action for action, trial in outcomes if trial.winner == player]
    if winning:
        chosen = rng.choice(winning)
    else:
        index = game.order.index(player)
        opponents = [game.order[(index + offset) % len(game.order)]
                     for offset in range(1, len(game.order))]
        scored = []
        for action, trial in outcomes:
            if trial.winner:
                score = (-2, 0, 0, 0)
            elif trial.draw:
                score = (0, 0, 0, 0)
            else:
                threats = [winning_moves(trial, opponent) for opponent in opponents]
                attack = winning_moves(trial, player)
                position = line_score(trial, player)
                position -= 0.6 * sum(line_score(trial, opponent) for opponent in opponents)
                position += 100 * attack + 150 * max(0, attack - 1)
                position += 2 * trial.pops[player]
                # Safety outranks positional gains. If all threats cannot be
                # stopped, prioritize the opponent who actually moves next.
                score = (1 if not any(threats) else -1,
                         -threats[0], -sum(threats), position)
            scored.append((score, action))
        best = max(score for score, action in scored)
        chosen = rng.choice([action for score, action in scored if score == best])
    command, column = chosen
    return {"type": command, "column": column, "move": state["move"]}


def run(args):
    client = communication.Client(args.socket)
    typed = queue.Queue()
    state = None
    input_state = [None, None]  # move number and whose turn when input is typed
    rng = random.Random()
    bot_move_sent = None

    def keyboard():
        while True:
            try:
                line = input()
            except EOFError:
                line = "quit"
            typed.put((line, *input_state))
            if line.strip().lower() == "quit":
                return

    print(f"CONNECT-4 MAYHEM — {args.name}" + (" [tactical bot]" if args.bot else ""), flush=True)
    if not args.bot:
        print(HELP, flush=True)
        threading.Thread(target=keyboard, daemon=True).start()
    client.send({"type": "join", "name": args.name})
    try:
        while True:
            message = client.receive(timeout=0.05)
            if message:
                kind = message.get("type")
                if kind == "state":
                    state = message
                    input_state[:] = [state["move"], state["turn"]]
                    show_board(state, args.name)
                elif kind == "lobby":
                    names = ', '.join(message['names']) or '(empty)'
                    print(f"Lobby: {names} ({len(message['names'])}/{message['capacity']}); "
                          f"{message['seconds']}s left. "
                          + ("Bots will fill empty seats." if message['bots'] else "Three humans required."), flush=True)
                elif kind == "chat":
                    print(f"[{message['channel']}] {message['sender']}: {message['text']}", flush=True)
                elif kind == "disconnected":
                    print("Disconnected from referee.")
                    return
                else:
                    print(message.get("text", ""), flush=True)
                    if kind == "end":
                        return

            if args.bot:
                if (state and not state["winner"] and not state["draw"]
                        and state["turn"] == args.name and state["move"] != bot_move_sent):
                    time.sleep(0.3)
                    client.send(choose_bot_move(state, args.name, rng))
                    bot_move_sent = state["move"]
                continue
            try:
                line, move, turn = typed.get_nowait()
            except queue.Empty:
                continue
            if line.strip().lower() == "quit":
                return
            if line.strip().lower() == "help":
                print(HELP, flush=True)
                continue
            try:
                outgoing = parse_command(line, move)
                if outgoing:
                    if outgoing["type"] in ("drop", "pop") and turn != args.name:
                        raise ValueError("Wait for YOUR TURN before dropping or popping. You can still chat.")
                    client.send(outgoing)
            except ValueError as error:
                print(error, flush=True)
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="display name, e.g. Alice (not a Linux account login)")
    parser.add_argument("--socket", default=communication.default_socket())
    parser.add_argument("--bot", action="store_true", help="play automatically with a tactical strategy")
    args = parser.parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nLeft the game.")
    except OSError as error:
        parser.exit(1, f"Connection failed: {error}\n")


if __name__ == "__main__":
    main()
