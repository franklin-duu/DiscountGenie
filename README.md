# DiscountGenie

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Setup Commands](#initial-setup-commands)
- [Run Commands](#run-commands)
- [Viewing Training Data](#viewing-training-data)
- [Training the Model](#training-the-model)
- [Testing Predictions](#testing-predictions)
- [Data Persistence](#data-persistence)
- [Stopping the Application](#stopping-the-application)
- [Notes](#notes)

---

## Prerequisites
- Node.js
- Docker Desktop with Docker Compose

---

## Environment Variables
The default values are already configured in `docker-compose.yml`. Create a
`.env` file in the `server` directory only if you need to override them:

DB_HOST=db

DB_PORT=5432

DB_USER=postgres

DB_PASSWORD=password

DB_NAME=steam_sales

AI_SERVICE_URL=http://ai-service:8000

---

## Initial Setup Commands
### --- Frontend Setup ---
```bash
cd client
npm install
```

### --- Database & Docker Services Setup ---
```bash
# Ensure you are in the project root directory containing docker-compose.yml
docker compose build
docker compose up -d
```

---

## Run Commands

### --- Run Backend ---
```bash
docker compose up -d db ai-service backend
```

### --- Run Frontend (In separate terminal) ---
```bash
cd client
npm run dev
```

## Viewing Training Data

The PostgreSQL database stores generated ML training examples in the
`sale_training_examples` table. To open a PostgreSQL shell inside the database
container:

```bash
docker compose exec db psql -U postgres -d steam_sales
```

Useful queries:

```sql
SELECT * FROM sale_training_examples
ORDER BY app_id, observation_date;

SELECT * FROM game_price_history_daily
WHERE app_id = 620
ORDER BY observation_date;
```

Price history is stored compactly as uninterrupted price periods in
`game_price_history`. The `game_price_history_daily` view expands those periods
into one logical UTC calendar-day observation when the model or a query needs
daily history. Training and prediction both use this daily representation;
only the database storage remains compressed.

## Training the Model

Run these commands from the project root. Training examples use the Steam price
history files in `training_data/price_history/` and the base-price schedules.

### Import Steam game metadata

This imports metadata for App IDs found in `training_data/price_history/` into
PostgreSQL and writes it to `training_data/games.csv`:

```bash
docker compose run --rm ai-service python -m ml_training.slow_import_games
```

It waits three seconds between Steam requests and skips games already in the
database. Add `--force` to refresh existing metadata, or use
`--delay 10` for a ten-second delay.

### Import CSV price history

Load the corrected SteamDB histories into PostgreSQL:

```bash
docker compose build ai-service
docker compose run --rm ai-service python -m ml_training.import_price_history
```

The CSV files are treated as the source of truth. Existing imported history for
each app is replaced transactionally, so this is safe to rerun after correcting
anomaly handling or base prices.

### Train the XGBoost model

The trainer reads `training_data/base_price_history.csv` and the CSV files in
`training_data/price_history/`, expands sparse price changes into daily
observations, generates labeled rows, saves them to
`sale_training_examples`, and writes the model to:

```bash
docker compose run --rm ai-service python -m ml_training.train_model
```

The model is stored in the Docker volume at:

```text
/models/steam_sale_xgboost.json
```

After retraining, clear cached predictions and restart the AI service:

```bash
docker compose exec -T db psql -U postgres -d steam_sales -c 'TRUNCATE sale_predictions;'
docker compose restart ai-service
```

When retraining the complete model stack, retrain the XGBoost model first and
then retrain the article and synthesis models so every model uses the same
daily observation format:

```bash
docker compose build ai-service
docker compose run --rm ai-service python -m ml_training.train_model
docker compose run --rm ai-service python -m ml_training.train_news_models
docker compose up -d --force-recreate ai-service
```

### Collect articles and train the news models

The bounded collector snapshots Steam app news for ten varied games from
`games.csv` into `training_data/articles/articles.json`. Training then works
from that saved snapshot without a news request:

```bash
docker compose run --rm ai-service python -m ml_training.collect_articles
docker compose run --rm ai-service python -m ml_training.train_news_models
docker compose restart ai-service
```

Train the existing XGBoost model first. The article/synthesis command reuses
that model, trains the weighted article lexicon and synthesis logistic
regression, prints the game/article counts, and truncates `sale_predictions`
after successful training. The trained JSON files are saved in `/models` on
the existing `model_data` volume.

The local backend uses `DB_*` values from Compose. For Compose, put
`JWT_SECRET` in the repository-root `.env` file (ignored by Git) if login
tokens should remain valid across backend restarts; direct `npm start` can
load it from `server/.env`. Without it, a fresh local-only key is generated at
startup.

## Testing Predictions

Test the AI service directly:

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"app_id":620}'
```

The response should contain `"model": "steam_sale_xgboost_v1"`.

The home-page ranking is also available at:

```bash
curl http://localhost:5000/api/games/ranked
```

Test through the backend:

```bash
curl http://localhost:5000/api/games/620/insights
```

Run the automated AI-service tests:

```bash
docker compose exec -T ai-service python -m unittest discover -s tests -p 'test_*.py'
```

## Data Persistence

Docker uses named volumes for PostgreSQL data and trained model files:

- `postgres_data` stores games, price history, training examples, and predictions.
- `model_data` stores files such as `/models/steam_sale_xgboost.json`. The
  model is not normally visible in the repository.

Do not run the following command unless you intentionally want to delete all
database and model data:

```bash
docker compose down -v
```

---

## Stopping The Application

### --- Stop Frontend---
```bash
Ctrl + C
```

### --- Stop Backend & Docker Services---
```bash
Ctrl + C
# OR run the following to tear down the containers completely:
docker compose down
```

`docker compose down` removes containers but preserves the named volumes.

---

## Notes
- PostgreSQL, the Python AI microservice, and the Node.js backend run entirely inside Docker containers.
- The React frontend runs locally via Vite on your host machine.
- Run `npm install` once unless the frontend dependencies change.
- Make sure Docker Desktop is running before executing Docker Compose commands.
