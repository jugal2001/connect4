import random
import unittest

from client import choose_bot_move, parse_command
from server import Game, valid_name

NAMES = ['Alice', 'Bob', 'Cara']


class GameTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(NAMES, random.Random(42))

    def test_three_individual_symbols_and_cyclic_turns(self):
        game = self.game
        self.assertEqual(sorted(game.order), sorted(NAMES))
        self.assertEqual([game.symbols[p] for p in game.order], ['X', 'O', '@'])
        self.assertNotIn('teams', game.state())
        self.assertEqual(game.order, Game(NAMES, random.Random(42)).order)
        for _ in range(3):
            game.drop(game.order[game.turn], 4)
        self.assertEqual([game.board[r][3] for r in (5, 4, 3)], ['X', 'O', '@'])
        self.assertEqual(game.turn, 0)
        for invalid in [NAMES[:2], NAMES + ['Dan'], ['Alice'] * 3]:
            with self.assertRaises(ValueError):
                Game(invalid, random.Random(42))

    def test_individual_horizontal_win(self):
        game = self.game
        for col in [1, 7, 6, 2, 7, 6, 3, 7, 6, 4]:
            game.drop(game.order[game.turn], col)
        self.assertEqual(game.winner, game.order[0])
        with self.assertRaises(ValueError):
            game.drop(game.order[game.turn], 5)

    def test_vertical_win(self):
        game = self.game
        for col in [1, 2, 3] * 3 + [1]:
            game.drop(game.order[game.turn], col)
        self.assertEqual(game.winner, game.order[0])

    def test_diagonal_wins(self):
        for cols in ((0, 1, 2, 3), (6, 5, 4, 3)):
            game = Game(NAMES, random.Random(42))
            for height, col in enumerate(cols):
                for support in range(height):
                    game.board[5-support][col] = 'O' if support % 2 == 0 else 'X'
                if height < 3:
                    game.board[5-height][col] = 'X'
            game.drop(game.order[0], cols[3]+1)
            self.assertEqual(game.winner, game.order[0])

    def test_bad_moves_full_column_and_turn(self):
        game = self.game
        for player, col in [(game.order[1], 1), (game.order[0], True), (game.order[0], 8),
                            (game.order[0], None), (game.order[0], '1')]:
            with self.assertRaises(ValueError):
                game.drop(player, col)
            self.assertEqual(game.move, 1)
        for _ in range(6):
            game.drop(game.order[game.turn], 1)
        with self.assertRaises(ValueError):
            game.drop(game.order[game.turn], 1)
        self.assertEqual(game.move, 7)

    def test_full_board_draw_even_with_tokens(self):
        game = self.game
        columns = [6, 5, 3, 1, 7, 5, 7, 2, 5, 2, 6, 7, 6, 5, 7, 6, 5, 6, 4, 4, 7,
                   4, 3, 1, 4, 3, 6, 4, 1, 3, 7, 5, 2, 2, 2, 4, 1, 1, 2, 3, 1, 3]
        for column in columns:
            game.drop(game.order[game.turn], column)
        self.assertTrue(game.draw)
        self.assertEqual(game.draw_reason, 'The board is full.')

    def test_pop_only_own_disc_and_once_per_player(self):
        game = self.game
        first, second, third = game.order
        game.drop(first, 1)
        game.drop(second, 1)
        with self.assertRaises(ValueError):
            game.pop(third, 1)
        game.drop(third, 2)
        game.pop(first, 1)
        self.assertEqual(game.board[5][0], 'O')
        self.assertEqual(game.board[4][0], '.')
        self.assertEqual(game.pops, {first: 0, second: 1, third: 1})
        self.assertEqual(game.order[game.turn], second)
        game.drop(second, 2)
        game.drop(third, 3)
        with self.assertRaisesRegex(ValueError, 'already used'):
            game.pop(first, 1)

    def test_invalid_pop_preserves_state(self):
        game = self.game
        game.board[5][0] = 'O'
        before = [row[:] for row in game.board]
        for player, col in [(game.order[0], 1), (game.order[0], 2), (game.order[1], 1),
                            (game.order[0], 0), (game.order[0], [])]:
            with self.assertRaises(ValueError):
                game.pop(player, col)
            self.assertEqual(game.board, before)
            self.assertEqual(game.move, 1)
            self.assertEqual(list(game.pops.values()), [1]*3)

    def test_pop_opponent_win_and_simultaneous_draw(self):
        for both in (False, True):
            game = Game(NAMES, random.Random(42))
            game.board[5] = list('OOOX...')
            game.board[4] = list('XXXO...' if both else '...O...')
            if both:
                game.board[3][3] = 'X'
            game.pop(game.order[0], 4)
            self.assertEqual(game.draw, both)
            self.assertEqual(game.winner, None if both else game.order[1])

    def test_bot_ownership_and_token(self):
        game = self.game
        player = game.order[0]
        game.board[5][:2] = ['X', 'O']
        rng = random.Random(42)
        moves = [choose_bot_move(game.state(), player, rng) for _ in range(100)]
        self.assertEqual({m['type'] for m in moves}, {'drop', 'pop'})
        self.assertTrue(all(m['column'] == 1 for m in moves if m['type'] == 'pop'))
        game.pops[player] = 0
        self.assertTrue(all(choose_bot_move(game.state(), player, rng)['type'] == 'drop' for _ in range(100)))

    def test_names_and_commands(self):
        for name in ['Alice', 'My-name', 'John_2']:
            self.assertTrue(valid_name(name))
        for name in ['', 'two names', '\x1b[2J', '1Joe', 'a'*21, None, []]:
            self.assertFalse(valid_name(name))
        with self.assertRaises(ValueError):
            parse_command('team block left', 2)
        self.assertEqual(parse_command('/w Alice hi', 2)['target'], 'Alice')
        self.assertEqual(parse_command('pop 4', 2), {'type': 'pop', 'column': 4, 'move': 2})
        with self.assertRaises(ValueError):
            parse_command('alliance Alice', 2)


if __name__ == '__main__':
    unittest.main()
