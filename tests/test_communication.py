import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest

import communication


class CommunicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "test.sock")
        self.server = communication.Server(self.path)
        self.raw = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.raw.connect(self.path)
        self.connection_id, event = self.server.receive(timeout=2)
        self.assertEqual(event["kind"], "connected")

    def tearDown(self):
        self.raw.close()
        self.server.close()
        self.temp.cleanup()

    def test_fragmented_and_coalesced_messages(self):
        self.raw.sendall(b'{"type": "cha')
        self.assertIsNone(self.server.receive(timeout=0.05))
        self.raw.sendall(b't"}\n{"type":"look"}\n')
        for expected in ("chat", "look"):
            _, event = self.server.receive(timeout=2)
            self.assertEqual(event["payload"]["type"], expected)

    def test_malformed_json_disconnects(self):
        self.raw.sendall(b'not json\n')
        _, event = self.server.receive(timeout=2)
        self.assertEqual(event["kind"], "disconnected")

    def test_oversize_message_disconnects(self):
        self.raw.sendall(b'x' * (communication.MAX_MESSAGE + 1))
        _, event = self.server.receive(timeout=2)
        self.assertEqual(event["kind"], "disconnected")

    def test_existing_path_is_preserved(self):
        with self.assertRaises(OSError):
            communication.Server(self.path)
        self.raw.sendall(b'{"type":"look"}\n')
        self.assertEqual(self.server.receive(timeout=2)[1]["kind"], "message")

    def test_concurrent_senders_preserve_message_boundaries(self):
        def send_range(offset):
            for number in range(offset, offset + 20):
                self.server.send(self.connection_id, {"number": number})

        threads = [threading.Thread(target=send_range, args=(i * 20,)) for i in range(3)]
        for thread in threads:
            thread.start()
        self.raw.settimeout(3)
        with self.raw.makefile("rb") as reader:
            received = [json.loads(reader.readline())["number"] for _ in range(60)]
        for thread in threads:
            thread.join(timeout=3)
        self.assertEqual(sorted(received), list(range(60)))


if __name__ == "__main__":
    unittest.main()
