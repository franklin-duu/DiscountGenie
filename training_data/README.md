# Training Data

Place unchanged SteamDB chart CSV files in `price_history/`.

The slow Steam importer writes game metadata to `games.csv`. This includes the
App ID, name, developer, publisher, and current Steam price fields.

Run it from the project root with:

```bash
docker compose run --rm ai-service python -m ml_training.slow_import_games
```

The filename must contain the Steam App ID, for example:

```text
price_history/steamdb_chart_620.csv
```

Enter base-price changes in `base_price_history.csv`. Add one row whenever a
game's regular price changes:

```csv
app_id,effective_from,base_price,country_code
620,2012-11-22,19.99,US
620,2018-06-14,9.99,US
```

Use ISO dates (`YYYY-MM-DD`) and numeric prices without currency symbols. The
trainer applies the latest base price on or before each CSV observation date.

During training, observations where `final_price` is greater than the entered
base price are reported as price anomalies and skipped. The original CSV rows
are not modified.

## Importing history into PostgreSQL

Training reads the CSV files directly, expands sparse price changes into one
observation per calendar day, and while the prediction API reads equivalent
daily history from PostgreSQL. Import the same corrected CSV data with:

```bash
docker compose build ai-service
docker compose run --rm ai-service python -m ml_training.import_price_history
```

The importer applies the same base-price and anomaly rules as training. It
replaces each app's existing imported history in one transaction and can be
rerun safely after correcting CSV data or anomaly handling.

## Training the model

After importing metadata and price history, run:

```bash
docker compose run --rm ai-service python -m ml_training.train_model
```

The model is saved inside Docker at `/models/steam_sale_xgboost.json`. After
retraining, clear cached predictions so the API generates fresh results:

```bash
docker compose exec -T db psql -U postgres -d steam_sales -c 'TRUNCATE sale_predictions;'
docker compose restart ai-service
```

## Steam article and synthesis models

Collect a recent, bounded Steam News snapshot for the ten varied App IDs in
`ml_training/collect_articles.py`. The command saves article metadata and
short text excerpts to `articles/articles.json`. That file is mounted into the
AI service and is the only article input used by inference and model training;
prediction refreshes never fetch news.

Train the article lexicon and synthesis model after training XGBoost:

```bash
docker compose run --rm ai-service python -m ml_training.collect_articles
docker compose run --rm ai-service python -m ml_training.train_news_models
docker compose restart ai-service
```

Training joins article dates to the existing `sale_within_30_days` labels for
the same Steam price-history rows. It requires price history for at least ten
games and an existing XGBoost model. It reports game/article sample counts,
writes `steam_sale_nlp.json` and `steam_sale_synthesis.json` under `/models`,
and clears `sale_predictions` so old dummy forecasts are not reused.
