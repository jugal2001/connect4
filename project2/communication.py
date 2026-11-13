"""All communication between machines: TCP sockets carrying JSON messages.

Game files use Server/Client; they never open sockets themselves. Each
connection has a reader thread, and queues hand messages to the game thread.

A broken network path does not close a TCP connection, so both sides send a
ping every HEARTBEAT_INTERVAL seconds. A peer that is silent for
HEARTBEAT_TIMEOUT seconds is treated as disconnected. The same timeout bounds
every send, so a peer that stops reading cannot block the sender forever.
"""

import json
import queue
import socket
import threading

DEFAULT_PORT = 5544
MAX_MESSAGE = 8192
HEARTBEAT_INTERVAL = 2.0
HEARTBEAT_TIMEOUT = 6.0
PING = {"type": "ping"}  # consumed inside this file, never seen by the game


def local_address():
    """Best guess at the address other machines use to reach this one."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # picks a route; UDP sends nothing here
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


class _Connection:
    """TCP is a byte stream, so frame it: one JSON object per line."""

    def __init__(self, sock):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # One timeout covers both directions: recv() gives up on a silent
        # peer, and sendall() gives up on a peer that is not reading.
        sock.settimeout(HEARTBEAT_TIMEOUT)
        self.sock = sock
        self.buffer = b""
        self.write_lock = threading.Lock()

    def send(self, message):
        data = (json.dumps(message, ensure_ascii=True) + "\n").encode("utf-8")
        if len(data) > MAX_MESSAGE:
            raise ValueError("Message is too long")
        # A broadcast, a private reply and a ping must not interleave bytes.
        with self.write_lock:
            self.sock.sendall(data)

    def receive(self):
        """Return the next game message. Raises when the peer is gone or silent."""
        while True:
            while b"\n" not in self.buffer:
                if len(self.buffer) >= MAX_MESSAGE:
                    raise ValueError("Message is too long")
                chunk = self.sock.recv(4096)  # socket.timeout after silence
                if not chunk:
                    raise EOFError("Peer disconnected")
                self.buffer += chunk
            line, _, self.buffer = self.buffer.partition(b"\n")
            if len(line) >= MAX_MESSAGE:
                raise ValueError("Message is too long")
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("Messages must be JSON objects")
            if message != PING:
                return message

    def close(self):
        # shutdown wakes a thread blocked in recv() on this socket.
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


class Server:
    """Listen on host:port and deliver (connection_id, event) pairs.

    Events have kind connected/message/disconnected. A connected event carries
    the peer's IP address; message events carry a payload dictionary.
    """

    def __init__(self, host, port=DEFAULT_PORT):
        self.events = queue.Queue()
        self.peers = {}
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.listener.bind((host, port))
        except OSError:
            self.listener.close()
            raise
        self.port = self.listener.getsockname()[1]  # useful when port was 0
        self.listener.listen(8)
        self.listener.settimeout(0.5)
        threading.Thread(target=self._accept, daemon=True).start()
        threading.Thread(target=self._heartbeat, daemon=True).start()

    def _accept(self):
        next_id = 1
        while not self.closed.is_set():
            try:
                sock, address = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            peer = _Connection(sock)
            with self.lock:
                if self.closed.is_set():
                    peer.close()
                    break
                connection_id = next_id
                next_id += 1
                self.peers[connection_id] = peer
            self.events.put((connection_id, {
                "kind": "connected", "address": address[0],
            }))
            threading.Thread(
                target=self._read, args=(connection_id, peer), daemon=True
            ).start()

    def _read(self, connection_id, peer):
        try:
            while not self.closed.is_set():
                self.events.put((connection_id, {
                    "kind": "message", "payload": peer.receive(),
                }))
        except (OSError, EOFError, ValueError):
            pass
        finally:
            peer.close()
            with self.lock:
                self.peers.pop(connection_id, None)
            self.events.put((connection_id, {"kind": "disconnected"}))

    def _heartbeat(self):
        while not self.closed.wait(HEARTBEAT_INTERVAL):
            self.broadcast(PING)

    def receive(self, timeout=None):
        """Return the next (id, event), or None after timeout seconds."""
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def send(self, connection_id, message):
        """Unicast. Return False if that connection has gone away."""
        with self.lock:
            peer = self.peers.get(connection_id)
        if peer is None:
            return False
        try:
            peer.send(message)
            return True
        except OSError:
            # Includes a send timeout. A partial write would corrupt the
            # framing, so the connection is dropped rather than reused.
            peer.close()
            return False

    def multicast(self, connection_ids, message):
        """Application-level multicast: deliver only to the listed peers."""
        for connection_id in list(connection_ids):
            self.send(connection_id, message)

    def broadcast(self, message):
        """Deliver to every connected peer."""
        with self.lock:
            connection_ids = list(self.peers)
        self.multicast(connection_ids, message)

    def disconnect(self, connection_id):
        with self.lock:
            peer = self.peers.get(connection_id)
        if peer:
            peer.close()

    def close(self):
        self.closed.set()
        self.listener.close()
        with self.lock:
            peers = list(self.peers.values())
        for peer in peers:
            peer.close()


class Client:
    """Connect to a server; a reader thread receives while the user types."""

    def __init__(self, host, port=DEFAULT_PORT):
        sock = socket.create_connection((host, port), timeout=HEARTBEAT_TIMEOUT)
        self.peer = _Connection(sock)
        self.events = queue.Queue()
        self.closed = threading.Event()
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._heartbeat, daemon=True).start()

    def _read(self):
        try:
            while True:
                self.events.put(self.peer.receive())
        except (OSError, EOFError, ValueError):
            pass
        finally:
            self.close()
            self.events.put({"type": "disconnected"})

    def _heartbeat(self):
        while not self.closed.wait(HEARTBEAT_INTERVAL):
            try:
                self.peer.send(PING)
            except OSError:
                self.close()

    def send(self, message):
        self.peer.send(message)

    def receive(self, timeout=None):
        """Return the next message, or None after timeout seconds."""
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        self.closed.set()
        self.peer.close()
