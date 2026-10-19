import random
import unittest

from client import choose_bot_move, parse_command
from server import Alliances, Game, PLAYERS


class GameTests(unittest.TestCase):
    def test_gravity_and_turn_rotation(self):
        game = Game()
        for player in PLAYERS:
            game.drop(player, 4)
        self.assertEqual([game.board[r][3] for r in (5, 4, 3)], ["X", "O", "@"])
        self.assertEqual(game.turn, 0)
        self.assertEqual(game.move, 4)

    def test_bad_moves_preserve_board_and_turn(self):
        game = Game()
        for player, column in (("player2", 1), ("player1", 0), ("player1", 8),
                               ("player1", "2"), ("player1", True), ("player1", None)):
            with self.assertRaises(ValueError):
                game.drop(player, column)
        self.assertEqual(game.move, 1)
        self.assertTrue(all(cell == "." for row in game.board for cell in row))

    def test_full_column_keeps_turn(self):
        game = Game()
        for _ in range(6):
            game.drop(PLAYERS[game.turn], 1)
        with self.assertRaises(ValueError):
            game.drop("player1", 1)
        self.assertEqual(game.turn, 0)
        self.assertEqual(game.move, 7)

    def test_vertical_win(self):
        game = Game()
        for _ in range(3):
            for player, column in zip(PLAYERS, (1, 2, 3)):
                game.drop(player, column)
        game.drop("player1", 1)
        self.assertEqual(game.winner, "player1")
        with self.assertRaises(ValueError):
            game.drop("player2", 4)

    def test_horizontal_win(self):
        game = Game()
        for col in (1, 2, 3):
            game.drop("player1", col)
            game.drop("player2", 7)
            game.drop("player3", 6)
        game.drop("player1", 4)
        self.assertEqual(game.winner, "player1")

    def test_both_diagonal_slopes(self):
        for mirror in (False, True):
            game = Game()
            columns = (0, 1, 2, 3) if not mirror else (6, 5, 4, 3)
            for height, col in enumerate(columns):
                for support in range(height):
                    game.board[5 - support][col] = "O" if support % 2 == 0 else "@"
                if height < 3:
                    game.board[5 - height][col] = "X"
            game.drop("player1", columns[3] + 1)
            self.assertEqual(game.winner, "player1")

    def test_legal_full_game_draw(self):
        columns = [6, 5, 3, 1, 7, 5, 7, 2, 5, 2, 6, 7, 6, 5, 7, 6, 5, 6, 4, 4, 7,
                   4, 3, 1, 4, 3, 6, 4, 1, 3, 7, 5, 2, 2, 2, 4, 1, 1, 2, 3, 1, 3]
        game = Game()
        for column in columns:
            game.drop(PLAYERS[game.turn], column)
        self.assertTrue(game.draw)
        self.assertIsNone(game.winner)
        self.assertTrue(all(cell != "." for row in game.board for cell in row))

    def test_three_in_a_row_is_not_a_win(self):
        game = Game()
        for _ in range(3):
            for player, column in zip(PLAYERS, (1, 2, 3)):
                game.drop(player, column)
        self.assertIsNone(game.winner)


class PopTests(unittest.TestCase):
    def test_pop_shifts_column_spends_token_and_uses_turn(self):
        game = Game()
        for player in PLAYERS:
            game.drop(player, 4)
        game.pop("player1", 4)
        self.assertEqual([game.board[r][3] for r in (5, 4, 3)], ["O", "@", "."])
        self.assertEqual(game.pops, {"player1": 0, "player2": 1, "player3": 1})
        self.assertEqual(game.turn, 1)
        self.assertEqual(game.move, 5)
        self.assertEqual(game.state()["pops"]["player1"], 0)

    def test_invalid_pop_changes_nothing(self):
        game = Game()
        game.board[5][0] = "O"
        before = [row[:] for row in game.board]
        for player, column in (("player1", 1), ("player1", 2), ("player2", 1),
                               ("player1", 0), ("player1", 8), ("player1", True),
                               ("player1", None)):
            with self.assertRaises(ValueError):
                game.pop(player, column)
            self.assertEqual(game.board, before)
            self.assertEqual(game.move, 1)
            self.assertEqual(list(game.pops.values()), [1, 1, 1])

    def test_token_cannot_be_used_twice(self):
        game = Game()
        game.board[5][0] = game.board[4][0] = "X"
        game.pop("player1", 1)
        game.drop("player2", 2)
        game.drop("player3", 3)
        before = [row[:] for row in game.board]
        with self.assertRaisesRegex(ValueError, "already used"):
            game.pop("player1", 1)
        self.assertEqual(game.board, before)
        self.assertEqual(game.turn, 0)
        self.assertEqual(game.pops["player1"], 0)

    def test_pop_can_give_opponent_a_win(self):
        game = Game()
        game.board[5] = list("OOOX...")
        game.board[4][3] = "O"
        game.pop("player1", 4)
        self.assertEqual(game.winner, "player2")
        self.assertFalse(game.draw)
        with self.assertRaises(ValueError):
            game.pop("player1", 4)

    def test_pop_can_win_for_its_player(self):
        game = Game()
        game.board[5] = list("O@OX...")
        game.board[4] = list("XXXO...")
        game.board[3][3] = "X"
        game.pop("player1", 4)
        self.assertEqual(game.winner, "player1")

    def test_pop_creates_two_winners_and_draw(self):
        game = Game()
        game.board[5] = list("OOOX...")
        game.board[4] = list("@@@O...")
        game.board[3][3] = "@"
        game.pop("player1", 4)
        self.assertTrue(game.draw)
        self.assertIsNone(game.winner)
        self.assertIn("Multiple players", game.draw_reason)

    def test_pop_can_remove_a_single_disc_or_open_a_full_column(self):
        for contents in (["."] * 5 + ["X"], list("XO@XOX")):
            game = Game()
            for row, symbol in enumerate(contents):
                game.board[row][0] = symbol
            game.pop("player1", 1)
            self.assertEqual([row[0] for row in game.board], ["."] + contents[:-1])

    def test_pop_command_and_bot_legal_choices(self):
        self.assertEqual(parse_command("pop 4", 8), {"type": "pop", "column": 4, "move": 8})
        with self.assertRaises(ValueError):
            parse_command("pop potato", 8)
        game = Game()
        game.board[5][:3] = ["X", "O", "@"]
        rng = random.Random(42)
        moves = [choose_bot_move(game.state(), "player1", rng) for _ in range(100)]
        self.assertEqual({m["type"] for m in moves}, {"drop", "pop"})
        self.assertTrue(all(m["column"] == 1 for m in moves if m["type"] == "pop"))
        game.pops["player1"] = 0
        self.assertTrue(all(choose_bot_move(game.state(), "player1", rng)["type"] == "drop"
                            for _ in range(100)))


class AllianceTests(unittest.TestCase):
    def test_offer_requires_acceptance_and_one_partner_only(self):
        alliances = Alliances()
        alliances.invite("player1", "player2")
        self.assertFalse(alliances.partners)
        with self.assertRaises(ValueError):
            alliances.accept("player3", "player1")
        alliances.accept("player2", "player1")
        self.assertEqual(alliances.partners, {"player1": "player2", "player2": "player1"})
        with self.assertRaises(ValueError):
            alliances.invite("player1", "player3")
        with self.assertRaises(ValueError):
            alliances.invite("player3", "player2")

    def test_leave_allows_new_partner_and_cancels_old_offers(self):
        alliances = Alliances()
        alliances.invite("player1", "player2")
        alliances.invite("player1", "player3")
        alliances.accept("player2", "player1")
        self.assertFalse(alliances.offers)
        self.assertEqual(alliances.leave("player1"), "player2")
        self.assertFalse(alliances.partners)
        alliances.invite("player1", "player3")
        alliances.leave("player1")
        with self.assertRaises(ValueError):
            alliances.accept("player3", "player1")

    def test_latest_offer_replaces_previous(self):
        alliances = Alliances()
        alliances.invite("player1", "player3")
        alliances.invite("player2", "player3")
        with self.assertRaises(ValueError):
            alliances.accept("player3", "player1")
        alliances.accept("player3", "player2")

    def test_commands(self):
        self.assertEqual(parse_command("drop 4", 1), {"type": "drop", "column": 4, "move": 1})
        self.assertEqual(parse_command("4", 1), parse_command("drop 4", 1))
        self.assertEqual(parse_command("/w player2 deal?", 1)["target"], "player2")
        self.assertEqual(parse_command("alliance say secret", 1)["channel"], "alliance")
        self.assertEqual(parse_command("alliance accept player2", 1)["operation"], "accept")
        with self.assertRaises(ValueError):
            parse_command("drop 4", None)


if __name__ == "__main__":
    unittest.main()
