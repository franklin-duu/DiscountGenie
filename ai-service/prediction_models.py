from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import pandas as pd
    from xgboost import XGBClassifier
except ImportError:  # Optional for the existing demo-only pipeline.
    pd = None
    XGBClassifier = Any

from model_features import SALE_FEATURE_COLUMNS, build_sale_feature_row


def _require_ml_dependencies() -> None:
    if pd is None:
        raise RuntimeError(
            "pandas and xgboost are required for SteamSaleXGBoostModel; "
            "install ai-service/requirements.txt"
        )


class SteamSaleXGBoostModel:
    """XGBoost classifier for predicting a sale event in the next 30 days."""

    name = "steam_sale_xgboost_v1"

    def __init__(self, model: Optional[XGBClassifier] = None):
        _require_ml_dependencies()
        self.model = model or XGBClassifier(
            objective="binary:logistic",
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=42,
        )

    def fit(self, training_rows: list[dict[str, Any]]) -> "SteamSaleXGBoostModel":
        if not training_rows:
            raise ValueError("At least one labeled training row is required")
        frame = pd.DataFrame(training_rows)
        missing = set(SALE_FEATURE_COLUMNS + ["sale_within_30_days"]) - set(frame.columns)
        if missing:
            raise ValueError(f"Training rows are missing columns: {sorted(missing)}")
        self.model.fit(frame[SALE_FEATURE_COLUMNS], frame["sale_within_30_days"])
        return self

    def predict(
        self, game: dict[str, Any], price_history: Iterable[dict[str, Any]]
    ) -> dict[str, Any]:
        features = build_sale_feature_row(game, price_history)
        probability = float(self.model.predict_proba(pd.DataFrame([features])[SALE_FEATURE_COLUMNS])[0, 1])
        return {
            "model": self.name,
            "features": features,
            "sale_probability": round(probability, 4),
            "will_sale_within_30_days": probability >= 0.5,
        }

    def save(self, path: str | Path) -> None:
        self.model.save_model(str(path))

    @classmethod
    def load(cls, path: str | Path) -> "SteamSaleXGBoostModel":
        model = cls()
        model.model.load_model(str(path))
        return model


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
    historical_model: Optional[SteamSaleXGBoostModel] = None,
) -> dict[str, Any]:
    historical_output = (
        historical_model.predict(game, price_history)
        if historical_model is not None
        else DummyHistoricalSalesModel().predict(game, price_history)
    )
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
