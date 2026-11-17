"""Build labeled rows used to train the Steam sale model."""

from __future__ import annotations

from bisect import bisect_right
from typing import Any, Iterable

import pandas as pd

from model_features import _normalise_history, _sale_event_dates


def build_training_rows(
    game: dict[str, Any], price_history: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Create one labeled row per historical day with a complete 30-day future."""
    history = _normalise_history(price_history)
    if len(history) < 2:
        return []

    event_dates = _sale_event_dates(history)
    event_dates = sorted(event_dates)
    last_date = history["observation_date"].max()
    indexed_history = history.set_index("observation_date")
    rolling_discount = indexed_history["discount_percent"].rolling("180D").mean()
    rows = []
    for index, target_date in enumerate(history["observation_date"]):
        if target_date + pd.Timedelta(days=30) > last_date:
            continue

        event_30_start = target_date - pd.Timedelta(days=30)
        event_90_start = target_date - pd.Timedelta(days=90)
        event_180_start = target_date - pd.Timedelta(days=180)
        sale_events_last_30_days = bisect_right(event_dates, target_date) - bisect_right(
            event_dates, event_30_start
        )
        sale_events_last_90_days = bisect_right(event_dates, target_date) - bisect_right(
            event_dates, event_90_start
        )
        sale_events_last_180_days = bisect_right(event_dates, target_date) - bisect_right(
            event_dates, event_180_start
        )
        previous_event_index = bisect_right(event_dates, target_date) - 1
        days_since_last_sale = (
            (target_date - event_dates[previous_event_index]).days
            if previous_event_index >= 0
            else 9999
        )
        label = int(
            bisect_right(event_dates, target_date + pd.Timedelta(days=30))
            > bisect_right(event_dates, target_date)
        )
        latest = history.iloc[index]
        features = {
            "current_price": float(latest["current_price"]),
            "base_price": float(latest["base_price"]),
            "discount_percent": float(latest["discount_percent"]),
            "sale_events_last_30_days": sale_events_last_30_days,
            "sale_events_last_90_days": sale_events_last_90_days,
            "sale_events_last_180_days": sale_events_last_180_days,
            "days_since_last_sale": days_since_last_sale,
            "average_discount_last_180_days": float(rolling_discount.iloc[index]),
            "month": int(target_date.month),
        }
        features.update(
            {
                "app_id": game.get("app_id"),
                "observation_date": target_date,
                "sale_within_30_days": label,
            }
        )
        rows.append(features)
    return rows
