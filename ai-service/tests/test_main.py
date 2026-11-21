import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from main import _load_articles


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


if __name__ == "__main__":
    unittest.main()
