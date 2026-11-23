"""Train the weighted article and synthesis sale models from local Steam data."""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg2
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import TimeSeriesSplit

from model_features import SALE_FEATURE_COLUMNS, _normalise_history
from ml_training.collect_articles import ARTICLE_GAME_IDS
from ml_training.training_data_loader import (
    expand_daily_history,
    load_base_price_schedule_csv,
    load_steamdb_csv,
)
from ml_training.training_rows import build_training_rows
from prediction_models import (
    ARTICLE_LEXICON,
    SteamSaleXGBoostModel,
    WeightedArticleSaleModel,
    article_feature_counts,
)


def _load_games(training_dir: Path) -> dict[int, dict[str, Any]]:
    with open(training_dir / "games.csv", newline="", encoding="utf-8-sig") as file:
        return {
            int(row["app_id"]): {
                **row,
                "app_id": int(row["app_id"]),
            }
            for row in csv.DictReader(file)
            if int(row["app_id"]) in ARTICLE_GAME_IDS
        }


def _dated_articles(path: Path) -> dict[int, list[dict[str, Any]]]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; collect an offline article snapshot first with "
            "`python -m ml_training.collect_articles`."
        )
    with open(path, encoding="utf-8") as file:
        payload = json.load(file)
    articles_by_game: dict[int, list[dict[str, Any]]] = {}
    for article in payload.get("articles", []):
        article["published_at"] = datetime.fromisoformat(
            article["published_at"].replace("Z", "+00:00")
        )
        articles_by_game.setdefault(int(article["app_id"]), []).append(article)
    for articles in articles_by_game.values():
        articles.sort(key=lambda article: article["published_at"])
    return articles_by_game


def _articles_available_on(
    articles: list[dict[str, Any]], observation_date: Any
) -> list[dict[str, Any]]:
    target = pd.Timestamp(observation_date).to_pydatetime().replace(
        tzinfo=timezone.utc
    )
    start = target - timedelta(days=30)
    return [
        article
        for article in articles
        if start <= article["published_at"] <= target
    ]


def _feature_vector(
    game: dict[str, Any],
    articles: list[dict[str, Any]],
    phrases: list[str],
) -> list[int]:
    _, counts = article_feature_counts(game, articles, phrases)
    return [counts[phrase] for phrase in phrases]


def _train_article_model(
    game_rows: list[tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]]
) -> tuple[dict[str, Any], int, int]:
    phrases = list(ARTICLE_LEXICON)
    feature_rows = []
    labels = []
    phrase_frequency = {phrase: 0 for phrase in phrases}
    matched_game_ids = set()
    matched_article_ids = set()
    counted_articles = set()
    for game, articles, row in game_rows:
        available = _articles_available_on(articles, row["observation_date"])
        matched, _ = article_feature_counts(game, available, phrases)
        if not matched:
            continue
        matched_game_ids.add(game["app_id"])
        matched_article_ids.update(
            article.get("url") or article.get("title") or ""
            for article in matched
        )
        for article in matched:
            article_id = article.get("url") or article.get("title") or ""
            if not article_id or article_id in counted_articles:
                continue
            counted_articles.add(article_id)
            _, article_counts = article_feature_counts(game, [article], phrases)
            for phrase, count in article_counts.items():
                phrase_frequency[phrase] += int(count > 0)
        vector = _feature_vector(game, available, phrases)
        feature_rows.append(vector)
        labels.append(int(row["sale_within_30_days"]))

    if len(set(labels)) < 2:
        raise RuntimeError(
            "Article training needs matched article dates with both sale and "
            "no-sale labels. Collect a newer Steam article snapshot."
        )
    if len(matched_game_ids) < 10:
        raise RuntimeError(
            "Article training needs matching article coverage across at least "
            f"10 games; found {len(matched_game_ids)}."
        )

    classifier = LogisticRegression(max_iter=1000, random_state=42)
    classifier.fit(feature_rows, labels)
    weights = {}
    for phrase, coefficient in zip(phrases, classifier.coef_[0]):
        weight = float(coefficient)
        if phrase_frequency[phrase] < 5:
            hand_weight = ARTICLE_LEXICON[phrase]
            weight = abs(weight) * (1 if hand_weight > 0 else -1)
            if weight == 0:
                weight = hand_weight
        weights[phrase] = round(weight, 8)
    artifact = {
        "intercept": float(classifier.intercept_[0]),
        "phrase_weights": weights,
        "training_samples": len(labels),
        "training_games": len(matched_game_ids),
    }
    return artifact, len(labels), len(matched_article_ids)


def _train_synthesis_model(
    records: list[tuple[dict[str, Any], dict[str, Any]]]
) -> dict[str, Any]:
    feature_names = [
        "historical_probability",
        "article_probability",
        "article_applies",
    ]
    features = [
        [float(sample.get(name, 0)) for name in feature_names]
        for sample, _ in records
    ]
    labels = [int(row["sale_within_30_days"]) for _, row in records]
    if len(set(labels)) < 2:
        raise RuntimeError("Synthesis training requires both sale and no-sale labels.")
    classifier = LogisticRegression(max_iter=1000, random_state=42)
    classifier.fit(features, labels)
    return {
        "feature_names": feature_names,
        "intercept": float(classifier.intercept_[0]),
        "coefficients": {
            name: float(coefficient)
            for name, coefficient in zip(feature_names, classifier.coef_[0])
        },
        "training_samples": len(labels),
    }


def _historical_oof_probabilities(
    rows_by_game: dict[int, tuple[dict[str, Any], list[dict[str, Any]], pd.Series]],
) -> list[tuple[dict[str, Any], float]]:
    """Generate time-ordered historical probabilities for synthesis training.

    The historical XGBoost model is trained on all rows for production.  Using
    its in-sample predictions to train synthesis would leak the labels into
    the second-stage model, so synthesis receives out-of-fold predictions
    instead.
    """
    rows = [row for _, game_rows, _ in rows_by_game.values() for row in game_rows]
    rows.sort(key=lambda row: pd.Timestamp(row["observation_date"]))
    if len(rows) < 10:
        return []

    probabilities: dict[int, float] = {}
    splitter = TimeSeriesSplit(n_splits=5)
    for train_indices, test_indices in splitter.split(rows):
        train_rows = [rows[index] for index in train_indices]
        if len({row["sale_within_30_days"] for row in train_rows}) < 2:
            continue
        fold_model = SteamSaleXGBoostModel().fit(train_rows)
        frame = pd.DataFrame([rows[index] for index in test_indices])
        predicted = fold_model.model.predict_proba(frame[SALE_FEATURE_COLUMNS])[:, 1]
        for index, probability in zip(test_indices, predicted):
            probabilities[index] = float(probability)

    return [
        (row, probabilities[index])
        for index, row in enumerate(rows)
        if index in probabilities
    ]


def _evaluate_synthesis_models(
    records: list[tuple[dict[str, Any], dict[str, Any]]]
) -> dict[str, float]:
    """Compare logistic synthesis with a simple probability blend on a holdout."""
    if len(records) < 20:
        return {}
    records = sorted(records, key=lambda item: item[1]["observation_date"])
    split = int(len(records) * 0.8)
    training, validation = records[:split], records[split:]
    feature_names = [
        "historical_probability",
        "article_probability",
        "article_applies",
    ]
    classifier = LogisticRegression(max_iter=1000, random_state=42)
    classifier.fit(
        [[float(sample.get(name, 0)) for name in feature_names] for sample, _ in training],
        [int(row["sale_within_30_days"]) for _, row in training],
    )
    actual = [int(row["sale_within_30_days"]) for _, row in validation]
    logistic_probabilities = classifier.predict_proba(
        [[float(sample.get(name, 0)) for name in feature_names] for sample, _ in validation]
    )[:, 1]
    best_weight = 0.5
    best_brier = float("inf")
    for historical_weight in [index / 20 for index in range(21)]:
        blended = [
            historical_weight * float(sample["historical_probability"])
            + (1 - historical_weight) * float(sample["article_probability"])
            for sample, _ in validation
        ]
        score = brier_score_loss(actual, blended)
        if score < best_brier:
            best_brier = score
            best_weight = historical_weight
    blend = [
        best_weight * float(sample["historical_probability"])
        + (1 - best_weight) * float(sample["article_probability"])
        for sample, _ in validation
    ]
    return {
        "validation_rows": len(validation),
        "logistic_brier": round(brier_score_loss(actual, logistic_probabilities), 6),
        "logistic_log_loss": round(log_loss(actual, logistic_probabilities, labels=[0, 1]), 6),
        "blend_brier": round(brier_score_loss(actual, blend), 6),
        "blend_log_loss": round(log_loss(actual, blend, labels=[0, 1]), 6),
        "blend_historical_weight": best_weight,
    }


def train_news_models() -> None:
    training_dir = Path(os.getenv("TRAINING_DATA_DIR", "/training_data"))
    model_dir = Path(os.getenv("MODEL_DIR", "/models"))
    game_map = _load_games(training_dir)
    selected_games = sorted(ARTICLE_GAME_IDS.intersection(game_map))
    if len(selected_games) < 10:
        raise RuntimeError(
            f"Expected 10 varied training games in games.csv; found {len(selected_games)}."
        )

    schedule_map = load_base_price_schedule_csv(
        training_dir / "base_price_history.csv"
    )
    articles_by_game = _dated_articles(training_dir / "articles" / "articles.json")
    xgb_path = model_dir / "steam_sale_xgboost.json"
    if not xgb_path.exists():
        raise FileNotFoundError(
            f"{xgb_path} is missing; train the existing XGBoost model first."
        )
    historical_model = SteamSaleXGBoostModel.load(xgb_path)
    all_game_rows = []
    rows_by_game: dict[
        int, tuple[dict[str, Any], list[dict[str, Any]], pd.Series]
    ] = {}

    for app_id in selected_games:
        csv_path = next(
            (
                path
                for path in (training_dir / "price_history").glob("*.csv")
                if (
                    match := re.search(r"(?:chart|price)[_-]?(\d+)", path.stem)
                )
                and int(match.group(1)) == app_id
            ),
            None,
        )
        if csv_path is None or app_id not in schedule_map:
            continue
        game = game_map[app_id]
        sparse_history = load_steamdb_csv(csv_path, schedule_map[app_id])
        history = expand_daily_history(sparse_history)
        rows = build_training_rows(game, history)
        if rows:
            normalized_history = _normalise_history(history)
            rows_by_game[app_id] = (
                game,
                rows,
                normalized_history["observation_date"],
            )
            all_game_rows.extend(
                (game, articles_by_game.get(app_id, []), row) for row in rows
            )

    used_games = len(rows_by_game)
    if used_games < 10:
        raise RuntimeError(
            f"Expected labeled price-history data for 10 varied games; found {used_games}."
        )

    article_artifact, article_samples, article_count = _train_article_model(all_game_rows)
    article_model = WeightedArticleSaleModel(article_artifact)
    synthesis_records = []
    oof_rows = _historical_oof_probabilities(rows_by_game)
    game_lookup = {
        app_id: (game, articles_by_game.get(app_id, []))
        for app_id, (game, _, _) in rows_by_game.items()
    }
    for row, historical_probability in oof_rows:
        game, articles = game_lookup[int(row["app_id"])]
        matched_articles = _articles_available_on(
            articles, row["observation_date"]
        )
        article_output = article_model.predict(game, matched_articles)
        article_applies = article_output["applicable"]
        synthesis_records.append(
            (
                {
                    "historical_probability": historical_probability,
                    "article_probability": (
                        article_output["sale_probability"]
                        if article_applies
                        else 0.0
                    ),
                    "article_applies": int(article_applies),
                    # Metadata for diagnostics/UI; excluded from synthesis features.
                    "article_count": (
                        article_output["article_count"] if article_applies else 0
                    ),
                },
                row,
            )
        )
    if len(synthesis_records) < 20:
        raise RuntimeError("Synthesis training needs at least 20 out-of-fold rows.")

    synthesis_artifact = _train_synthesis_model(synthesis_records)
    synthesis_artifact["validation"] = _evaluate_synthesis_models(synthesis_records)
    model_dir.mkdir(parents=True, exist_ok=True)
    article_path = model_dir / "steam_sale_nlp.json"
    synthesis_path = model_dir / "steam_sale_synthesis.json"
    with open(article_path, "w", encoding="utf-8") as file:
        json.dump(article_artifact, file, indent=2)
    with open(synthesis_path, "w", encoding="utf-8") as file:
        json.dump(synthesis_artifact, file, indent=2)

    with psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "password"),
        dbname=os.getenv("DB_NAME", "steam_sales"),
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE sale_predictions")

    print(f"games={used_games}")
    print(f"articles={article_count}")
    print(f"article_training_rows={article_samples}")
    print(f"synthesis_training_rows={len(synthesis_records)}")
    print(f"synthesis_validation={synthesis_artifact['validation']}")
    print(f"article_model_path={article_path}")
    print(f"synthesis_model_path={synthesis_path}")
    print("prediction_cache_cleared=true")


if __name__ == "__main__":
    train_news_models()
