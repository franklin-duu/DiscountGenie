# Training data

Place unchanged SteamDB chart CSV files in `price_history/`.

The slow Steam importer writes game metadata to `games.csv`. This includes the
App ID, name, developer, publisher, and current Steam price fields.

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
