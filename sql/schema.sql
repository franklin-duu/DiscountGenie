CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE games (
    app_id INT PRIMARY KEY, -- Steam App ID
    name VARCHAR(255) NOT NULL,
    publisher VARCHAR(255),
    developer VARCHAR(255),
    base_price DECIMAL(10,2),
    current_price DECIMAL(10,2),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_watchlist (
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    app_id INT REFERENCES games(app_id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (app_id)
);