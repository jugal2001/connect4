"""Real socket tests: timed joining, shared team results, privacy, and bot fill."""
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
import unittest

import communication
from client import choose_bot_move

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['Alice', 'Bob', 'Cara', 'Dan']


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'game.sock')
        self.clients = []
        self.log = tempfile.TemporaryFile(mode='w+')
        self.server = None

    def tearDown(self):
        for client in self.clients:
            client.close()
        if self.server:
            if self.server.poll() is None:
                self.server.terminate()
            self.server.wait(timeout=6)
        self.log.close()
        self.temp.cleanup()

    def start(self, bots=False, demo=True, seconds=0.6):
        command = [sys.executable, '-u', 'server.py', '--socket', self.path,
                   '--lobby-seconds', str(seconds), '--bot-delay', '0', '--seed', '42']
        if demo:
            command.append('--demo')
        if bots:
            command.append('--bots')
        self.started = time.monotonic()
        self.server = subprocess.Popen(command, cwd=ROOT, stdout=self.log, stderr=self.log)
        deadline = time.monotonic()+5
        while not Path(self.path).exists():
            if self.server.poll() is not None or time.monotonic() > deadline:
                self.log.seek(0)
                self.fail(self.log.read())
            time.sleep(0.01)

    def join(self, name):
        client = communication.Client(self.path)
        self.clients.append(client)
        client.send({'type': 'join', 'name': name})
        return client

    def until(self, client, kind, predicate=lambda m: True):
        deadline = time.monotonic()+7
        seen = []
        while time.monotonic() < deadline:
            message = client.receive(timeout=0.05)
            if message:
                seen.append(message)
                if message.get('type') == kind and predicate(message):
                    return message
        self.fail(f'Missing {kind}: {seen}')

    def four(self):
        clients = {name: self.join(name) for name in NAMES}
        states = [self.until(c, 'state') for c in clients.values()]
        self.assertTrue(all(s == states[0] for s in states))
        return clients, states[0]

    def test_full_lobby_waits_then_shared_team_win(self):
        self.start(seconds=0.8)
        clients, state = self.four()
        self.assertGreaterEqual(time.monotonic()-self.started, 0.8)
        self.assertEqual([state['symbols'][p] for p in state['order']], ['X','O','X','O'])
        for col in [1, 7, 2, 7, 3, 6, 4]:
            clients[state['turn']].send({'type':'drop', 'column':col, 'move':state['move']})
            states = [self.until(c, 'state') for c in clients.values()]
            self.assertTrue(all(s == states[0] for s in states))
            state = states[0]
        for client in clients.values():
            result = self.until(client, 'end')['text']
            self.assertIn('Team X wins', result)
            for name in state['teams']['X']:
                self.assertIn(name, result)
        self.assertEqual(self.server.wait(timeout=5), 0)

    def test_team_multicast_and_whisper_privacy(self):
        self.start()
        clients, state = self.four()
        sender, partner = state['teams']['X']
        opponents = state['teams']['O']
        clients[sender].send({'type':'chat', 'channel':'team', 'text':'secret', 'sender':opponents[0], 'members':opponents})
        for name in [sender, partner]:
            self.assertEqual(self.until(clients[name], 'chat')['sender'], sender)
        for name in opponents:
            self.assertIsNone(clients[name].receive(timeout=0.1))
        clients[sender].send({'type':'chat', 'channel':'private', 'target':opponents[0].lower(), 'text':'hello'})
        self.assertEqual(self.until(clients[opponents[0]], 'chat')['text'], 'hello')
        self.until(clients[sender], 'info')
        self.assertIsNone(clients[partner].receive(timeout=0.1))
        clients[sender].send({'type':'alliance'})
        self.until(clients[sender], 'error')
        clients[partner].close()
        self.assertIn('cancelled', self.until(clients[sender], 'end')['text'])

    def test_one_named_human_three_bot_processes_complete(self):
        self.start(bots=True)
        human = self.join('Tester')
        state = self.until(human, 'state')
        self.assertEqual(set(state['symbols']), {'Tester','Bot1','Bot2','Bot3'})
        rng = random.Random(3)
        deadline = time.monotonic()+10
        while not state['winner'] and not state['draw']:
            self.assertLess(time.monotonic(), deadline)
            if state['turn'] == 'Tester':
                human.send(choose_bot_move(state, 'Tester', rng))
            state = self.until(human, 'state')
        self.until(human, 'end')
        self.assertEqual(self.server.wait(timeout=5), 0)
        self.assertFalse(Path(self.path).exists())

    def test_two_humans_fill_only_two_bots_and_reject_late_join(self):
        self.start(bots=True)
        a, b = self.join('Alice'), self.join('Bob')
        state = self.until(a, 'state')
        self.until(b, 'state')
        self.assertEqual(set(state['symbols']), {'Alice','Bob','Bot1','Bot2'})
        late = self.join('Late')
        self.assertIn('running', self.until(late, 'error')['text'])
        self.until(late, 'disconnected')

    def test_underfilled_human_lobby_cancels(self):
        self.start()
        a = self.join('Alice')
        self.assertIn('Four players', self.until(a, 'end')['text'])
        self.assertEqual(self.server.wait(timeout=5), 0)

    def test_no_humans_does_not_launch_bots(self):
        self.start(bots=True, seconds=0.2)
        self.assertEqual(self.server.wait(timeout=5), 0)
        self.log.seek(0)
        self.assertIn('At least one human', self.log.read())

    def test_name_validation_duplicate_and_full(self):
        self.start(seconds=2)
        a = self.join('Alice')
        self.until(a, 'info')
        for name in ['alice', 'Bot1', 'two names', []]:
            rejected = self.join(name)
            self.until(rejected, 'error')
            self.until(rejected, 'disconnected')
        for name in ['Bob','Cara','Dan']:
            c = self.join(name)
            self.until(c, 'info')
        fifth = self.join('Eve')
        self.assertIn('full', self.until(fifth, 'error')['text'])

    def test_referee_uid_rejected_in_class_mode(self):
        self.start(demo=False)
        a = self.join('Alice')
        self.assertIn('distinct Linux user', self.until(a, 'error')['text'])
        self.until(a, 'disconnected')

    def test_lobby_departure_frees_seat_and_moves_wait(self):
        self.start(seconds=1)
        a = self.join('Alice')
        self.until(a, 'info')
        a.send({'type':'drop','column':1,'move':1})
        self.until(a, 'error')
        a.send({'type':'chat','channel':'team','text':'secret'})
        self.until(a, 'error')
        a.close()
        replacement = self.join('Alice')
        self.until(replacement, 'info')

    def test_team_pop_broadcast_stale_and_turn_checks(self):
        self.start()
        clients, state = self.four()
        order = state['order']
        clients[order[1]].send({'type':'pop','column':1,'move':1})
        self.until(clients[order[1]], 'error')
        for action, column in [('drop',1), ('drop',1), ('pop',1)]:
            clients[state['turn']].send({'type':action,'column':column,'move':state['move']})
            states = [self.until(c, 'state') for c in clients.values()]
            self.assertTrue(all(s == states[0] for s in states))
            state = states[0]
        self.assertEqual(state['board'][5][0], 'O')
        self.assertEqual(state['pops'][order[2]], 0)
        self.assertEqual(state['pops'][order[0]], 1)
        clients[order[3]].send({'type':'drop','column':2,'move':1})
        self.assertIn('older board', self.until(clients[order[3]], 'error')['text'])


if __name__ == '__main__':
    unittest.main()
