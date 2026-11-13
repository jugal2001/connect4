"""End-to-end tests over real TCP sockets: tokens, privacy, bots, lost players."""
from pathlib import Path
import os
import random
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import communication
from client import choose_bot_move

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['Alice', 'Bob', 'Cara']


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.clients = []
        self.log = tempfile.NamedTemporaryFile(mode='w+')
        self.server = None

    def tearDown(self):
        for client in self.clients:
            client.close()
        if self.server:
            if self.server.poll() is None:
                self.server.terminate()
            self.server.wait(timeout=6)
        self.log.close()

    def read_log(self):
        return Path(self.log.name).read_text()

    def start(self, *options, lobby=0.8):
        with socket.socket() as probe:  # pick a free port
            probe.bind(('127.0.0.1', 0))
            self.port = probe.getsockname()[1]
        command = [sys.executable, '-u', 'server.py', '--bind', '127.0.0.1',
                   '--port', str(self.port), '--lobby', str(lobby), *options]
        self.server = subprocess.Popen(command, cwd=ROOT, stdout=self.log, stderr=self.log)
        deadline = time.monotonic() + 5
        while 'Referee listening' not in self.read_log() or (
                'C4_TOKENS' not in os.environ and self.read_log().count('--token') < 3):
            if self.server.poll() is not None or time.monotonic() > deadline:
                self.fail(self.read_log())
            time.sleep(0.01)
        self.tokens = re.findall(r'--token (\w+)', self.read_log())

    def join(self, name, token):
        client = communication.Client('127.0.0.1', self.port)
        self.clients.append(client)
        client.send({'type': 'join', 'name': name, 'token': token})
        return client

    def until(self, client, kind, predicate=lambda m: True):
        deadline = time.monotonic() + 7
        seen = []
        while time.monotonic() < deadline:
            message = client.receive(timeout=0.05)
            if message:
                seen.append(message)
                if message.get('type') == kind and predicate(message):
                    return message
        self.fail(f'Missing {kind}: {seen}')

    def three(self):
        clients = {name: self.join(name, token) for name, token in zip(NAMES, self.tokens)}
        states = [self.until(c, 'state') for c in clients.values()]
        self.assertTrue(all(s == states[0] for s in states))
        return clients, states[0]

    def test_three_players_start_at_once_and_one_wins(self):
        self.start(lobby=30)
        started = time.monotonic()
        clients, state = self.three()
        self.assertLess(time.monotonic() - started, 5)  # did not wait out the lobby
        for col in [1, 7, 6, 2, 7, 6, 3, 7, 6, 4]:
            clients[state['turn']].send({'type': 'drop', 'column': col, 'move': state['move']})
            states = [self.until(c, 'state') for c in clients.values()]
            self.assertTrue(all(s == states[0] for s in states))
            state = states[0]
        for client in clients.values():
            self.assertIn(state['order'][0] + ' (X) wins', self.until(client, 'end')['text'])
        self.assertEqual(self.server.wait(timeout=5), 0)

    def test_tokens_are_required_and_single_use(self):
        self.start(lobby=3)
        for token in ['wrong', None, 7]:
            rejected = self.join('Mallory', token)
            self.assertIn('token', self.until(rejected, 'error')['text'])
            self.until(rejected, 'disconnected')
        alice = self.join('Alice', self.tokens[0])
        self.until(alice, 'info')
        reused = self.join('Bob', self.tokens[0])
        self.assertIn('token', self.until(reused, 'error')['text'])
        # A rejected name does not burn the token.
        for name in ['alice', 'Bot1', 'two names', []]:
            rejected = self.join(name, self.tokens[1])
            self.until(rejected, 'error')
            self.until(rejected, 'disconnected')
        bob = self.join('Bob', self.tokens[1])
        self.until(bob, 'info')

    def test_whisper_is_unicast_and_say_is_broadcast(self):
        self.start()
        clients, _ = self.three()
        clients['Alice'].send({'type': 'chat', 'channel': 'private', 'target': 'bob',
                               'text': 'secret', 'sender': 'Cara'})
        message = self.until(clients['Bob'], 'chat')
        self.assertEqual((message['sender'], message['text']), ('Alice', 'secret'))
        self.until(clients['Alice'], 'info')
        self.assertIsNone(clients['Cara'].receive(timeout=0.1))
        clients['Bob'].send({'type': 'chat', 'channel': 'all', 'text': 'public'})
        for client in clients.values():
            self.assertEqual(self.until(client, 'chat')['text'], 'public')

    def test_bots_fill_empty_seats_and_finish_a_game(self):
        self.start('--bots', lobby=30)
        human = self.join('Tester', self.tokens[0])
        state = self.until(human, 'state')
        self.assertEqual(set(state['symbols']), {'Tester', 'Bot1', 'Bot2'})
        late = communication.Client('127.0.0.1', self.port)
        self.clients.append(late)
        self.assertIn('already running', self.until(late, 'error')['text'])
        rng = random.Random(3)
        deadline = time.monotonic() + 30
        while not state['winner'] and not state['draw']:
            self.assertLess(time.monotonic(), deadline)
            if state['turn'] == 'Tester':
                human.send(choose_bot_move(state, 'Tester', rng))
            state = self.until(human, 'state')
        self.until(human, 'end')
        self.assertEqual(self.server.wait(timeout=5), 0)

    def test_launcher_supplied_tokens(self):
        os.environ['C4_TOKENS'] = 'one,two,three'
        self.addCleanup(os.environ.pop, 'C4_TOKENS')
        self.start()
        self.until(self.join('Alice', 'two'), 'info')

    def test_nobody_joins(self):
        self.start(lobby=0.2)
        self.assertEqual(self.server.wait(timeout=5), 0)
        self.assertIn('nobody joined', self.read_log())

    def test_closed_connection_cancels_match(self):
        self.start()
        clients, _ = self.three()
        clients['Cara'].close()
        self.assertIn('Cara', self.until(clients['Alice'], 'end')['text'])

    def test_unreachable_player_cancels_match(self):
        # Cara's connection stays open but goes silent, as when a link fails.
        self.start()
        raw = socket.create_connection(('127.0.0.1', self.port))
        self.addCleanup(raw.close)
        raw.sendall(b'{"type":"join","name":"Cara","token":"%s"}\n' % self.tokens[2].encode())
        alice, bob = (self.join(n, t) for n, t in zip(NAMES[:2], self.tokens))
        self.until(alice, 'state')
        started = time.monotonic()
        deadline = started + communication.HEARTBEAT_TIMEOUT + 4
        while True:
            self.assertLess(time.monotonic(), deadline)
            message = alice.receive(timeout=0.1)
            if message and message.get('type') == 'end':
                break
        self.assertIn('Cara', message['text'])
        self.assertIn('unreachable', self.until(bob, 'end')['text'])

    def test_stale_move_and_turn_checks(self):
        self.start()
        clients, state = self.three()
        order = state['order']
        clients[order[1]].send({'type': 'pop', 'column': 1, 'move': 1})
        self.until(clients[order[1]], 'error')
        for action, column in [('drop', 1), ('drop', 1), ('drop', 2), ('pop', 1)]:
            clients[state['turn']].send({'type': action, 'column': column, 'move': state['move']})
            state = [self.until(c, 'state') for c in clients.values()][0]
        self.assertEqual(state['board'][5][0], 'O')
        self.assertEqual(state['pops'][order[0]], 0)
        clients[order[1]].send({'type': 'drop', 'column': 2, 'move': 1})
        self.assertIn('older board', self.until(clients[order[1]], 'error')['text'])


if __name__ == '__main__':
    unittest.main()
