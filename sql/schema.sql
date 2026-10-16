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
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (app_id)
);
