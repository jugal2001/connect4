#!/usr/bin/env python3
"""A scrolling text client, or a random bot when started with --bot."""

import argparse
import queue
import random
import threading
import time

import communication

HELP = """drop 4                 Drop in column 4 (a bare number also works).
pop 4                  Remove YOUR bottom disc in column 4; once per game.
say MESSAGE            Talk to everyone.
/w player2 MESSAGE     Whisper / offer a deal to one player.
alliance player2       Invite someone to a private alliance.
alliance accept player1  Accept their latest invitation to you.
alliance say MESSAGE   Talk only to your alliance partner.
alliance leave         Leave and cancel your pending invitations.
alliance               Show your current partner.
look / help / quit     Redisplay board / commands / exit.
Alliances are for chat; only one player can win. Promises are not enforced.
"""


def show_board(state, player):
    symbols = {"player1": "X", "player2": "O", "player3": "@"}
    print("\n    1 2 3 4 5 6 7")
    for row in state["board"]:
        print("  | " + " ".join(row) + " |")
    print("  +---------------+")
    print(f"player1=X  player2=O  player3=@ | You: {player} ({symbols[player]})")
    print("Pop tokens: " + "  ".join(f"{symbols[p]}={tokens}" for p, tokens in state["pops"].items()))
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
            raise ValueError("Wait for three players to join.")
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
            raise ValueError("Use: /w player2 your message")
        return {"type": "chat", "channel": "private", "target": target, "text": body}
    if command == "alliance":
        operation, _, body = text.partition(" ")
        if operation == "say":
            return {"type": "chat", "channel": "alliance", "text": body}
        if operation == "accept":
            return {"type": "alliance", "operation": "accept", "target": body.strip()}
        if operation == "leave":
            return {"type": "alliance", "operation": "leave"}
        if not operation:
            return {"type": "alliance", "operation": "status"}
        return {"type": "alliance", "operation": "invite", "target": text}
    if command == "look":
        return {"type": "look"}
    raise ValueError("Unknown command. Type help.")


def choose_bot_move(state, player, rng):
    """Usually drop; use a legal pop on about one quarter of eligible turns."""
    symbol = {"player1": "X", "player2": "O", "player3": "@"}[player]
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
    rng = random.Random(args.seed)
    bot_move_sent = None
    bot_due = 0
    bot_replied = set()

    def keyboard():
        while True:
            try:
                line = input()
            except EOFError:
                line = "quit"
            typed.put((line, *input_state))
            if line.strip().lower() == "quit":
                return

    print(f"CONNECT-4 MAYHEM — {args.player}" + (" [random bot]" if args.bot else ""), flush=True)
    if not args.bot:
        print(HELP, flush=True)
        threading.Thread(target=keyboard, daemon=True).start()
    client.send({"type": "join", "player": args.player})
    try:
        while True:
            message = client.receive(timeout=0.05)
            if message:
                kind = message.get("type")
                if kind == "state":
                    if not state or message["move"] != state["move"]:
                        bot_due = time.monotonic() + args.delay
                    state = message
                    input_state[:] = [state["move"], state["turn"]]
                    show_board(state, args.player)
                elif kind == "chat":
                    print(f"[{message['channel']}] {message['sender']}: {message['text']}", flush=True)
                    if args.bot and message["channel"] == "private" and message["sender"] not in bot_replied:
                        bot_replied.add(message["sender"])
                        client.send({"type": "chat", "channel": "private", "target": message["sender"],
                                     "text": "I'm a random bot. I accept alliances, but my drops and pops stay random!"})
                elif kind == "disconnected":
                    print("Disconnected from referee.")
                    return
                else:
                    print(message.get("text", ""), flush=True)
                    if kind == "end":
                        return
                    if args.bot and kind == "offer":
                        client.send({"type": "alliance", "operation": "accept", "target": message["sender"]})
                    if args.bot and kind == "allied":
                        client.send({"type": "chat", "channel": "alliance",
                                     "text": "Deal! I'm still choosing random columns."})

            if args.bot:
                if (state and not state["winner"] and not state["draw"]
                        and state["turn"] == args.player and state["move"] != bot_move_sent
                        and time.monotonic() >= bot_due):
                    client.send(choose_bot_move(state, args.player, rng))
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
                    if outgoing["type"] in ("drop", "pop") and turn != args.player:
                        raise ValueError("Wait for YOUR TURN before dropping or popping. You can still chat.")
                    client.send(outgoing)
            except ValueError as error:
                print(error, flush=True)
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--player", choices=("player1", "player2", "player3"), required=True)
    parser.add_argument("--bot", action="store_true", help="choose random legal columns without keyboard input")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--delay", type=float, default=0.6, help="seconds before each bot move")
    args = parser.parse_args()
    if not 0 <= args.delay <= 60:
        parser.error("--delay must be between 0 and 60 seconds")
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nLeft the game.")
    except OSError as error:
        parser.exit(1, f"Connection failed: {error}\n")


if __name__ == "__main__":
    main()
