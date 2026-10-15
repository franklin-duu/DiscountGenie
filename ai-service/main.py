from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Steam Sale AI Inference Service")

class PredictionRequest(BaseModel):
    app_id: int
    days_since_last_sale: int
    discount_history_avg: float
    news_sentiment_score: float

@app.post("/predict")
def predict_sale(data: PredictionRequest):
    # Placeholder for Model 1, Model 2, and Model 3 evaluation logic
    # In production, load your pickled XGBoost / Meta-models here and run inference.
    
    mock_probability = 0.78 # 78% chance of sale soon
    predicted_window = "Next 14 Days"
    
    return {
        "app_id": data.app_id,
        "sale_probability": mock_probability,
        "predicted_window": predicted_window
    }