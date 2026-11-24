import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from main import (
    _artifact_version,
    _load_articles,
    _prediction_for_game,
    ranked_games,
)


class FakePredictionManager:
    def __init__(self, saved_prediction):
        self.saved_prediction = saved_prediction
        self.saved = None

    def get_prediction(self, app_id):
        return self.saved_prediction

    def get_daily_price_history(self, app_id):
        return []

    def save_prediction(self, *args):
        self.saved = args


class MainTests(unittest.TestCase):
    def test_load_articles_accepts_seven_digit_fractional_seconds(self):
        published_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        published_at = published_at.replace(
            "+00:00", ".1234567+00:00"
        )
        article = {
            "app_id": 203160,
            "published_at": published_at,
        }

        with patch("main._article_snapshot", return_value=[article]):
            self.assertEqual(_load_articles(203160), [article])

    def test_prediction_recomputes_when_model_artifacts_change(self):
        now = datetime.now(timezone.utc)
        game = {
            "app_id": 730,
            "name": "Counter-Strike 2",
            "last_updated": now,
        }
        manager = FakePredictionManager(
            {
                "updated_at": now + timedelta(seconds=1),
                "final_probability": 0.4,
                "predicted_sale_window": "More than 30 days",
                "model_details": {"artifact_version": "previous-model-version"},
            }
        )
        signature = (("steam_sale_xgboost.json", 2, 100),)
        result = {
            "game": game,
            "prediction": {
                "sale_probability": 0.6,
                "predicted_sale_window": "Within 30 days",
                "expected_discount_percent": None,
            },
            "models": {
                "historical": {"sale_probability": 0.6},
                "nlp": {"applicable": False},
            },
            "effective_weights": {"historical": 1.0, "article": 0.0},
        }

        with (
            patch("main._prediction_artifact_signature", return_value=signature),
            patch("main._load_trained_models", return_value=(None, None, None, True)),
            patch("main.run_prediction_pipeline", return_value=result) as predict,
        ):
            actual = _prediction_for_game(manager, game)

        predict.assert_called_once()
        self.assertFalse(actual["cached"])
        self.assertEqual(manager.saved[2], 0.0)
        self.assertEqual(
            manager.saved[5]["artifact_version"],
            _artifact_version(signature),
        )

    def test_ranked_predictions_refresh_game_before_scoring(self):
        stored_game = {"app_id": 730, "name": "Old name"}
        refreshed_game = {"app_id": 730, "name": "Current name"}
        manager = FakePredictionManager(None)
        manager.get_rankable_games = lambda limit: [stored_game]
        manager.get_or_fetch_game = lambda app_id, country, language: refreshed_game
        manager.close = lambda: None
        result = {
            "game": refreshed_game,
            "prediction": {
                "sale_probability": 0.6,
                "predicted_sale_window": "Within 30 days",
                "expected_discount_percent": None,
            },
        }

        with (
            patch("main.GamesDBManager", return_value=manager),
            patch("main._prediction_for_game", return_value=result) as predict,
        ):
            response = ranked_games(limit=1)

        predict.assert_called_once_with(manager, refreshed_game)
        self.assertEqual(response["games"][0]["name"], "Current name")
        self.assertEqual(response["games"][0]["sale_probability"], 0.6)


if __name__ == "__main__":
    unittest.main()
