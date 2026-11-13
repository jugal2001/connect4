import json
import socket
import threading
import time
import unittest

import communication


class CommunicationTests(unittest.TestCase):
    def setUp(self):
        # Short heartbeat so the timeout tests finish quickly.
        self.saved = communication.HEARTBEAT_INTERVAL, communication.HEARTBEAT_TIMEOUT
        communication.HEARTBEAT_INTERVAL, communication.HEARTBEAT_TIMEOUT = 0.1, 0.5
        self.server = communication.Server("127.0.0.1", 0)
        self.raw = socket.create_connection(("127.0.0.1", self.server.port))
        self.connection_id, event = self.server.receive(timeout=2)
        self.assertEqual(event, {"kind": "connected", "address": "127.0.0.1"})

    def tearDown(self):
        self.raw.close()
        self.server.close()
        communication.HEARTBEAT_INTERVAL, communication.HEARTBEAT_TIMEOUT = self.saved

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

    def test_port_in_use_is_reported(self):
        with self.assertRaises(OSError):
            communication.Server("127.0.0.1", self.server.port)

    def test_concurrent_senders_preserve_message_boundaries(self):
        def send_range(offset):
            for number in range(offset, offset + 20):
                self.server.send(self.connection_id, {"number": number})

        threads = [threading.Thread(target=send_range, args=(i * 20,)) for i in range(3)]
        for thread in threads:
            thread.start()
        self.raw.settimeout(3)
        received = []
        with self.raw.makefile("rb") as reader:
            while len(received) < 60:
                message = json.loads(reader.readline())
                if message != communication.PING:
                    received.append(message["number"])
        for thread in threads:
            thread.join(timeout=3)
        self.assertEqual(sorted(received), list(range(60)))

    def test_silent_peer_times_out(self):
        # The raw socket stays open but never sends: a dead link looks like this.
        started = time.monotonic()
        _, event = self.server.receive(timeout=3)
        self.assertEqual(event["kind"], "disconnected")
        self.assertGreaterEqual(time.monotonic() - started, 0.4)

    def test_pings_keep_a_quiet_connection_alive_and_stay_hidden(self):
        client = communication.Client("127.0.0.1", self.server.port)
        try:
            connection_id, event = self.server.receive(timeout=2)
            self.assertEqual(event["kind"], "connected")
            time.sleep(1.2)  # more than two timeouts with no game traffic
            self.assertIsNone(client.receive(timeout=0.05))
            self.assertTrue(self.server.send(connection_id, {"type": "hello"}))
            self.assertEqual(client.receive(timeout=2), {"type": "hello"})
        finally:
            client.close()

    def test_client_detects_silent_server(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        try:
            client = communication.Client("127.0.0.1", listener.getsockname()[1])
            accepted, _ = listener.accept()  # accepts, then never sends a ping
            self.assertEqual(client.receive(timeout=3), {"type": "disconnected"})
            accepted.close()
        finally:
            listener.close()

    def test_peer_that_stops_reading_is_dropped(self):
        # The raw socket never reads, so its buffers fill and a send must time out.
        big = {"text": "x" * 8000}
        started = time.monotonic()
        while self.server.send(self.connection_id, big):
            self.assertLess(time.monotonic() - started, 10)
        self.assertLess(time.monotonic() - started, 10)


if __name__ == "__main__":
    unittest.main()
