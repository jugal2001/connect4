"""Real referee subprocess, real UNIX sockets, and real independent bots."""

from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import communication

ROOT = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "game.sock")
        self.clients = []
        self.children = []
        self.logs = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        for process in self.children:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
        for log in self.logs:
            log.close()
        self.temp.cleanup()

    def process(self, arguments):
        log = tempfile.TemporaryFile(mode="w+")
        self.logs.append(log)
        process = subprocess.Popen([sys.executable, "-u"] + arguments, cwd=ROOT, stdout=log, stderr=log)
        self.children.append(process)
        return process

    def start(self, demo=True):
        self.server = self.process(["server.py", "--socket", self.path] + (["--demo"] if demo else []))
        deadline = time.monotonic() + 5
        while not Path(self.path).exists():
            if self.server.poll() is not None or time.monotonic() > deadline:
                self.logs[0].seek(0)
                self.fail(self.logs[0].read())
            time.sleep(0.01)

    def join(self, name):
        client = communication.Client(self.path)
        self.clients.append(client)
        client.send({"type": "join", "player": name})
        return client

    def until(self, client, kind, predicate=lambda message: True):
        deadline = time.monotonic() + 5
        seen = []
        while time.monotonic() < deadline:
            message = client.receive(timeout=0.05)
            if message:
                seen.append(message)
                if message.get("type") == kind and predicate(message):
                    return message
        self.fail(f"Missing {kind}: {seen}")

    def three(self):
        clients = [self.join(f"player{i}") for i in range(1, 4)]
        for client in clients:
            self.until(client, "state")
        return clients

    def assert_quiet(self, client):
        self.assertIsNone(client.receive(timeout=0.1))

    def test_board_broadcast_turn_validation_and_complete_win(self):
        self.start()
        clients = self.three()
        clients[1].send({"type": "drop", "move": 1, "column": 1})
        self.assertIn("player1", self.until(clients[1], "error")["text"])
        clients[0].send({"type": "drop", "move": 0, "column": 1})
        self.until(clients[0], "error")
        for number in range(1, 11):
            index = (number - 1) % 3
            clients[index].send({"type": "drop", "move": number, "column": index + 1})
            states = [self.until(client, "state") for client in clients]
            self.assertEqual(states[0], states[1])
            self.assertEqual(states[1], states[2])
        for client in clients:
            self.assertIn("player1 wins", self.until(client, "end")["text"])
        self.assertEqual(self.server.wait(timeout=5), 0)

    def test_whispers_alliance_consent_privacy_and_leave(self):
        self.start()
        a, b, c = self.three()
        a.send({"type": "chat", "channel": "private", "target": "player2", "text": "deal?", "sender": "player3"})
        self.assertEqual(self.until(b, "chat")["sender"], "player1")
        self.until(a, "info")
        self.assert_quiet(c)
        a.send({"type": "alliance", "operation": "invite", "target": "player2"})
        self.until(b, "offer")
        self.until(a, "info")
        self.assert_quiet(c)
        a.send({"type": "chat", "channel": "alliance", "text": "not accepted yet"})
        self.until(a, "error")
        b.send({"type": "alliance", "operation": "accept", "target": "player1"})
        self.until(a, "allied")
        self.until(b, "allied")
        a.send({"type": "chat", "channel": "alliance", "text": "secret", "members": ["player3"]})
        self.assertEqual(self.until(a, "chat")["text"], "secret")
        self.assertEqual(self.until(b, "chat")["text"], "secret")
        self.assert_quiet(c)
        c.send({"type": "chat", "channel": "alliance", "text": "intrude"})
        self.until(c, "error")
        b.send({"type": "alliance", "operation": "leave"})
        self.until(a, "info")
        self.until(b, "info")
        a.send({"type": "chat", "channel": "alliance", "text": "old partner"})
        self.until(a, "error")
        c.send({"type": "chat", "channel": "all", "text": "public"})
        for client in (a, b, c):
            self.assertEqual(self.until(client, "chat")["text"], "public")

    def test_malformed_fields_and_disconnect(self):
        self.start()
        a, b, c = self.three()
        for message in (
            {"type": "drop", "column": [], "move": 1},
            {"type": "alliance", "operation": "accept", "target": []},
            {"type": "chat", "channel": "private", "target": [], "text": "hi"},
            {"type": "chat", "channel": "all", "text": "\u001b[2J"},
        ):
            a.send(message)
            self.until(a, "error")
        b.close()
        self.assertIn("cancelled", self.until(a, "end")["text"])
        self.assertIn("cancelled", self.until(c, "end")["text"])
        self.assertEqual(self.server.wait(timeout=5), 0)

    def test_class_mode_rejects_referee_uid(self):
        self.start(demo=False)
        a = self.join("player1")
        self.assertIn("distinct Linux user", self.until(a, "error")["text"])
        self.until(a, "disconnected")

    def test_duplicate_slot_and_fourth_client_rejected(self):
        self.start()
        a = self.join("player1")
        self.until(a, "info", lambda m: "joined" in m["text"])
        duplicate = self.join("player1")
        self.until(duplicate, "error")
        self.until(duplicate, "disconnected")
        b, c = self.join("player2"), self.join("player3")
        for client in (a, b, c):
            self.until(client, "state")
        fourth = self.join("player3")
        self.until(fourth, "error")
        self.until(fourth, "disconnected")

    def test_three_independent_bots_finish_game(self):
        self.start()
        bots = [self.process(["client.py", "--socket", self.path, "--player", f"player{i}",
                              "--bot", "--delay", "0", "--seed", str(i)]) for i in range(1, 4)]
        self.assertEqual(self.server.wait(timeout=10), 0)
        for bot, log in zip(bots, self.logs[1:]):
            self.assertEqual(bot.wait(timeout=5), 0)
            log.seek(0)
            text = log.read()
            self.assertTrue("wins!" in text or "Draw!" in text, text)
            self.assertNotIn("Traceback", text)

    def test_bot_accepts_human_alliance(self):
        self.start()
        a, c = self.join("player1"), self.join("player3")
        self.process(["client.py", "--socket", self.path, "--player", "player2", "--bot", "--delay", "0"])
        self.until(a, "state")
        self.until(c, "state")
        a.send({"type": "alliance", "operation": "invite", "target": "player2"})
        self.until(a, "allied")
        self.assertIn("random columns", self.until(a, "chat")["text"])
        self.assert_quiet(c)


if __name__ == "__main__":
    unittest.main()
