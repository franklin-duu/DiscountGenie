from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from games_db_manager import GamesDBManager
from prediction_models import run_prediction_pipeline
from steam_api import SteamAPIError

app = FastAPI(title="Steam Sale AI Inference Service")


class PredictionRequest(BaseModel):
    app_id: int


DEMO_GAME = {
    "app_id": 730,
    "name": "Counter-Strike 2",
    "publisher": "Valve",
    "developer": "Valve",
    "base_price": 14.99,
    "current_price": 7.49,
    "discount_percent": 50.0,
}

DEMO_ARTICLES = [
    {
        "title": "Demo article input",
        "text": "Placeholder article text for the future game, developer, and publisher news model.",
        "source": "demo-fixture",
    }
]


def _cached_response(game, saved_prediction):
    details = saved_prediction.get("model_details") or {}
    updated_at = saved_prediction.get("updated_at")
    return {
        "app_id": game["app_id"],
        "game": details.get("game", {}),
        "prediction": {
            "sale_probability": float(saved_prediction["final_probability"]),
            "predicted_sale_window": saved_prediction["predicted_sale_window"],
        },
        "models": details.get("models", {}),
        "cached": True,
        "demo": True,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


@app.post("/predict")
def predict_sale(data: PredictionRequest):
    manager = None
    try:
        manager = GamesDBManager()
        game = manager.get_game(data.app_id)

        if game is None and data.app_id == DEMO_GAME["app_id"]:
            game = manager.input_game(**DEMO_GAME)
        elif game is None:
            try:
                game = manager.get_or_fetch_game(data.app_id, "us", "en")
            except SteamAPIError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
        else:
            try:
                game = manager.get_or_fetch_game(data.app_id, "us", "en")
            except SteamAPIError:
                pass

        saved_prediction = manager.get_prediction(data.app_id)
        if saved_prediction and saved_prediction.get("updated_at"):
            game_updated_at = game.get("last_updated")
            prediction_updated_at = saved_prediction["updated_at"]
            if (
                game_updated_at
                and prediction_updated_at >= game_updated_at
                and saved_prediction.get("model_details")
            ):
                return _cached_response(game, saved_prediction)

        result = run_prediction_pipeline(
            game,
            manager.get_price_history(data.app_id),
            DEMO_ARTICLES,
        )
        models = result["models"]
        manager.save_prediction(
            data.app_id,
            models["historical"]["sale_probability"],
            models["nlp"]["sale_probability"],
            result["prediction"]["sale_probability"],
            result["prediction"]["predicted_sale_window"],
            {"game": result["game"], "models": models},
        )
        result.update({"cached": False, "demo": True})
        return result
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