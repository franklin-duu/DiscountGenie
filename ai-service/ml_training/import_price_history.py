"""Import SteamDB CSV price histories into PostgreSQL.

Run inside the AI-service container with:
    python -m ml_training.import_price_history

The CSV files are treated as the source of truth for historical price data.
Each app's existing compressed history is replaced in one transaction, making
the command safe to rerun after correcting anomaly handling or base prices.
"""

from __future__ import annotations

import os
import re
from datetime import timedelta
from pathlib import Path

from games_db_manager import GamesDBManager
from .training_data_loader import load_base_price_schedule_csv, load_steamdb_csv


APP_ID_PATTERN = re.compile(r"(?:chart|price)[_-]?(\d+)")


def main() -> None:
    training_dir = Path(os.getenv("TRAINING_DATA_DIR", "/training_data"))
    price_dir = training_dir / "price_history"
    schedules = load_base_price_schedule_csv(
        training_dir / "base_price_history.csv"
    )
    manager = GamesDBManager()
    imported_apps = 0
    imported_periods = 0

    try:
        for csv_path in sorted(price_dir.glob("*.csv")):
            match = APP_ID_PATTERN.search(csv_path.stem)
            if not match:
                print(f"skipping={csv_path.name} reason=App ID not found")
                continue

            app_id = int(match.group(1))
            schedule = schedules.get(app_id)
            if not schedule:
                print(f"skipping={csv_path.name} reason=no base-price schedule")
                continue

            if manager.get_game(app_id) is None:
                print(f"skipping={csv_path.name} reason=game not in database")
                continue

            history = load_steamdb_csv(csv_path, schedule)
            if not history:
                print(f"skipping={csv_path.name} reason=no valid observations")
                continue

            # The model consumes one observation per calendar day. SteamDB
            # exports can contain several observations on one day and are not
            # guaranteed to be ordered, so retain the final observation for
            # each day after sorting chronologically.
            daily_history = {}
            for row in sorted(history, key=lambda item: item["observation_date"]):
                daily_history[row["observation_date"].normalize()] = row
            history = [daily_history[key] for key in sorted(daily_history)]

            # A SteamDB row marks the beginning of a price period. End the
            # period immediately before the next change so the daily view does
            # not assign the next day's price to the previous period.
            periods = []
            for index, row in enumerate(history):
                start = row["observation_date"].to_pydatetime()
                if index + 1 < len(history):
                    end = (
                        history[index + 1]["observation_date"].to_pydatetime()
                        - timedelta(seconds=1)
                    )
                else:
                    end = start
                periods.append((
                    start,
                    end,
                    row["base_price"],
                    row["current_price"],
                    row["discount_percent"],
                ))

            try:
                with manager.connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM game_price_history WHERE app_id = %s",
                        (app_id,),
                    )
                    cursor.executemany(
                        """
                        INSERT INTO game_price_history (
                            app_id, base_price, current_price, discount_percent,
                            first_recorded_at, last_recorded_at
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        [
                            (app_id, base, current, discount, start, end)
                            for start, end, base, current, discount in periods
                        ],
                    )
                manager.connection.commit()
            except Exception:
                manager.connection.rollback()
                raise

            imported_apps += 1
            imported_periods += len(periods)
            print(
                f"app_id={app_id} imported_periods={len(periods)} "
                f"observations={len(history)}"
            )

        print(f"imported_apps={imported_apps}")
        print(f"imported_periods={imported_periods}")
    finally:
        manager.close()


if __name__ == "__main__":
    main()
