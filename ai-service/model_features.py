"""Feature engineering shared by model training and prediction."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Optional, Union

try:
    import pandas as pd
except ImportError:  # Optional for the demo-only pipeline.
    pd = None


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


def _require_pandas() -> None:
    if pd is None:
        raise RuntimeError(
            "pandas is required for Steam sale feature engineering; "
            "install ai-service/requirements.txt"
        )


def _observation_date(row: dict[str, Any]) -> pd.Timestamp:
    _require_pandas()
    value = row.get("observation_date")
    if value is None:
        value = row.get("last_recorded_at") or row.get("first_recorded_at")
    if value is None:
        raise ValueError("Every price-history row needs an observation date")
    return pd.Timestamp(value).tz_localize(None).normalize()


def _normalise_history(price_history: Iterable[dict[str, Any]]) -> pd.DataFrame:
    _require_pandas()
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
