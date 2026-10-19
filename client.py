#!/usr/bin/env python3
"""A scrolling text client, or a random bot when started with --bot."""

import argparse
import queue
import random
import threading
import time

import communication

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


def choose_bot_move(state, player, rng):
    """Usually drop; use a legal pop on about one quarter of eligible turns."""
    symbol = state["symbols"][player]
    pops = [i + 1 for i, cell in enumerate(state["board"][-1])
            if cell == symbol and state["pops"][player]]
    if pops and rng.random() < 0.25:
        return {"type": "pop", "column": rng.choice(pops), "move": state["move"]}
    drops = [i + 1 for i, cell in enumerate(state["board"][0]) if cell == "."]
    return {"type": "drop", "column": rng.choice(drops), "move": state["move"]}


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

    print(f"CONNECT-4 MAYHEM — {args.name}" + (" [random bot]" if args.bot else ""), flush=True)
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
    parser.add_argument("--bot", action="store_true", help="choose random legal columns without keyboard input")
    args = parser.parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nLeft the game.")
    except OSError as error:
        parser.exit(1, f"Connection failed: {error}\n")


if __name__ == "__main__":
    main()
