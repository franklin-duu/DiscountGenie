from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Union

try:
    import pandas as pd
    from xgboost import XGBClassifier
except ImportError:  # Optional for the existing demo-only pipeline.
    pd = None
    XGBClassifier = Any


SALE_FEATURE_COLUMNS = [
    "current_price",
    "base_price",
    "discount_percent",
    "sale_events_last_30_days",
    "sale_events_last_90_days",
    "sale_events_last_180_days",
    "days_since_last_sale",
    "average_discount_last_180_days",
    "month",
]


def load_steamdb_csv(
    path: Union[str, Path],
    base_price_schedule: list[tuple[Union[date, datetime, str], float]],
) -> list[dict[str, Any]]:
    """Load SteamDB price points using known historical list-price changes.

    ``base_price_schedule`` contains (effective_date, base_price) entries.
    The latest entry at or before each observation is used. Blank prices are
    skipped because they cannot produce a training observation.
    """
    _require_ml_dependencies()
    schedule = sorted(
        (pd.Timestamp(effective).tz_localize(None).normalize(), float(price))
        for effective, price in base_price_schedule
    )
    if not schedule:
        raise ValueError("At least one base-price schedule entry is required")

    history = []
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        for row in csv.DictReader(csv_file):
            if not (row.get("Final price") or "").strip():
                continue
            observed_at = pd.Timestamp(row["DateTime"]).tz_localize(None)
            applicable = [entry for entry in schedule if entry[0] <= observed_at.normalize()]
            if not applicable:
                raise ValueError(
                    f"No base price schedule entry covers {observed_at.date()}"
                )
            base_price = applicable[-1][1]
            current_price = float(row["Final price"])
            history.append(
                {
                    "observation_date": observed_at,
                    "current_price": current_price,
                    "base_price": base_price,
                    "discount_percent": max(
                        0, round((1 - current_price / base_price) * 100)
                    ),
                }
            )
    return history


def load_base_price_schedule_csv(
    path: Union[str, Path],
) -> dict[int, list[tuple[str, float]]]:
    """Load manually maintained base-price changes grouped by App ID."""
    _require_ml_dependencies()
    schedules: dict[int, list[tuple[str, float]]] = {}
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        for row in csv.DictReader(csv_file):
            if not row.get("app_id") or not row.get("effective_from"):
                continue
            app_id = int(row["app_id"])
            schedules.setdefault(app_id, []).append(
                (row["effective_from"], float(row["base_price"]))
            )
    for app_id in schedules:
        schedules[app_id].sort(key=lambda item: item[0])
    return schedules


def _require_ml_dependencies() -> None:
    if pd is None:
        raise RuntimeError(
            "pandas and xgboost are required for SteamSaleXGBoostModel; "
            "install ai-service/requirements.txt"
        )


def _observation_date(row: dict[str, Any]) -> pd.Timestamp:
    _require_ml_dependencies()
    value = row.get("observation_date")
    if value is None:
        value = row.get("last_recorded_at") or row.get("first_recorded_at")
    if value is None:
        raise ValueError("Every price-history row needs an observation date")
    return pd.Timestamp(value).tz_localize(None).normalize()


def _normalise_history(price_history: Iterable[dict[str, Any]]) -> pd.DataFrame:
    _require_ml_dependencies()
    rows = []
    for row in price_history:
        copied = dict(row)
        copied["observation_date"] = _observation_date(copied)
        copied["discount_percent"] = float(copied.get("discount_percent") or 0)
        copied["current_price"] = float(copied.get("current_price") or 0)
        copied["base_price"] = float(copied.get("base_price") or 0)
        rows.append(copied)

    if not rows:
        return pd.DataFrame(
            columns=["observation_date", "current_price", "base_price", "discount_percent"]
        )

    return (
        pd.DataFrame(rows)
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
        .reset_index(drop=True)
    )


def _sale_event_dates(history: pd.DataFrame) -> list[pd.Timestamp]:
    if history.empty:
        return []
    discounted = history["discount_percent"] > 0
    started = discounted & ~discounted.shift(1, fill_value=False)
    return history.loc[started, "observation_date"].tolist()


def build_sale_feature_row(
    game: dict[str, Any],
    price_history: Iterable[dict[str, Any]],
    as_of: Optional[Union[date, datetime, str]] = None,
) -> dict[str, Any]:
    """Build one prediction row using only history available on ``as_of``."""
    history = _normalise_history(price_history)
    if history.empty:
        raise ValueError("At least one price-history row is required")

    target_date = (
        pd.Timestamp(as_of).tz_localize(None).normalize()
        if as_of is not None
        else history["observation_date"].max()
    )
    prior = history[history["observation_date"] <= target_date]
    if prior.empty:
        raise ValueError("No price history exists on or before as_of")

    latest = prior.iloc[-1]
    event_dates = _sale_event_dates(prior)

    def events_in_days(days: int) -> int:
        start = target_date - pd.Timedelta(days=days)
        return sum(start < event_date <= target_date for event_date in event_dates)

    previous_events = [event_date for event_date in event_dates if event_date <= target_date]
    days_since_last_sale = (
        (target_date - previous_events[-1]).days if previous_events else 9999
    )

    discount_start = target_date - pd.Timedelta(days=180)
    recent = prior[prior["observation_date"] >= discount_start]
    return {
        "current_price": float(latest["current_price"]),
        "base_price": float(latest["base_price"]),
        "discount_percent": float(latest["discount_percent"]),
        "sale_events_last_30_days": events_in_days(30),
        "sale_events_last_90_days": events_in_days(90),
        "sale_events_last_180_days": events_in_days(180),
        "days_since_last_sale": days_since_last_sale,
        "average_discount_last_180_days": float(recent["discount_percent"].mean()),
        "month": int(target_date.month),
    }


def build_training_rows(
    game: dict[str, Any], price_history: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Create one labeled row per historical day with a complete 30-day future."""
    history = _normalise_history(price_history)
    if len(history) < 2:
        return []

    event_dates = _sale_event_dates(history)
    last_date = history["observation_date"].max()
    rows = []
    for target_date in history["observation_date"]:
        if target_date + pd.Timedelta(days=30) > last_date:
            continue
        features = build_sale_feature_row(game, price_history, target_date)
        label = int(any(target_date < event <= target_date + pd.Timedelta(days=30) for event in event_dates))
        features.update({"app_id": game.get("app_id"), "observation_date": target_date, "sale_within_30_days": label})
        rows.append(features)
    return rows


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
