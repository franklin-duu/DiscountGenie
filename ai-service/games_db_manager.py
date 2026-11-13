import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import RealDictCursor

from steam_api import get_steam_game


class GamesDBManager:
    def __init__(self, connection=None):
        self.connection = connection if connection is not None else psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "password"),
            dbname=os.getenv("DB_NAME", "steam_sales"),
        )

    # Game writes

    def input_game(
        self,
        app_id: int,
        name: str,
        publisher: Optional[str] = None,
        developer: Optional[str] = None,
        base_price: Optional[float] = None,
        current_price: Optional[float] = None,
        discount_percent: Optional[float] = 0.0,
    ) -> dict[str, Any]:
        # Input a game into the games database or refresh the data
        # Inputs a new entry into the games history database or if the base_price, current_price, or discount_percent change don't change, just update the last_recorded date.
        game_query = """
            INSERT INTO games
                (app_id, name, publisher, developer, base_price, current_price,
                 discount_percent)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (app_id) DO UPDATE SET
                name = EXCLUDED.name,
                publisher = EXCLUDED.publisher,
                developer = EXCLUDED.developer,
                base_price = EXCLUDED.base_price,
                current_price = EXCLUDED.current_price,
                discount_percent = EXCLUDED.discount_percent,
                last_updated = CURRENT_TIMESTAMP
            RETURNING app_id, name, publisher, developer, base_price,
                      current_price, discount_percent, last_updated;
        """
        latest_history_query = """
            SELECT id, base_price, current_price, discount_percent
            FROM game_price_history
            WHERE app_id = %s
            ORDER BY last_recorded_at DESC, id DESC
            LIMIT 1;
        """
        extend_history_query = """
            UPDATE game_price_history
            SET last_recorded_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """
        insert_history_query = """
            INSERT INTO game_price_history
                (app_id, base_price, current_price, discount_percent)
            VALUES (%s, %s, %s, %s);
        """

        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    game_query,
                    (
                        app_id,
                        name,
                        publisher,
                        developer,
                        base_price,
                        current_price,
                        discount_percent,
                    ),
                )
                game = dict(cursor.fetchone())

                cursor.execute(latest_history_query, (app_id,))
                latest_history = cursor.fetchone()
                prices_unchanged = latest_history and (
                    self._same_price(latest_history["base_price"], base_price)
                    and self._same_price(
                        latest_history["current_price"], current_price
                    )
                    and self._same_price(
                        latest_history["discount_percent"], discount_percent
                    )
                )

                if prices_unchanged:
                    cursor.execute(extend_history_query, (latest_history["id"],))
                else:
                    cursor.execute(
                        insert_history_query,
                        (app_id, base_price, current_price, discount_percent),
                    )

            self.connection.commit()
            return game
        except Exception:
            self.connection.rollback()
            raise

    # Game reads

    def get_game(self, app_id: int) -> Optional[dict[str, Any]]: # Helper Function Return game from Games database Steam app ID, or None when it does not exist.
        query = """
            SELECT app_id, name, publisher, developer, base_price,
                   current_price, discount_percent, last_updated
            FROM games
            WHERE app_id = %s;
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (app_id,))
            game = cursor.fetchone()
        return dict(game) if game else None

    def get_games(self) -> list[dict[str, Any]]: # Return all games from games table ordered by app ID.
        query = """
            SELECT app_id, name, publisher, developer, base_price,
                   current_price, discount_percent, last_updated
            FROM games
            ORDER BY app_id;
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query)
            return [dict(game) for game in cursor.fetchall()]

    def get_price_history(self, app_id: int) -> list[dict[str, Any]]: # Returns all of the table entries for a game using its app id, newest period first.
        query = """
            SELECT id, app_id, base_price, current_price,
                   discount_percent, first_recorded_at, last_recorded_at
            FROM game_price_history
            WHERE app_id = %s
            ORDER BY last_recorded_at DESC, id DESC;
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (app_id,))
            return [dict(history_row) for history_row in cursor.fetchall()]

    def get_daily_price_history(self, app_id: int) -> list[dict[str, Any]]:
        """Return logical daily observations expanded from compressed periods.

        The daily rows are generated by PostgreSQL from the view and are not
        persisted, so storage remains proportional to the number of price
        changes rather than the number of days observed.
        """
        query = """
            SELECT app_id, observation_date, base_price, current_price,
                   discount_percent, first_recorded_at, last_recorded_at
            FROM game_price_history_daily
            WHERE app_id = %s
            ORDER BY observation_date DESC;
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (app_id,))
            return [dict(history_row) for history_row in cursor.fetchall()]

    def save_training_examples(self, rows: list[dict[str, Any]]) -> None:
        """Persist generated feature rows and their 30-day labels."""
        if not rows:
            return
        self._ensure_training_examples_table()
        query = """
            INSERT INTO sale_training_examples (
                app_id, observation_date, current_price, base_price,
                discount_percent, sale_events_last_30_days,
                sale_events_last_90_days, sale_events_last_180_days,
                days_since_last_sale, average_discount_last_180_days,
                month, sale_within_30_days
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (app_id, observation_date) DO UPDATE SET
                current_price = EXCLUDED.current_price,
                base_price = EXCLUDED.base_price,
                discount_percent = EXCLUDED.discount_percent,
                sale_events_last_30_days = EXCLUDED.sale_events_last_30_days,
                sale_events_last_90_days = EXCLUDED.sale_events_last_90_days,
                sale_events_last_180_days = EXCLUDED.sale_events_last_180_days,
                days_since_last_sale = EXCLUDED.days_since_last_sale,
                average_discount_last_180_days = EXCLUDED.average_discount_last_180_days,
                month = EXCLUDED.month,
                sale_within_30_days = EXCLUDED.sale_within_30_days,
                created_at = CURRENT_TIMESTAMP;
        """
        values = [
            (
                row["app_id"],
                row["observation_date"],
                row.get("current_price"),
                row.get("base_price"),
                round(float(row.get("discount_percent") or 0)),
                row.get("sale_events_last_30_days", 0),
                row.get("sale_events_last_90_days", 0),
                row.get("sale_events_last_180_days", 0),
                row.get("days_since_last_sale", 9999),
                row.get("average_discount_last_180_days", 0),
                row["month"],
                bool(row["sale_within_30_days"]),
            )
            for row in rows
        ]
        try:
            with self.connection.cursor() as cursor:
                cursor.executemany(query, values)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def get_training_examples(self, app_id: Optional[int] = None) -> list[dict[str, Any]]:
        """Read saved training rows, optionally limited to one game."""
        self._ensure_training_examples_table()
        query = """
            SELECT app_id, observation_date, current_price, base_price,
                   discount_percent, sale_events_last_30_days,
                   sale_events_last_90_days, sale_events_last_180_days,
                   days_since_last_sale, average_discount_last_180_days,
                   month, sale_within_30_days, created_at
            FROM sale_training_examples
        """
        params = ()
        if app_id is not None:
            query += " WHERE app_id = %s"
            params = (app_id,)
        query += " ORDER BY app_id, observation_date;"
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def _ensure_training_examples_table(self) -> None:
        """Allow existing databases to receive the new table without reset."""
        query = """
            CREATE TABLE IF NOT EXISTS sale_training_examples (
                id BIGSERIAL PRIMARY KEY,
                app_id INT NOT NULL REFERENCES games(app_id) ON DELETE CASCADE,
                observation_date DATE NOT NULL,
                current_price DECIMAL(10,2),
                base_price DECIMAL(10,2),
                discount_percent INT NOT NULL DEFAULT 0,
                sale_events_last_30_days INT NOT NULL DEFAULT 0,
                sale_events_last_90_days INT NOT NULL DEFAULT 0,
                sale_events_last_180_days INT NOT NULL DEFAULT 0,
                days_since_last_sale INT NOT NULL,
                average_discount_last_180_days DECIMAL(5,2) NOT NULL DEFAULT 0,
                month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
                sale_within_30_days BOOLEAN NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (app_id, observation_date)
            );
            CREATE INDEX IF NOT EXISTS idx_training_examples_app_date
            ON sale_training_examples(app_id, observation_date);
        """
        with self.connection.cursor() as cursor:
            cursor.execute(query)
        self.connection.commit()

    def get_prediction(self, app_id: int) -> Optional[dict[str, Any]]:
        migration_query = """
            ALTER TABLE sale_predictions
            ADD COLUMN IF NOT EXISTS model_details JSONB NOT NULL DEFAULT '{}'::jsonb;
        """
        query = """
            SELECT app_id, model_1_score, model_2_score, final_probability,
                   predicted_sale_window, updated_at, model_details
            FROM sale_predictions
            WHERE app_id = %s;
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(migration_query)
            cursor.execute(query, (app_id,))
            prediction = cursor.fetchone()
        self.connection.commit()
        return dict(prediction) if prediction else None

    def save_prediction(
        self,
        app_id: int,
        historical_probability: float,
        news_probability: float,
        final_probability: float,
        predicted_sale_window: str,
        model_details: dict[str, Any],
    ) -> None:
        query = """
            INSERT INTO sale_predictions
                (app_id, model_1_score, model_2_score, final_probability,
                 predicted_sale_window, model_details, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
            ON CONFLICT (app_id) DO UPDATE SET
                model_1_score = EXCLUDED.model_1_score,
                model_2_score = EXCLUDED.model_2_score,
                final_probability = EXCLUDED.final_probability,
                predicted_sale_window = EXCLUDED.predicted_sale_window,
                model_details = EXCLUDED.model_details,
                updated_at = CURRENT_TIMESTAMP;
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        app_id,
                        historical_probability,
                        news_probability,
                        final_probability,
                        predicted_sale_window,
                        json.dumps(model_details),
                    ),
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    # Steam integration

    def input_steam_game(
        self,
        app_id: int,
        country_code: str,
        language: str,
    ) -> dict[str, Any]: # Helper Function that stores game from Steam and saves its current data and price history.
        steam_game = get_steam_game(
            app_id,
            country_code=country_code,
            language=language,
        )
        return self.input_game(**steam_game)

    def get_or_fetch_game(
        self,
        app_id: int,
        country_code: str,
        language: str,
    ) -> dict[str, Any]: # Gets game from games data base or refresh entry if no entry was made after Steam's expected 10:00 AM Pacific time sales update.
        game = self.get_game(app_id)
        if game is None or self._needs_daily_refresh(game.get("last_updated")):
            return self.input_steam_game(app_id, country_code, language)
        return game

    # Helpers

    @staticmethod
    def _same_price(first: Optional[float], second: Optional[float]) -> bool: # Helper Method: Compare database Decimal values and Python numeric values safely.
        if first is None or second is None:
            return first is None and second is None
        return Decimal(str(first)) == Decimal(str(second))

    @staticmethod
    def _needs_daily_refresh(last_updated: Optional[datetime]) -> bool: # Helper Method: If last time the entry was updated was before today at 10:00 AM Pacific , use yesterday's cutoff.
        pacific = ZoneInfo("America/Los_Angeles")
        now = datetime.now(pacific)
        cutoff = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if now < cutoff:
            cutoff -= timedelta(days=1)

        if last_updated is None:
            return True
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)
        return last_updated < cutoff

    def close(self) -> None:
        self.connection.close()
