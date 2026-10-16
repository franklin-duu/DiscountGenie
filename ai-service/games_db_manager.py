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
