# READ ME

## Table of Contents
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Setup Commands](#initial-setup-commands)
- [Run Commands](#run-commands)
- [Viewing Training Data](#viewing-training-data)
- [Data Persistence](#data-persistence)
- [Stopping the Application](#stopping-the-application)
- [Notes](#notes)

---

## Prerequisites
- Node.js
- Python 3.x
- PostgreSQL (running locally)

---

## Environment Variables
Create a `.env` file in the `server` directory or configure them in your `docker-compose.yml` if needed:

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
docker-compose build
docker-compose up -d
```

---

## Run Commands

### --- Run Backend ---
```bash
docker-compose up
```

### --- Run Frontend (In seperate terminal) ---
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

Training examples are generated from compressed price history and can be saved
through `GamesDBManager.save_training_examples()`.

## Training the Model

After the database contains games with at least 30 days of price history, run:

```bash
docker compose run --rm ai-service python train_model.py
```

The trainer reads manually maintained base prices from
`training_data/base_price_history.csv` and SteamDB CSVs from
`training_data/price_history/`. SteamDB files should include the App ID in
their filename, such as `steamdb_chart_620.csv`.

To slowly populate the `games` table and write metadata to
`training_data/games.csv` using the App IDs in those filenames,
run the one-time importer:

```bash
docker compose run --rm ai-service python slow_import_games.py
```

It waits three seconds between Steam requests by default, skips games already
in the database, and reuses the existing `steam_api.py` caller. To refresh
existing games, add `--force`. To use a longer delay, for example ten seconds:

```bash
docker compose run --rm ai-service python slow_import_games.py --delay 10
```

The command generates labeled rows, saves them to `sale_training_examples`,
trains the XGBoost model, and saves it to:

```text
/models/steam_sale_xgboost.json
```

## Data Persistence

Docker uses named volumes for PostgreSQL data and trained model files:

- `postgres_data` stores games, price history, training examples, and predictions.
- `model_data` stores files such as `/models/steam_sale_xgboost.json`.

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
docker-compose down
```

`docker compose down` removes containers but preserves the named volumes.

---

## Notes
- PostgreSQL, the Python AI microservice, and the Node.js backend run entirely inside Docker containers.
- The React frontend runs locally via Vite on your host machine.
- Only run npm install and initial setup steps once.
- Make sure Docker Desktop is running on your machine before executing docker-compose up.
