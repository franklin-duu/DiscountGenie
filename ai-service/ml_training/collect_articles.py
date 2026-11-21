"""Collect a bounded snapshot of Steam game news for offline model training."""

from __future__ import annotations

import csv
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests


ARTICLE_GAME_IDS = {
    620, 8930, 22380, 105600, 108600, 203160, 239140, 270880, 284160, 413150
}
STEAM_NEWS_URL = (
    "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
)
OTHER_STORES = re.compile(
    r"\b(epic games store|epic|gog(?:\.com)?|playstation(?: network| store)?|"
    r"xbox(?: game pass| store)?|nintendo eshop|ubisoft connect|ea app|origin|"
    r"itch\.io|battle\.net|microsoft store|amazon games|google play|app store|"
    r"humble store|green man gaming|fanatical|gamesplanet)\b",
    re.IGNORECASE,
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _plain_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()


def _article_excerpt(text: str, entities: list[str], limit: int = 240) -> str:
    if len(text) <= limit:
        return text
    folded_text = text.casefold()
    for entity in entities:
        position = folded_text.find(entity.casefold())
        if position >= 0:
            start = max(0, position - max(0, (limit - len(entity)) // 2))
            return text[start : start + limit]
    return text[:limit]


def _game_rows(training_dir: Path) -> dict[int, dict[str, str]]:
    with open(training_dir / "games.csv", newline="", encoding="utf-8-sig") as file:
        return {
            int(row["app_id"]): row
            for row in csv.DictReader(file)
            if int(row["app_id"]) in ARTICLE_GAME_IDS
        }


def collect_articles() -> Path:
    training_dir = Path(os.getenv("TRAINING_DATA_DIR", "/training_data"))
    games = _game_rows(training_dir)
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    articles: dict[str, dict[str, object]] = {}

    for app_id, game in games.items():
        response = requests.get(
            STEAM_NEWS_URL,
            params={"appid": app_id, "count": 40, "maxlength": 3000},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json().get("appnews", {}).get("newsitems", [])
        game_name = game["name"].casefold()
        publisher = game.get("publisher", "").strip().casefold()
        for item in payload:
            published = datetime.fromtimestamp(
                int(item.get("date") or 0), tz=timezone.utc
            )
            if published < cutoff:
                continue
            title = _plain_text(item.get("title") or "")
            full_text = _plain_text(item.get("contents") or "")
            searchable = f"{title} {full_text}".casefold()
            if not (game_name in searchable or (publisher and publisher in searchable)):
                continue
            if OTHER_STORES.search(searchable):
                continue
            text = _article_excerpt(full_text, [game["name"], game.get("publisher", "")])
            article_id = str(item.get("gid") or item.get("url") or "")
            if not article_id:
                continue
            articles[article_id] = {
                "app_id": app_id,
                "title": title,
                "text": text,
                "published_at": published.isoformat(),
                "source": item.get("feedlabel") or item.get("feedname") or "Steam News",
                "url": item.get("url"),
            }

    output_dir = training_dir / "articles"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "articles.json"
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            {"source": STEAM_NEWS_URL, "articles": list(articles.values())},
            file,
            ensure_ascii=False,
            indent=2,
        )
    print(f"games_checked={len(games)}")
    print(f"articles_saved={len(articles)}")
    print(f"article_file={output_path}")
    return output_path


if __name__ == "__main__":
    collect_articles()
