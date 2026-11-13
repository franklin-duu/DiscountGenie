"""Slowly import game metadata for App IDs represented by training CSVs.

This intentionally reuses get_steam_game() from steam_api.py and waits between
requests. It is meant for one-time data population, not the prediction API.

Run from the AI-service container with:
    python slow_import_games.py
"""

import argparse
import csv
import os
import re
import time
from pathlib import Path

from games_db_manager import GamesDBManager
from steam_api import SteamAPIError, get_steam_game


APP_ID_PATTERN = re.compile(r"(?:chart|price)[_-]?(\d+)")
GAME_COLUMNS = [
    "app_id",
    "name",
    "developer",
    "publisher",
    "base_price",
    "current_price",
    "discount_percent",
]


def find_app_ids(price_history_dir: Path) -> list[int]:
    app_ids = set()
    for csv_path in sorted(price_history_dir.glob("*.csv")):
        match = APP_ID_PATTERN.search(csv_path.stem)
        if match:
            app_ids.add(int(match.group(1)))
        else:
            print(f"Skipping {csv_path.name}: App ID not found in filename")
    return sorted(app_ids)


def save_training_game(path: Path, game: dict) -> None:
    """Upsert one game's metadata into the host-mounted training folder."""
    existing = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8-sig") as csv_file:
            for row in csv.DictReader(csv_file):
                if row.get("app_id"):
                    existing[int(row["app_id"])] = row

    existing[int(game["app_id"])] = {
        "app_id": game["app_id"],
        "name": game.get("name") or "",
        "developer": game.get("developer") or "",
        "publisher": game.get("publisher") or "",
        "base_price": game.get("base_price") if game.get("base_price") is not None else "",
        "current_price": game.get("current_price") if game.get("current_price") is not None else "",
        "discount_percent": game.get("discount_percent") or 0,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=GAME_COLUMNS)
        writer.writeheader()
        writer.writerows(existing[app_id] for app_id in sorted(existing))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh games that already exist in the database",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=float(os.getenv("STEAM_REQUEST_DELAY_SECONDS", "3")),
        help="Seconds to wait between Steam requests (default: 3)",
    )
    args = parser.parse_args()

    training_dir = Path(os.getenv("TRAINING_DATA_DIR", "/training_data"))
    app_ids = find_app_ids(training_dir / "price_history")
    if not app_ids:
        raise RuntimeError("No App IDs found in training_data/price_history/")

    manager = GamesDBManager()
    games_file = training_dir / "games.csv"
    imported = 0
    skipped = 0
    failed = 0
    try:
        for index, app_id in enumerate(app_ids):
            existing = manager.get_game(app_id)
            if existing is not None and not args.force:
                save_training_game(games_file, existing)
                print(f"[{index + 1}/{len(app_ids)}] {app_id}: already exists; skipping")
                skipped += 1
                continue

            try:
                game = get_steam_game(app_id, country_code="us", language="en")
                saved_game = manager.input_game(**game)
                save_training_game(games_file, saved_game)
                print(f"[{index + 1}/{len(app_ids)}] {app_id}: imported {game['name']}")
                imported += 1
            except SteamAPIError as error:
                print(f"[{index + 1}/{len(app_ids)}] {app_id}: failed: {error}")
                failed += 1

            if index < len(app_ids) - 1:
                time.sleep(max(0.0, args.delay))
    finally:
        manager.close()

    print(f"imported={imported} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
