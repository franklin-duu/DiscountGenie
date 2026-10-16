import sys
import types
import unittest
from unittest.mock import Mock, patch


try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests = types.ModuleType("requests")
    requests.RequestException = Exception
    sys.modules["requests"] = requests

from steam_api import SteamAPIError, get_steam_game


class SteamAPITests(unittest.TestCase):
    @patch("steam_api.requests.get")
    def test_get_steam_game_maps_steam_data_to_database_fields(self, get):
        response = Mock()
        response.json.return_value = {
            "730": {
                "success": True,
                "data": {
                    "name": "Counter-Strike 2",
                    "developers": ["Valve"],
                    "publishers": ["Valve"],
                    "price_overview": {
                        "initial": 1499,
                        "final": 749,
                        "discount_percent": 50,
                    },
                },
            }
        }
        get.return_value = response

        result = get_steam_game(730)

        self.assertEqual(result["name"], "Counter-Strike 2")
        self.assertEqual(result["base_price"], 14.99)
        self.assertEqual(result["current_price"], 7.49)
        self.assertEqual(result["discount_percent"], 50)
        get.assert_called_once()
        response.raise_for_status.assert_called_once()

    @patch("steam_api.requests.get")
    def test_missing_steam_app_raises_error(self, get):
        response = Mock()
        response.json.return_value = {"730": {"success": False}}
        get.return_value = response

        with self.assertRaises(SteamAPIError):
            get_steam_game(730)


if __name__ == "__main__":
    unittest.main()
