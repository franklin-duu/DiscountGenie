from typing import Any


class DummyHistoricalSalesModel:
    """Estimate sale likelihood from stored price-history observations."""

    name = "dummy_historical_sales_v1"

    def predict(
        self, game: dict[str, Any], price_history: list[dict[str, Any]]
    ) -> dict[str, Any]:
        discounts = [float(row.get("discount_percent") or 0) for row in price_history]
        discounted_periods = sum(discount > 0 for discount in discounts)
        history_rate = discounted_periods / len(discounts) if discounts else 0.0
        sale_probability = 0.55 + 0.30 * history_rate

        return {
            "model": self.name,
            "inputs": {
                "app_id": game["app_id"],
                "current_discount_percent": float(game.get("discount_percent") or 0),
                "history_observations": len(discounts),
                "discounted_periods": discounted_periods,
            },
            "sale_probability": round(sale_probability, 4),
        }


class DummyNewsLanguageModel:
    """Accept article and entity inputs while returning a neutral demo score."""

    name = "dummy_news_nlp_v1"

    def predict(
        self, game: dict[str, Any], articles: list[dict[str, str]]
    ) -> dict[str, Any]:
        return {
            "model": self.name,
            "inputs": {
                "game_name": game.get("name"),
                "developer": game.get("developer"),
                "publisher": game.get("publisher"),
                "articles": articles,
            },
            "article_count": len(articles),
            "sentiment_score": 0.5,
            "sale_probability": 0.5,
        }


class DummyFusionModel:
    """Combine historical and article model scores into a demo forecast."""

    name = "dummy_prediction_fusion_v1"
    historical_weight = 0.7
    news_weight = 0.3

    def predict(
        self,
        historical_output: dict[str, Any],
        news_output: dict[str, Any],
    ) -> dict[str, Any]:
        historical_probability = historical_output["sale_probability"]
        news_probability = news_output["sale_probability"]
        sale_probability = round(
            historical_probability * self.historical_weight
            + news_probability * self.news_weight,
            4,
        )

        if sale_probability >= 0.75:
            predicted_sale_window = "Within 14 days"
        elif sale_probability >= 0.5:
            predicted_sale_window = "Within 30 days"
        else:
            predicted_sale_window = "More than 30 days"

        return {
            "model": self.name,
            "inputs": {
                "historical_probability": historical_probability,
                "news_probability": news_probability,
                "historical_weight": self.historical_weight,
                "news_weight": self.news_weight,
            },
            "sale_probability": sale_probability,
            "predicted_sale_window": predicted_sale_window,
        }


def run_prediction_pipeline(
    game: dict[str, Any],
    price_history: list[dict[str, Any]],
    articles: list[dict[str, str]],
) -> dict[str, Any]:
    historical_output = DummyHistoricalSalesModel().predict(game, price_history)
    news_output = DummyNewsLanguageModel().predict(game, articles)
    fusion_output = DummyFusionModel().predict(historical_output, news_output)

    return {
        "app_id": game["app_id"],
        "game": {
            "app_id": game["app_id"],
            "name": game["name"],
            "developer": game.get("developer"),
            "publisher": game.get("publisher"),
            "current_price": (
                float(game["current_price"])
                if game.get("current_price") is not None
                else None
            ),
            "discount_percent": float(game.get("discount_percent") or 0),
        },
        "prediction": {
            "sale_probability": fusion_output["sale_probability"],
            "predicted_sale_window": fusion_output["predicted_sale_window"],
        },
        "models": {
            "historical": historical_output,
            "nlp": news_output,
            "fusion": fusion_output,
        },
    }