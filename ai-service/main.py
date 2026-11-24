import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from games_db_manager import GamesDBManager
from prediction_models import (
    SteamSaleXGBoostModel,
    SynthesisLogisticModel,
    WeightedArticleSaleModel,
    run_prediction_pipeline,
)
from steam_api import SteamAPIError

app = FastAPI(title="Steam Sale AI Inference Service")


class PredictionRequest(BaseModel):
    app_id: int


def _model_paths() -> dict[str, Path]:
    model_dir = Path(os.getenv("MODEL_DIR", "/models"))
    return {
        "historical": model_dir / "steam_sale_xgboost.json",
        "nlp": model_dir / "steam_sale_nlp.json",
        "synthesis": model_dir / "steam_sale_synthesis.json",
    }


def _article_snapshot_path() -> Path:
    return (
        Path(os.getenv("TRAINING_DATA_DIR", "/training_data"))
        / "articles"
        / "articles.json"
    )


def _file_signature(path: Path) -> tuple[str, Optional[int], Optional[int]]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return str(path), None, None
    return str(path), stat.st_mtime_ns, stat.st_size


def _prediction_artifact_signature() -> tuple[
    tuple[str, Optional[int], Optional[int]], ...
]:
    return tuple(
        _file_signature(path)
        for path in (*_model_paths().values(), _article_snapshot_path())
    )


def _artifact_version(signature: tuple[Any, ...]) -> str:
    encoded = json.dumps(signature, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@lru_cache(maxsize=1)
def _load_trained_models(_signature):
    paths = _model_paths()
    historical = (
        SteamSaleXGBoostModel.load(paths["historical"])
        if paths["historical"].exists()
        else None
    )
    article = (
        WeightedArticleSaleModel.load(paths["nlp"])
        if paths["nlp"].exists()
        else WeightedArticleSaleModel()
    )
    synthesis = (
        SynthesisLogisticModel.load(paths["synthesis"])
        if paths["synthesis"].exists()
        else SynthesisLogisticModel()
    )
    is_demo = not all(path.exists() for path in paths.values())
    return historical, article, synthesis, is_demo


@lru_cache(maxsize=1)
def _article_snapshot(_signature) -> list[dict[str, Any]]:
    article_path = _article_snapshot_path()
    if not article_path.exists():
        return []
    with open(article_path, encoding="utf-8") as file:
        payload = json.load(file)
    return payload.get("articles", [])


def _load_articles(app_id: int) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    return [
        article
        for article in _article_snapshot(
            _file_signature(_article_snapshot_path())
        )
        if int(article.get("app_id", 0)) == app_id
        and cutoff
        <= datetime.fromisoformat(
            re.sub(
                r"(\.\d{6})\d+(?=[+-]\d{2}:\d{2}$)",
                r"\1",
                article["published_at"].replace("Z", "+00:00"),
            )
        ).astimezone(timezone.utc)
        <= now
    ]


def _header_image(app_id: int) -> str:
    return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"


def _cached_response(game, saved_prediction):
    details = saved_prediction.get("model_details") or {}
    updated_at = saved_prediction.get("updated_at")
    response = {
        "app_id": game["app_id"],
        "game": details.get("game") or {
            "app_id": game["app_id"],
            "name": game["name"],
            "publisher": game.get("publisher"),
            "developer": game.get("developer"),
            "current_price": (
                float(game["current_price"])
                if game.get("current_price") is not None
                else None
            ),
            "discount_percent": float(game.get("discount_percent") or 0),
        },
        "prediction": details.get("prediction") or {
            "sale_probability": float(saved_prediction["final_probability"]),
            "predicted_sale_window": saved_prediction["predicted_sale_window"],
        },
        "models": details.get("models", {}),
        "effective_weights": details.get("effective_weights", {}),
        "cached": True,
        "demo": bool(details.get("demo", True)),
        "updated_at": updated_at.isoformat() if updated_at else None,
    }
    return response


def _prediction_for_game(manager: GamesDBManager, game: dict[str, Any]):
    app_id = int(game["app_id"])
    artifact_signature = _prediction_artifact_signature()
    artifact_version = _artifact_version(artifact_signature)
    saved_prediction = manager.get_prediction(app_id)
    if saved_prediction and saved_prediction.get("updated_at"):
        prediction_updated_at = saved_prediction["updated_at"]
        game_updated_at = game.get("last_updated")
        if (
            game_updated_at
            and prediction_updated_at >= game_updated_at
            and saved_prediction.get("model_details")
            and saved_prediction["model_details"].get("artifact_version")
            == artifact_version
        ):
            return _cached_response(game, saved_prediction)

    historical, article, synthesis, is_demo = _load_trained_models(
        artifact_signature
    )
    result = run_prediction_pipeline(
        game,
        manager.get_daily_price_history(app_id),
        _load_articles(app_id),
        historical_model=historical,
        article_model=article,
        synthesis_model=synthesis,
    )
    result.update({"cached": False, "demo": is_demo})
    models = result["models"]
    manager.save_prediction(
        app_id,
        models["historical"]["sale_probability"],
        (
            models["nlp"]["sale_probability"]
            if models["nlp"]["applicable"]
            else 0.0
        ),
        result["prediction"]["sale_probability"],
        result["prediction"]["predicted_sale_window"],
        {
            "game": result["game"],
            "prediction": result["prediction"],
            "models": models,
            "effective_weights": result["effective_weights"],
            "demo": is_demo,
            "artifact_version": artifact_version,
        },
    )
    return result


@app.post("/predict")
def predict_sale(data: PredictionRequest):
    manager = None
    try:
        manager = GamesDBManager()
        game = manager.get_game(data.app_id)
        if game is None:
            try:
                game = manager.get_or_fetch_game(data.app_id, "us", "en")
            except SteamAPIError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
        else:
            try:
                game = manager.get_or_fetch_game(data.app_id, "us", "en")
            except SteamAPIError:
                pass
        return _prediction_for_game(manager, game)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Prediction service is unavailable. Check the database connection.",
        ) from error
    finally:
        if manager is not None:
            manager.close()


@app.get("/ranked")
def ranked_games(limit: int = Query(default=20, ge=1, le=30)):
    manager = None
    try:
        manager = GamesDBManager()
        ranked = []
        for game in manager.get_rankable_games(limit):
            try:
                game = manager.get_or_fetch_game(
                    int(game["app_id"]), "us", "en"
                )
            except SteamAPIError:
                pass
            result = _prediction_for_game(manager, game)
            game_data = result["game"]
            ranked.append(
                {
                    "app_id": game_data["app_id"],
                    "name": game_data["name"],
                    "publisher": game_data.get("publisher"),
                    "developer": game_data.get("developer"),
                    "header_image": _header_image(game_data["app_id"]),
                    "current_price": game_data.get("current_price"),
                    "discount_percent": game_data.get("discount_percent", 0),
                    "sale_probability": result["prediction"]["sale_probability"],
                    "predicted_sale_window": result["prediction"][
                        "predicted_sale_window"
                    ],
                    "expected_discount_percent": result["prediction"].get(
                        "expected_discount_percent"
                    ),
                }
            )
        ranked.sort(key=lambda item: item["sale_probability"], reverse=True)
        return {"games": ranked}
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Ranking service is unavailable. Check the database connection.",
        ) from error
    finally:
        if manager is not None:
            manager.close()


@app.get("/search")
def search_games(q: str = Query(min_length=1, max_length=100)):
    manager = None
    try:
        manager = GamesDBManager()
        games = manager.search_games(q.strip())
        return {
            "games": [
                {
                    **game,
                    "header_image": _header_image(game["app_id"]),
                }
                for game in games
            ]
        }
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Search service is unavailable. Check the database connection.",
        ) from error
    finally:
        if manager is not None:
            manager.close()
