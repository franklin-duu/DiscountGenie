CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE games (
    app_id INT PRIMARY KEY, -- Steam App ID
    name VARCHAR(255) NOT NULL,
    publisher VARCHAR(255),
    developer VARCHAR(255),
    base_price DECIMAL(10,2),
    current_price DECIMAL(10,2),
    discount_percent DECIMAL(5,2) DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE game_price_history (
    id BIGSERIAL PRIMARY KEY,
    app_id INT NOT NULL REFERENCES games(app_id) ON DELETE CASCADE,
    base_price DECIMAL(10,2),
    current_price DECIMAL(10,2),
    discount_percent DECIMAL(5,2) NOT NULL DEFAULT 0,
    first_recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (last_recorded_at >= first_recorded_at)
);

CREATE INDEX idx_price_history_app_date
ON game_price_history(app_id, last_recorded_at DESC);

-- Compressed storage remains in game_price_history. This view expands each
-- uninterrupted price period into one logical UTC calendar-day observation
-- only when the model queries it.
CREATE OR REPLACE VIEW game_price_history_daily AS
WITH expanded AS (
    SELECT
        h.id,
        h.app_id,
        day::date AS observation_date,
        h.base_price,
        h.current_price,
        h.discount_percent,
        h.first_recorded_at,
        h.last_recorded_at
    FROM game_price_history AS h
    CROSS JOIN LATERAL generate_series(
        date_trunc('day', h.first_recorded_at AT TIME ZONE 'UTC'),
        date_trunc('day', h.last_recorded_at AT TIME ZONE 'UTC'),
        interval '1 day'
    ) AS day
), ranked AS (
    SELECT
        expanded.*,
        row_number() OVER (
            PARTITION BY app_id, observation_date
            ORDER BY first_recorded_at DESC, id DESC
        ) AS row_rank
    FROM expanded
)
SELECT
    app_id,
    observation_date,
    base_price,
    current_price,
    discount_percent,
    first_recorded_at,
    last_recorded_at
FROM ranked
WHERE row_rank = 1;

CREATE INDEX idx_price_history_app_first_date
ON game_price_history(app_id, first_recorded_at DESC);

-- not used at the moment but can be used in the future use db data to train the ml model
CREATE TABLE sale_training_examples (
    id BIGSERIAL PRIMARY KEY,
    app_id INT NOT NULL REFERENCES games(app_id) ON DELETE CASCADE,
    observation_date DATE NOT NULL,
    current_price DECIMAL(10,2),
    base_price DECIMAL(10,2),
    discount_percent INT NOT NULL DEFAULT 0,
    sale_events_last_30_days INT NOT NULL DEFAULT 0,
    sale_events_last_90_days INT NOT NULL DEFAULT 0,
    sale_events_last_180_days INT NOT NULL DEFAULT 0,
    days_since_last_sale INT NOT NULL,
    average_discount_last_180_days DECIMAL(5,2) NOT NULL DEFAULT 0,
    month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    sale_within_30_days BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (app_id, observation_date)
);

CREATE INDEX idx_training_examples_app_date
ON sale_training_examples(app_id, observation_date);

CREATE TABLE user_watchlist (
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    app_id INT REFERENCES games(app_id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, app_id)
);

CREATE TABLE friendships (
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    friend_id INT REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'pending', -- pending, accepted
    PRIMARY KEY (user_id, friend_id)
);

CREATE TABLE sale_predictions (
    app_id INT REFERENCES games(app_id) ON DELETE CASCADE,
    model_1_score DECIMAL(5,4),
    model_2_score DECIMAL(5,4),
    final_probability DECIMAL(5,4),
    predicted_sale_window VARCHAR(100),
    model_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (app_id)
);

ALTER TABLE sale_predictions
ADD COLUMN IF NOT EXISTS model_details JSONB NOT NULL DEFAULT '{}'::jsonb;
