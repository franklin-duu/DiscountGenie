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

    def test_pipeline_passes_history_and_article_inputs_through_models(self):
        articles = [
            {
                "title": "Demo fixture article",
                "text": "Placeholder article text for the NLP model.",
                "source": "demo-fixture",
            }
        ]

        result = run_prediction_pipeline(
            self.game,
            [{"discount_percent": 50}, {"discount_percent": 0}],
            articles,
        )

        self.assertEqual(result["models"]["historical"]["inputs"]["history_observations"], 2)
        self.assertEqual(result["models"]["historical"]["sale_probability"], 0.7)
        self.assertEqual(result["models"]["nlp"]["inputs"]["articles"], articles)
        self.assertEqual(result["models"]["nlp"]["inputs"]["publisher"], "Valve")
        self.assertEqual(result["prediction"]["sale_probability"], 0.64)
        self.assertEqual(result["prediction"]["predicted_sale_window"], "Within 30 days")

    def test_pipeline_returns_a_usable_demo_prediction_without_history(self):
        result = run_prediction_pipeline(self.game, [], [])

        self.assertEqual(result["models"]["historical"]["inputs"]["history_observations"], 0)
        self.assertEqual(result["prediction"]["sale_probability"], 0.535)
        self.assertEqual(result["prediction"]["predicted_sale_window"], "Within 30 days")


if __name__ == "__main__":
    unittest.main()