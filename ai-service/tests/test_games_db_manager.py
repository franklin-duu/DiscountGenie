import sys
import types
import unittest
from decimal import Decimal
from unittest.mock import patch


# Allow the tests to run before the Docker requirements are installed.
try:
    import psycopg2  # noqa: F401
except ModuleNotFoundError:
    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.extras = types.ModuleType("psycopg2.extras")
    psycopg2.extras.RealDictCursor = object
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = psycopg2.extras

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests = types.ModuleType("requests")
    requests.RequestException = Exception
    requests.get = None
    sys.modules["requests"] = requests

from games_db_manager import GamesDBManager


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.fetchone_results = list(connection.fetchone_results)
        self.fetchall_result = connection.fetchall_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.connection.executed.append((query, params))
        if self.connection.execute_error:
            raise self.connection.execute_error

    def fetchone(self):
        return self.fetchone_results.pop(0)

    def fetchall(self):
        return self.fetchall_result


class FakeConnection:
    def __init__(self, fetchone_results=None, fetchall_result=None, execute_error=None):
        self.fetchone_results = fetchone_results or []
        self.fetchall_result = fetchall_result or []
        self.execute_error = execute_error
        self.executed = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self, cursor_factory=None):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class GamesDBManagerTests(unittest.TestCase):
    GAME = {
        "app_id": 730,
        "name": "Counter-Strike 2",
        "publisher": "Valve",
        "developer": "Valve",
        "base_price": Decimal("14.99"),
        "current_price": Decimal("7.49"),
        "discount_percent": Decimal("50.00"),
    }

    def test_first_scan_inserts_a_history_period(self):
        connection = FakeConnection(fetchone_results=[self.GAME, None])
        manager = GamesDBManager(connection)

        result = manager.input_game(730, "Counter-Strike 2", base_price=14.99, current_price=7.49)

        self.assertEqual(result, self.GAME)
        self.assertEqual(connection.commits, 1)
        self.assertEqual(len(connection.executed), 3)
        self.assertIn("INSERT INTO game_price_history", connection.executed[2][0])
        self.assertEqual(connection.executed[2][1], (730, 14.99, 7.49, 0.0))

    def test_unchanged_prices_extend_the_latest_period(self):
        latest = {"id": 12, "base_price": Decimal("14.99"), "current_price": Decimal("7.49"), "discount_percent": Decimal("50.00")}
        connection = FakeConnection(fetchone_results=[self.GAME, latest])
        manager = GamesDBManager(connection)

        manager.input_game(730, "Counter-Strike 2", base_price=14.99, current_price=7.49, discount_percent=50.0)

        self.assertEqual(connection.commits, 1)
        self.assertIn("UPDATE game_price_history", connection.executed[2][0])
        self.assertEqual(connection.executed[2][1], (12,))

    def test_changed_prices_insert_a_new_period(self):
        latest = {"id": 12, "base_price": Decimal("14.99"), "current_price": Decimal("7.49"), "discount_percent": Decimal("50.00")}
        connection = FakeConnection(fetchone_results=[self.GAME, latest])
        manager = GamesDBManager(connection)

        manager.input_game(730, "Counter-Strike 2", base_price=14.99, current_price=4.99)

        self.assertIn("INSERT INTO game_price_history", connection.executed[2][0])
        self.assertEqual(connection.executed[2][1], (730, 14.99, 4.99, 0.0))

    def test_get_price_history_filters_by_app_id(self):
        history = [{"id": 12, "app_id": 730, "current_price": Decimal("7.49")}]
        connection = FakeConnection(fetchall_result=history)
        manager = GamesDBManager(connection)

        result = manager.get_price_history(730)

        self.assertEqual(result, history)
        self.assertEqual(connection.executed[0][1], (730,))
        self.assertIn("ORDER BY last_recorded_at DESC", connection.executed[0][0])

    def test_database_error_rolls_back(self):
        connection = FakeConnection(execute_error=RuntimeError("database error"))
        manager = GamesDBManager(connection)

        with self.assertRaises(RuntimeError):
            manager.input_game(730, "Counter-Strike 2")

        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)

    @patch("games_db_manager.get_steam_game")
    def test_input_steam_game_fetches_and_saves_steam_data(self, steam_getter):
        steam_getter.return_value = {
            "app_id": 730,
            "name": "Counter-Strike 2",
            "publisher": "Valve",
            "developer": "Valve",
            "base_price": 14.99,
            "current_price": 7.49,
            "discount_percent": 50.0,
        }
        connection = FakeConnection(fetchone_results=[self.GAME, None])
        manager = GamesDBManager(connection)

        manager.input_steam_game(730, "ca", "fr")

        steam_getter.assert_called_once_with(730, country_code="ca", language="fr")
        self.assertEqual(connection.commits, 1)


if __name__ == "__main__":
    unittest.main()
