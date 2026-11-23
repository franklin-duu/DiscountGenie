import unittest

from ml_training.training_data_loader import expand_daily_history


class TrainingDataLoaderTests(unittest.TestCase):
    def test_expand_daily_history_carries_price_until_next_change(self):
        history = expand_daily_history(
            [
                {
                    "observation_date": "2024-01-01T12:00:00",
                    "current_price": 10,
                    "discount_percent": 0,
                },
                {
                    "observation_date": "2024-01-03T08:00:00",
                    "current_price": 5,
                    "discount_percent": 50,
                },
            ]
        )

        self.assertEqual(
            [row["observation_date"].date().isoformat() for row in history],
            ["2024-01-01", "2024-01-02", "2024-01-03"],
        )
        self.assertEqual(
            [row["current_price"] for row in history],
            [10, 10, 5],
        )


if __name__ == "__main__":
    unittest.main()
