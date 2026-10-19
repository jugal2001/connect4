"""All interprocess communication: UNIX stream sockets and JSON messages.

Game files use Server/Client; they never open sockets themselves. Each socket
has a reader thread, while queues hand messages to the main game/UI thread.
"""

import json
import os
import pwd
import queue
import socket
import struct
import threading

def default_socket():
    """Predictable per-user demo address shared by the launcher and named clients."""
    return f"/tmp/connect4-mayhem-{os.getuid()}/game.sock"


MAX_MESSAGE = 8192


class _Connection:
    """A stream needs framing: one UTF-8 JSON object followed by a newline."""

    def __init__(self, sock):
        self.sock = sock
        self.reader = sock.makefile("rb")
        self.write_lock = threading.Lock()

    def send(self, message):
        data = (json.dumps(message, ensure_ascii=True) + "\n").encode("utf-8")
        if len(data) > MAX_MESSAGE:
            raise ValueError("Message is too long")
        # A broadcast and a private reply must not interleave their bytes.
        with self.write_lock:
            self.sock.sendall(data)

    def receive(self):
        data = self.reader.readline(MAX_MESSAGE + 1)
        if not data:
            raise EOFError("Peer disconnected")
        if len(data) > MAX_MESSAGE or not data.endswith(b"\n"):
            raise ValueError("Message is too long or missing its newline")
        message = json.loads(data)
        if not isinstance(message, dict):
            raise ValueError("Messages must be JSON objects")
        return message

    def close(self):
        # shutdown wakes a thread blocked in receive(). That thread closes its
        # buffered reader in finally, avoiding a lock conflict with readline.
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


class Server:
    """Accept local connections and deliver (connection_id, event) pairs.

    Events have kind connected/message/disconnected. Message events contain
    a payload dictionary. UID/user on connected events come from the kernel,
    never from a client's claimed identity.
    """

    def __init__(self, path):
        self.path = path
        self.events = queue.Queue()
        self.peers = {}
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # Do not unlink a preexisting path: it may belong to a running game.
        try:
            self.listener.bind(path)
        except OSError:
            self.listener.close()
            raise
        os.chmod(path, 0o660)
        self.listener.listen(8)
        self.listener.settimeout(0.5)
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        next_id = 1
        while not self.closed.is_set():
            try:
                sock, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            # Linux SO_PEERCRED returns the connecting process's PID/UID/GID.
            _, uid, _ = struct.unpack(
                "3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            )
            try:
                user = pwd.getpwuid(uid).pw_name
            except KeyError:
                user = str(uid)
            peer = _Connection(sock)
            with self.lock:
                if self.closed.is_set():
                    peer.close()
                    peer.reader.close()
                    break
                connection_id = next_id
                next_id += 1
                self.peers[connection_id] = peer
            self.events.put((connection_id, {
                "kind": "connected", "uid": uid, "user": user,
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
            peer.reader.close()
            with self.lock:
                self.peers.pop(connection_id, None)
            self.events.put((connection_id, {"kind": "disconnected"}))

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
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass


class Client:
    """Connect to a server; a reader thread receives while the user types."""

    def __init__(self, path):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(path)
        except OSError:
            sock.close()
            raise
        self.peer = _Connection(sock)
        self.events = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                self.events.put(self.peer.receive())
        except (OSError, EOFError, ValueError):
            pass
        finally:
            self.peer.close()
            self.peer.reader.close()
            self.events.put({"type": "disconnected"})

    def send(self, message):
        self.peer.send(message)

    def receive(self, timeout=None):
        """Return the next message, or None after timeout seconds."""
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        self.peer.close()
