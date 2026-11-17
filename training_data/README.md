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

Training reads the CSV files directly, while the prediction API reads price
history from PostgreSQL. Import the same corrected CSV data with:

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
