import unittest

from prediction_models import run_prediction_pipeline


class PredictionModelsTests(unittest.TestCase):
    def setUp(self):
        self.game = {
            "app_id": 730,
            "name": "Counter-Strike 2",
            "developer": "Valve",
            "publisher": "Valve",
            "current_price": 0,
            "discount_percent": 0,
        }

    def test_matched_articles_raise_probability_and_report_model_weights(self):
        articles = [
            {
                "title": "Counter-Strike 2 seasonal sale announcement",
                "text": "A publisher sale brings a deep discount.",
                "source": "Steam news",
            }
        ]

        result = run_prediction_pipeline(
            self.game,
            [
                {"discount_percent": 50},
                {"discount_percent": 0},
                {"discount_percent": 20},
            ],
            articles,
        )

        article_output = result["models"]["nlp"]
        self.assertTrue(article_output["applicable"])
        self.assertEqual(article_output["article_count"], 1)
        self.assertIn("seasonal sale", [item["phrase"] for item in article_output["matched_phrases"]])
        self.assertGreater(article_output["sale_probability"], 0.5)
        self.assertGreater(result["effective_weights"]["article"], 0)
        self.assertEqual(result["prediction"]["expected_discount_percent"], 35)
        self.assertIn(result["prediction"]["predicted_sale_window"], [
            "Within 14 days", "Within 30 days", "More than 30 days"
        ])

    def test_article_abstention_uses_historical_probability_only(self):
        result = run_prediction_pipeline(
            self.game,
            [{"discount_percent": 50}, {"discount_percent": 0}],
            [{"title": "A different game", "text": "No shared publisher here."}],
        )

        self.assertFalse(result["models"]["nlp"]["applicable"])
        self.assertNotIn("sale_probability", result["models"]["nlp"])
        self.assertEqual(
            result["prediction"]["sale_probability"],
            result["models"]["historical"]["sale_probability"],
        )
        self.assertEqual(result["effective_weights"], {"historical": 1.0, "article": 0.0})

    def test_negative_article_phrases_reduce_article_probability(self):
        result = run_prediction_pipeline(
            self.game,
            [],
            [{
                "title": "Counter-Strike 2 price hike",
                "text": "No discount is planned.",
            }],
        )

        self.assertTrue(result["models"]["nlp"]["applicable"])
        self.assertLess(result["models"]["nlp"]["sale_probability"], 0.5)

    def test_missing_history_and_articles_returns_historical_only(self):
        result = run_prediction_pipeline(self.game, [], [])

        self.assertEqual(result["models"]["historical"]["inputs"]["history_observations"], 0)
        self.assertFalse(result["models"]["nlp"]["applicable"])
        self.assertEqual(
            result["prediction"]["sale_probability"],
            result["models"]["historical"]["sale_probability"],
        )
        self.assertIsNone(result["prediction"]["expected_discount_percent"])

    def test_missing_history_does_not_call_xgboost(self):
        class HistoryRequiredModel:
            def predict(self, game, price_history):
                raise AssertionError("XGBoost cannot build features without history")

        result = run_prediction_pipeline(
            self.game, [], [], historical_model=HistoryRequiredModel()
        )

        self.assertEqual(
            result["models"]["historical"]["model"],
            "dummy_historical_sales_v1",
        )
        self.assertEqual(result["models"]["historical"]["inputs"]["history_observations"], 0)


if __name__ == "__main__":
    unittest.main()
