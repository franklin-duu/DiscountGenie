"""Load SteamDB CSV files and manually maintained base-price schedules."""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any, Union

import pandas as pd


def load_steamdb_csv(
    path: Union[str, Path],
    base_price_schedule: list[tuple[Union[date, datetime, str], float]],
) -> list[dict[str, Any]]:
    """Load SteamDB price points using known historical regular prices."""
    schedule = sorted(
        (pd.Timestamp(effective).tz_localize(None).normalize(), float(price))
        for effective, price in base_price_schedule
    )
    if not schedule:
        raise ValueError("At least one base-price schedule entry is required")

    history = []
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        for row in csv.DictReader(csv_file):
            final_price_text = (row.get("Final price") or "").strip()
            historical_low_text = (row.get("Historical Low") or "").strip()
            if not final_price_text:
                continue
            # SteamDB occasionally emits a synthetic zero-price row without a
            # historical low. It is not a usable sale observation.
            if float(final_price_text) == 0 and not historical_low_text:
                continue
            observed_at = pd.Timestamp(row["DateTime"]).tz_localize(None)
            applicable = [
                entry for entry in schedule
                if entry[0] <= observed_at.normalize()
            ]
            if not applicable:
                raise ValueError(
                    f"No base price schedule entry covers {observed_at.date()}"
                )
            base_price = applicable[-1][1]
            current_price = float(final_price_text)
            if current_price > base_price:
                print(
                    "Skipping price anomaly: "
                    f"{Path(path).name} {observed_at} final={current_price:.2f} "
                    f"> base={base_price:.2f}"
                )
                continue
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


def expand_daily_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand sparse price changes into one observation per calendar day.

    This mirrors the ``game_price_history_daily`` PostgreSQL view used by
    inference: a price observation remains in effect until the next price
    change, and multiple observations on one day use the final observation.
    """
    if not history:
        return []

    by_day: dict[pd.Timestamp, dict[str, Any]] = {}
    for row in sorted(history, key=lambda item: pd.Timestamp(item["observation_date"])):
        observation = pd.Timestamp(row["observation_date"]).tz_localize(None)
        by_day[observation.normalize()] = {**row, "observation_date": observation}

    dates = sorted(by_day)
    expanded: list[dict[str, Any]] = []
    point_index = 0
    active = by_day[dates[0]]
    for day in pd.date_range(dates[0], dates[-1], freq="D"):
        while point_index + 1 < len(dates) and dates[point_index + 1] <= day:
            point_index += 1
            active = by_day[dates[point_index]]
        expanded.append({**active, "observation_date": day})
    return expanded


def load_base_price_schedule_csv(
    path: Union[str, Path],
) -> dict[int, list[tuple[str, float]]]:
    """Load base-price changes grouped by Steam App ID."""
    schedules: dict[int, list[tuple[str, float]]] = {}
    seen_dates: set[tuple[int, str]] = set()
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        for row in csv.DictReader(csv_file):
            if not row.get("app_id") or not row.get("effective_from"):
                continue
            app_id = int(row["app_id"])
            effective_from = row["effective_from"]
            key = (app_id, effective_from)
            if key in seen_dates:
                raise ValueError(
                    "Duplicate base-price date for App ID "
                    f"{app_id}: {effective_from}. Keep only the verified regular price."
                )
            seen_dates.add(key)
            schedules.setdefault(app_id, []).append(
                (effective_from, float(row["base_price"]))
            )
    for app_id in schedules:
        schedules[app_id].sort(key=lambda item: item[0])
    return schedules
