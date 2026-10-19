#!/usr/bin/env python3
"""Connect-4 Mayhem referee. The main thread owns the board and alliances."""

import argparse
import os

import communication

PLAYERS = ("player1", "player2", "player3")
SYMBOLS = dict(zip(PLAYERS, ("X", "O", "@")))
ROWS, COLS = 6, 7


class Game:
    def __init__(self):
        self.board = [["." for _ in range(COLS)] for _ in range(ROWS)]
        self.turn = 0
        self.move = 1
        self.winner = None
        self.draw = False
        self.draw_reason = None
        self.pops = {player: 1 for player in PLAYERS}

    def validate_turn(self, player, column):
        if self.winner or self.draw:
            raise ValueError("The game has finished.")
        if player != PLAYERS[self.turn]:
            raise ValueError(f"It is {PLAYERS[self.turn]}'s turn.")
        if type(column) is not int or not 1 <= column <= COLS:
            raise ValueError("Choose a column from 1 to 7.")

    def drop(self, player, column):
        self.validate_turn(player, column)
        col = column - 1
        if self.board[0][col] != ".":
            raise ValueError("That column is full. Choose another.")
        row = next(r for r in range(ROWS - 1, -1, -1) if self.board[r][col] == ".")
        self.board[row][col] = SYMBOLS[player]
        self.finish_turn()

    def pop(self, player, column):
        self.validate_turn(player, column)
        col = column - 1
        if not self.pops[player]:
            raise ValueError("You already used your pop token.")
        if self.board[-1][col] != SYMBOLS[player]:
            raise ValueError("You can only pop your own bottom disc.")
        # Shift from bottom to top so no disc is overwritten before it moves.
        for row in range(ROWS - 1, 0, -1):
            self.board[row][col] = self.board[row - 1][col]
        self.board[0][col] = "."
        self.pops[player] -= 1
        self.finish_turn()

    def finish_turn(self):
        # A pop can create someone else's line, or multiple winners. Scan the
        # entire small board after either action, using the same simple rule.
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
            self.winner = next(p for p in PLAYERS if SYMBOLS[p] in winning_symbols)
        elif len(winning_symbols) > 1:
            self.draw = True
            self.draw_reason = "Multiple players connected four at once."
        elif all(cell != "." for cell in self.board[0]):
            self.draw = True
            self.draw_reason = "The board is full."
        if not self.winner and not self.draw:
            self.turn = (self.turn + 1) % len(PLAYERS)
            self.move += 1

    def state(self):
        return {"type": "state", "board": self.board, "turn": PLAYERS[self.turn],
                "move": self.move, "winner": self.winner, "draw": self.draw,
                "pops": self.pops, "draw_reason": self.draw_reason}


class Alliances:
    """At most one partner per player. An invitation requires acceptance."""

    def __init__(self):
        self.partners = {}
        self.offers = {}  # recipient -> sender (the latest offer to that player)

    def invite(self, sender, target):
        if target not in PLAYERS or sender == target:
            raise ValueError("Invite one of the other two players.")
        if sender in self.partners or target in self.partners:
            raise ValueError("An existing alliance must be left first.")
        self.offers[target] = sender

    def accept(self, player, sender):
        if self.offers.get(player) != sender or sender not in PLAYERS:
            raise ValueError("No current invitation from that player.")
        if player in self.partners or sender in self.partners:
            raise ValueError("One of you already has a partner.")
        self.partners[player] = sender
        self.partners[sender] = player
        self.offers = {p: s for p, s in self.offers.items()
                       if p not in (player, sender) and s not in (player, sender)}

    def leave(self, player):
        partner = self.partners.pop(player, None)
        if partner:
            del self.partners[partner]
        self.offers = {p: s for p, s in self.offers.items() if player not in (p, s)}
        return partner


def run(args):
    transport = communication.Server(args.socket)
    identities = {}
    players = {}
    game = None
    alliances = Alliances()

    def reply(connection_id, text, kind="info"):
        transport.send(connection_id, {"type": kind, "text": text})

    print(f"Waiting for three players at {args.socket}", flush=True)
    print("DEMO: shared Linux users allowed" if args.demo else
          "CLASS: three distinct player UIDs required", flush=True)
    try:
        while True:
            connection_id, event = transport.receive()
            kind = event["kind"]
            if kind == "connected":
                if game:
                    reply(connection_id, "A match is already running.", "error")
                    transport.disconnect(connection_id)
                else:
                    identities[connection_id] = event
                    reply(connection_id, "Connected. Waiting for three players.")
                continue
            player = next((p for p, c in players.items() if c == connection_id), None)
            if kind == "disconnected":
                identities.pop(connection_id, None)
                if player:
                    del players[player]
                    partner = alliances.leave(player)
                    if partner:
                        reply(players[partner], "Your partner disconnected. Alliance ended.")
                    if game:
                        transport.broadcast({"type": "end", "text": f"Match cancelled: {player} disconnected."})
                        return
                    transport.broadcast({"type": "info", "text": f"{player} left the lobby."})
                continue
            if connection_id not in identities:
                continue
            message = event["payload"]
            action = message.get("type")
            try:
                if action == "join" and not player:
                    name = message.get("player")
                    if not isinstance(name, str) or name not in PLAYERS or name in players:
                        reply(connection_id, "Choose an unused slot: player1, player2, player3.", "error")
                        transport.disconnect(connection_id)
                        continue
                    uid = identities[connection_id]["uid"]
                    occupied = {identities[c]["uid"] for c in players.values()}
                    if not args.demo and (uid == os.getuid() or uid in occupied):
                        reply(connection_id, "Each player needs a distinct Linux user, separate from the referee. Use --demo for testing.", "error")
                        transport.disconnect(connection_id)
                        continue
                    players[name] = connection_id
                    print(f"{name}: {identities[connection_id]['user']} (UID {uid})", flush=True)
                    transport.broadcast({"type": "info", "text": f"{name} joined ({len(players)}/3)."})
                    if len(players) == 3:
                        game = Game()
                        transport.broadcast(game.state())
                    continue
                if not player:
                    raise ValueError("Join the lobby first.")
                if action in ("drop", "pop"):
                    if not game:
                        raise ValueError("Wait for all three players.")
                    if message.get("move") != game.move:
                        raise ValueError("That command used an older board. Type look and try again.")
                    if action == "pop":
                        game.pop(player, message.get("column"))
                        description = "popped their bottom disc from"
                    else:
                        game.drop(player, message.get("column"))
                        description = "dropped in"
                    transport.broadcast({"type": "info", "text": f"{player} ({SYMBOLS[player]}) {description} column {message['column']}."})
                    transport.broadcast(game.state())
                    if game.winner or game.draw:
                        result = f"{game.winner} wins! Four connected!" if game.winner else f"Draw! {game.draw_reason}"
                        transport.broadcast({"type": "end", "text": result})
                        print(result, flush=True)
                        return
                elif action == "look":
                    if game:
                        transport.send(connection_id, game.state())
                    else:
                        reply(connection_id, f"Waiting for players ({len(players)}/3).")
                elif action == "alliance":
                    operation = message.get("operation")
                    target = message.get("target")
                    if operation in ("invite", "accept"):
                        if not isinstance(target, str) or target not in players:
                            raise ValueError("Choose a connected player.")
                        if operation == "invite":
                            alliances.invite(player, target)
                            # A deal offer is a unicast to the intended recipient.
                            transport.send(players[target], {"type": "offer", "sender": player,
                                "text": f"{player} offers an alliance. Use: alliance accept {player}"})
                            reply(connection_id, f"Offer sent to {target}.")
                        else:
                            alliances.accept(player, target)
                            transport.multicast([connection_id, players[target]], {
                                "type": "allied", "members": [player, target],
                                "text": f"Alliance formed: {player} + {target}. Use: alliance say MESSAGE"})
                    elif operation == "leave":
                        partner = alliances.leave(player)
                        reply(connection_id, "You left the alliance and cancelled pending offers.")
                        if partner:
                            reply(players[partner], f"{player} left your alliance.")
                    elif operation == "status":
                        reply(connection_id, f"Partner: {alliances.partners.get(player, 'none')}.")
                    else:
                        raise ValueError("Unknown alliance command.")
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
                        if not isinstance(target, str) or target not in players or target == player:
                            raise ValueError("Whisper to another connected player.")
                        transport.send(players[target], chat)
                        reply(connection_id, f"Whisper to {target}: {text}")
                    elif channel == "alliance":
                        partner = alliances.partners.get(player)
                        if not partner:
                            raise ValueError("Form an alliance first; use alliance player2.")
                        transport.multicast([connection_id, players[partner]], chat)
                    else:
                        raise ValueError("Unknown chat channel.")
                else:
                    raise ValueError("Unknown command. Type help.")
            except ValueError as error:
                reply(connection_id, str(error), "error")
    finally:
        transport.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--demo", action="store_true", help="allow shared UIDs for testing")
    args = parser.parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nReferee stopped.")
    except OSError as error:
        parser.exit(1, f"Cannot run referee: {error}\n")


if __name__ == "__main__":
    main()
