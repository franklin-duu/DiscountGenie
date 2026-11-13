"""Build training examples and train the Steam sale model.

Run inside the AI-service container with:
    python train_model.py
"""

import os
import re
from pathlib import Path

from games_db_manager import GamesDBManager
from prediction_models import (
    SteamSaleXGBoostModel,
    build_training_rows,
    load_base_price_schedule_csv,
    load_steamdb_csv,
)
from steam_api import get_steam_game


def main() -> None:
    manager = GamesDBManager()
    try:
        all_rows = []
        training_dir = Path(os.getenv("TRAINING_DATA_DIR", "/training_data"))
        price_dir = training_dir / "price_history"
        base_price_file = training_dir / "base_price_history.csv"
        schedules = load_base_price_schedule_csv(base_price_file)
        csv_files = sorted(price_dir.glob("*.csv"))
        games = []

        for csv_path in csv_files:
            match = re.search(r"(?:chart|price)[_-]?(\d+)", csv_path.stem)
            if not match:
                print(f"skipping={csv_path.name} reason=App ID not found in filename")
                continue
            app_id = int(match.group(1))
            if app_id not in schedules:
                print(f"skipping={csv_path.name} reason=no base-price schedule")
                continue

            history = load_steamdb_csv(csv_path, schedules[app_id])
            game = manager.get_game(app_id)
            if game is None:
                game = manager.input_game(**get_steam_game(app_id))
            games.append(game)
            rows = build_training_rows(game, history)
            if rows:
                manager.save_training_examples(rows)
                all_rows.extend(rows)
            print(f"app_id={game['app_id']} training_rows={len(rows)}")

        if not all_rows:
            raise RuntimeError(
                "No training rows were created. Check price_history CSVs, "
                "App IDs, base_price_history.csv, and 30-day history coverage."
            )

        labels = {row["sale_within_30_days"] for row in all_rows}
        if len(labels) < 2:
            raise RuntimeError(
                "Training data needs both sale and no-sale examples before "
                "XGBoost can be trained."
            )

        model = SteamSaleXGBoostModel().fit(all_rows)
        model_dir = Path(os.getenv("MODEL_DIR", "/models"))
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / "steam_sale_xgboost.json"
        model.save(model_path)

        print(f"games={len(games)}")
        print(f"training_rows={len(all_rows)}")
        print(f"model_path={model_path}")
    finally:
        manager.close()


if __name__ == "__main__":
    main()
