"""Real socket tests: timed joining, individual results, privacy, and bot fill."""
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
NAMES = ['Alice', 'Bob', 'Cara']


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

    def start(self, bots=False, demo=True, seconds=0.6, solo=False):
        command = [sys.executable, '-u', 'server.py', '--socket', self.path,
                   '--lobby-seconds', str(seconds), '--bot-delay', '0', '--seed', '42']
        if demo:
            command.append('--demo')
        if bots:
            command.append('--bots')
        if solo:
            command.append('--solo')
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

    def three(self):
        clients = {name: self.join(name) for name in NAMES}
        states = [self.until(c, 'state') for c in clients.values()]
        self.assertTrue(all(s == states[0] for s in states))
        return clients, states[0]

    def test_full_lobby_waits_then_individual_win(self):
        self.start(seconds=0.8)
        clients, state = self.three()
        self.assertGreaterEqual(time.monotonic()-self.started, 0.8)
        self.assertEqual([state['symbols'][p] for p in state['order']], ['X','O','@'])
        for col in [1, 7, 6, 2, 7, 6, 3, 7, 6, 4]:
            clients[state['turn']].send({'type':'drop', 'column':col, 'move':state['move']})
            states = [self.until(c, 'state') for c in clients.values()]
            self.assertTrue(all(s == states[0] for s in states))
            state = states[0]
        for client in clients.values():
            result = self.until(client, 'end')['text']
            self.assertIn(state['order'][0] + ' (X) wins', result)
        self.assertEqual(self.server.wait(timeout=5), 0)

    def test_whisper_unicast_public_broadcast_and_no_teams(self):
        self.start()
        clients, state = self.three()
        self.assertNotIn('teams', state)
        clients['Alice'].send({'type':'chat', 'channel':'private', 'target':'bob',
                               'text':'secret', 'sender':'Cara'})
        message = self.until(clients['Bob'], 'chat')
        self.assertEqual(message['sender'], 'Alice')
        self.assertEqual(message['text'], 'secret')
        self.until(clients['Alice'], 'info')
        self.assertIsNone(clients['Cara'].receive(timeout=0.1))
        clients['Alice'].send({'type':'chat', 'channel':'team', 'text':'old command'})
        self.until(clients['Alice'], 'error')
        clients['Bob'].send({'type':'chat', 'channel':'all', 'text':'public'})
        for client in clients.values():
            self.assertEqual(self.until(client, 'chat')['text'], 'public')
        clients['Cara'].close()
        self.assertIn('cancelled', self.until(clients['Alice'], 'end')['text'])

    def test_one_named_human_two_bot_processes_complete(self):
        self.start(bots=True)
        human = self.join('Tester')
        state = self.until(human, 'state')
        self.assertEqual(set(state['symbols']), {'Tester','Bot1','Bot2'})
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

    def test_solo_starts_immediately_with_exactly_two_bots(self):
        self.start(seconds=30, solo=True)
        human = self.join('Host')
        state = self.until(human, 'state')
        self.assertLess(time.monotonic() - self.started, 5)
        self.assertEqual(set(state['symbols']), {'Host', 'Bot1', 'Bot2'})
        late = communication.Client(self.path)
        self.clients.append(late)
        self.until(late, 'error')
        self.until(late, 'disconnected')

    def test_two_humans_fill_only_one_bot_and_reject_late_join(self):
        self.start(bots=True)
        a, b = self.join('Alice'), self.join('Bob')
        state = self.until(a, 'state')
        self.until(b, 'state')
        self.assertEqual(set(state['symbols']), {'Alice','Bob','Bot1'})
        late = communication.Client(self.path)
        self.clients.append(late)
        self.assertIn('running', self.until(late, 'error')['text'])
        self.until(late, 'disconnected')

    def test_underfilled_human_lobby_cancels(self):
        self.start()
        a = self.join('Alice')
        self.assertIn('Three players', self.until(a, 'end')['text'])
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
        for name in ['Bob','Cara']:
            c = self.join(name)
            self.until(c, 'info')
        fourth = self.join('Dan')
        self.assertIn('full', self.until(fourth, 'error')['text'])

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

    def test_pop_broadcast_stale_and_turn_checks(self):
        self.start()
        clients, state = self.three()
        order = state['order']
        clients[order[1]].send({'type':'pop','column':1,'move':1})
        self.until(clients[order[1]], 'error')
        for action, column in [('drop',1), ('drop',1), ('drop',2), ('pop',1)]:
            clients[state['turn']].send({'type':action,'column':column,'move':state['move']})
            states = [self.until(c, 'state') for c in clients.values()]
            self.assertTrue(all(s == states[0] for s in states))
            state = states[0]
        self.assertEqual(state['board'][5][0], 'O')
        self.assertEqual(state['pops'][order[0]], 0)
        self.assertEqual(state['pops'][order[1]], 1)
        clients[order[1]].send({'type':'drop','column':2,'move':1})
        self.assertIn('older board', self.until(clients[order[1]], 'error')['text'])


if __name__ == '__main__':
    unittest.main()
