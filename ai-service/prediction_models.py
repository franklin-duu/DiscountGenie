from __future__ import annotations

import json
import math
import re
from statistics import median
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol

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


class HistoricalSalesModel(Protocol):
    def predict(
        self, game: dict[str, Any], price_history: list[dict[str, Any]]
    ) -> dict[str, Any]: ...


ARTICLE_LEXICON = {
    "sale": 0.8,
    "discount": 0.8,
    "anniversary": 0.8,
    "sequel": 0.7,
    "seasonal sale": 1.2,
    "publisher sale": 1.2,
    "bundle": 0.7,
    "deep discount": 1.2,
    "summer sale": 1.2,
    "winter sale": 1.2,
    "price hike": -1.2,
    "full price": -0.8,
    "no discount": -1.2,
    "delisted": -1.2,
    "price increase": -1.2,
}


def _sigmoid(value: float) -> float:
    value = max(-40.0, min(40.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _entity_match(game: dict[str, Any], article: dict[str, Any]) -> bool:
    text = " ".join(
        str(article.get(field) or "") for field in ("title", "text")
    ).casefold()
    entities = [game.get("name"), game.get("publisher")]
    return any(
        len(entity_text) >= 3 and entity_text.casefold() in text
        for entity in entities
        if (entity_text := str(entity or "").strip())
    )


def article_feature_counts(
    game: dict[str, Any],
    articles: list[dict[str, Any]],
    phrases: Iterable[str] = ARTICLE_LEXICON,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    matched_articles = [article for article in articles if _entity_match(game, article)]
    combined_text = " ".join(
        f"{article.get('title') or ''} {article.get('text') or ''}"
        for article in matched_articles
    ).casefold()
    counts = {
        phrase: min(5, len(re.findall(rf"(?<!\w){re.escape(phrase)}(?!\w)", combined_text)))
        for phrase in phrases
    }
    return matched_articles, counts


class WeightedArticleSaleModel:
    """Logistic sale model over entity-matched article phrase counts."""

    name = "steam_sale_article_logistic_v1"

    def predict(
        self, game: dict[str, Any], articles: list[dict[str, Any]]
    ) -> dict[str, Any]:
        phrases = self.artifact["phrase_weights"]
        matched_articles, counts = article_feature_counts(game, articles, phrases)
        if not matched_articles:
            return {
                "model": self.name,
                "applicable": False,
                "article_count": 0,
                "matched_phrases": [],
                "sentiment_score": None,
            }

        matched_phrases = [
            {
                "phrase": phrase,
                "weight": round(float(weight), 4),
                "count": counts.get(phrase, 0),
            }
            for phrase, weight in phrases.items()
            if counts.get(phrase, 0)
        ]
        weighted_score = sum(
            item["weight"] * item["count"] for item in matched_phrases
        )
        logit = float(self.artifact["intercept"]) + weighted_score
        probability = _sigmoid(logit)
        return {
            "model": self.name,
            "applicable": True,
            "article_count": len(matched_articles),
            "matched_phrases": matched_phrases,
            "sentiment_score": round(_sigmoid(weighted_score), 4),
            "sale_probability": round(probability, 4),
        }

    def __init__(self, artifact: Optional[dict[str, Any]] = None):
        self.artifact = artifact or {
            "intercept": 0.0,
            "phrase_weights": dict(ARTICLE_LEXICON),
        }

    @classmethod
    def load(cls, path: str | Path) -> "WeightedArticleSaleModel":
        with open(path, encoding="utf-8") as model_file:
            return cls(json.load(model_file))


class SynthesisLogisticModel:
    """Combine model probabilities and coverage signals with logistic regression."""

    name = "steam_sale_synthesis_logistic_v1"

    def __init__(self, artifact: Optional[dict[str, Any]] = None):
        self.artifact = artifact or {
            "intercept": -0.7,
            "coefficients": {
                "historical_probability": 1.8,
                "article_probability": 0.9,
                "article_applies": 0.2,
                "article_count": 0.03,
                "history_observations": 0.001,
            },
        }

    @classmethod
    def load(cls, path: str | Path) -> "SynthesisLogisticModel":
        with open(path, encoding="utf-8") as model_file:
            return cls(json.load(model_file))

    def predict(
        self,
        historical_output: dict[str, Any],
        article_output: dict[str, Any],
        history_observations: int,
    ) -> dict[str, Any]:
        historical_probability = float(historical_output["sale_probability"])
        applies = bool(article_output["applicable"])
        article_probability = (
            float(article_output["sale_probability"]) if applies else 0.0
        )
        article_count = int(article_output["article_count"]) if applies else 0
        coefficients = self.artifact["coefficients"]
        features = {
            "historical_probability": historical_probability,
            "article_probability": article_probability,
            "article_applies": int(applies),
            "article_count": article_count,
            "history_observations": int(history_observations),
        }
        # Abstention is a true pass-through: no synthetic news score can shift it.
        if not applies:
            sale_probability = historical_probability
            effective_weights = {"historical": 1.0, "article": 0.0}
        else:
            logit = float(self.artifact["intercept"]) + sum(
                float(coefficients.get(name, 0.0)) * value
                for name, value in features.items()
            )
            sale_probability = _sigmoid(logit)
            historical_term = abs(
                float(coefficients.get("historical_probability", 0.0))
                * historical_probability
            )
            article_term = abs(
                float(coefficients.get("article_probability", 0.0))
                * article_probability
            )
            total_term = historical_term + article_term
            effective_weights = (
                {
                    "historical": round(historical_term / total_term, 4),
                    "article": round(article_term / total_term, 4),
                }
                if total_term
                else {"historical": 1.0, "article": 0.0}
            )
        sale_probability = round(sale_probability, 4)

        if sale_probability >= 0.75:
            predicted_sale_window = "Within 14 days"
        elif sale_probability >= 0.5:
            predicted_sale_window = "Within 30 days"
        else:
            predicted_sale_window = "More than 30 days"

        return {
            "model": self.name,
            "inputs": features,
            "sale_probability": sale_probability,
            "predicted_sale_window": predicted_sale_window,
            "effective_weights": effective_weights,
        }


def run_prediction_pipeline(
    game: dict[str, Any],
    price_history: list[dict[str, Any]],
    articles: list[dict[str, Any]],
    historical_model: Optional[HistoricalSalesModel] = None,
    article_model: Optional[WeightedArticleSaleModel] = None,
    synthesis_model: Optional[SynthesisLogisticModel] = None,
) -> dict[str, Any]:
    historical_output = (
        historical_model.predict(game, price_history)
        if historical_model is not None and price_history
        else DummyHistoricalSalesModel().predict(game, price_history)
    )
    article_output = (article_model or WeightedArticleSaleModel()).predict(game, articles)
    history_observations = len(price_history)
    fusion_output = (synthesis_model or SynthesisLogisticModel()).predict(
        historical_output, article_output, history_observations
    )
    sale_discounts = [
        float(row.get("discount_percent") or 0)
        for row in price_history
        if float(row.get("discount_percent") or 0) > 0
    ]
    expected_discount_percent = (
        float(median(sale_discounts)) if sale_discounts else None
    )

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
            "expected_discount_percent": (
                round(expected_discount_percent, 1)
                if expected_discount_percent is not None
                else None
            ),
        },
        "models": {
            "historical": historical_output,
            "nlp": article_output,
            "fusion": fusion_output,
        },
        "effective_weights": fusion_output["effective_weights"],
    }
