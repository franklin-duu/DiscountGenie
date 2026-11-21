const crypto = require('crypto');
require('dotenv').config();
const express = require('express');
const cors = require('cors');
const axios = require('axios');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const { Pool } = require('pg');

const app = express();
app.use(express.json());
app.use(cors());

const PORT = process.env.PORT || 5000;
const AI_SERVICE_URL = process.env.AI_SERVICE_URL || 'http://localhost:8000';
const JWT_SECRET = process.env.JWT_SECRET || crypto.randomBytes(32).toString('hex');
if (!process.env.JWT_SECRET) {
    console.warn('JWT_SECRET is unset; login tokens will not survive a backend restart.');
}

const pool = new Pool({
    host: process.env.DB_HOST || 'localhost',
    port: Number(process.env.DB_PORT || 5432),
    user: process.env.DB_USER || 'postgres',
    password: process.env.DB_PASSWORD || 'password',
    database: process.env.DB_NAME || 'steam_sales',
});

class HttpError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
    }
}

const asyncHandler = (handler) => (req, res, next) => {
    Promise.resolve(handler(req, res, next)).catch(next);
};

function authenticate(req, res, next) {
    const token = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
    if (!token) return res.status(401).json({ error: 'Authentication required' });
    try {
        req.userId = Number(jwt.verify(token, JWT_SECRET).sub);
        if (!Number.isInteger(req.userId) || req.userId <= 0) {
            return res.status(401).json({ error: 'Invalid authentication token' });
        }
        return next();
    } catch (error) {
        return res.status(401).json({ error: 'Invalid or expired authentication token' });
    }
}

function validAppId(value) {
    const appId = Number(value);
    return Number.isInteger(appId) && appId > 0 ? appId : null;
}

function publicUser(user) {
    return { id: user.id, username: user.username, email: user.email };
}

app.get('/api/games/:appId/insights', asyncHandler(async (req, res) => {
    const numericAppId = validAppId(req.params.appId);
    if (!numericAppId) throw new HttpError(400, 'Invalid Steam app ID');
    const response = await axios.post(`${AI_SERVICE_URL}/predict`, {
        app_id: numericAppId,
    });
    res.json({
        appId: response.data.app_id,
        game: response.data.game,
        predictions: response.data.prediction,
        models: response.data.models,
        effectiveWeights: response.data.effective_weights,
        matchedPhrases: response.data.models?.nlp?.matched_phrases || [],
        cached: response.data.cached,
        demo: response.data.demo,
        updatedAt: response.data.updated_at,
    });
}));

app.get('/api/games/search', asyncHandler(async (req, res) => {
    const query = String(req.query.q || '').trim();
    if (!query || query.length > 100) throw new HttpError(400, 'Enter a search term');
    const response = await axios.get(`${AI_SERVICE_URL}/search`, { params: { q: query } });
    res.json(response.data);
}));

app.get('/api/games/ranked', asyncHandler(async (req, res) => {
    const response = await axios.get(`${AI_SERVICE_URL}/ranked`, {
        params: { limit: Math.min(validAppId(req.query.limit) || 20, 30) },
    });
    res.json(response.data);
}));

app.post('/api/auth/register', asyncHandler(async (req, res) => {
    const { username, email, password } = req.body || {};
    if (typeof username !== 'string' || username.trim().length < 3 || username.trim().length > 50) {
        throw new HttpError(400, 'Username must be between 3 and 50 characters');
    }
    if (
        typeof email !== 'string' ||
        email.length > 255 ||
        !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
    ) {
        throw new HttpError(400, 'Enter a valid email address');
    }
    if (
        typeof password !== 'string' ||
        password.length < 8 ||
        Buffer.byteLength(password, 'utf8') > 72
    ) {
        throw new HttpError(400, 'Password must be between 8 and 72 characters');
    }
    const passwordHash = await bcrypt.hash(password, 12);
    let result;
    try {
        result = await pool.query(
            `INSERT INTO users (username, email, password_hash)
             VALUES ($1, $2, $3)
             RETURNING id, username, email`,
            [username.trim(), email.trim().toLowerCase(), passwordHash],
        );
    } catch (error) {
        if (error.code === '23505') throw new HttpError(409, 'Username or email is already registered');
        throw error;
    }
    const user = publicUser(result.rows[0]);
    const token = jwt.sign({}, JWT_SECRET, { subject: String(user.id), expiresIn: '7d' });
    res.status(201).json({ token, user });
}));

app.post('/api/auth/login', asyncHandler(async (req, res) => {
    const { email, password } = req.body || {};
    if (typeof email !== 'string' || typeof password !== 'string') {
        throw new HttpError(400, 'Email and password are required');
    }
    const result = await pool.query(
        'SELECT id, username, email, password_hash FROM users WHERE lower(email) = lower($1)',
        [email.trim()],
    );
    const user = result.rows[0];
    if (!user || !(await bcrypt.compare(password, user.password_hash))) {
        throw new HttpError(401, 'Email or password is incorrect');
    }
    const token = jwt.sign({}, JWT_SECRET, { subject: String(user.id), expiresIn: '7d' });
    res.json({ token, user: publicUser(user) });
}));

app.get('/api/auth/me', authenticate, asyncHandler(async (req, res) => {
    const result = await pool.query(
        `SELECT u.id, u.username, u.email,
                (SELECT count(*)::int FROM user_watchlist w WHERE w.user_id = u.id) AS watchlist_count,
                (SELECT count(*)::int FROM (
                    SELECT friend_id AS id FROM friendships
                    WHERE user_id = u.id AND status = 'accepted'
                    UNION
                    SELECT user_id AS id FROM friendships
                    WHERE friend_id = u.id AND status = 'accepted'
                ) accepted_friends) AS friend_count
         FROM users u WHERE u.id = $1`,
        [req.userId],
    );
    if (!result.rows[0]) throw new HttpError(404, 'Account not found');
    res.json(result.rows[0]);
}));

app.get('/api/watchlist', authenticate, asyncHandler(async (req, res) => {
    const result = await pool.query(
        `SELECT g.app_id, g.name, g.publisher, g.developer, g.current_price,
                g.discount_percent, w.added_at,
                'https://cdn.cloudflare.steamstatic.com/steam/apps/' || g.app_id || '/header.jpg' AS header_image
         FROM user_watchlist w JOIN games g ON g.app_id = w.app_id
         WHERE w.user_id = $1 ORDER BY w.added_at DESC`,
        [req.userId],
    );
    res.json({ games: result.rows });
}));

app.post('/api/watchlist', authenticate, asyncHandler(async (req, res) => {
    const appId = validAppId(req.body?.appId);
    if (!appId) throw new HttpError(400, 'Invalid Steam app ID');
    const game = await pool.query('SELECT 1 FROM games WHERE app_id = $1', [appId]);
    if (!game.rowCount) throw new HttpError(404, 'Steam game is not in the local catalog');
    await pool.query(
        'INSERT INTO user_watchlist (user_id, app_id) VALUES ($1, $2) ON CONFLICT DO NOTHING',
        [req.userId, appId],
    );
    res.status(204).end();
}));

app.delete('/api/watchlist/:appId', authenticate, asyncHandler(async (req, res) => {
    const appId = validAppId(req.params.appId);
    if (!appId) throw new HttpError(400, 'Invalid Steam app ID');
    await pool.query('DELETE FROM user_watchlist WHERE user_id = $1 AND app_id = $2', [
        req.userId,
        appId,
    ]);
    res.status(204).end();
}));

app.post('/api/friends/requests', authenticate, asyncHandler(async (req, res) => {
    const username = String(req.body?.username || '').trim();
    if (!username) throw new HttpError(400, 'Enter a username');
    const target = await pool.query('SELECT id FROM users WHERE lower(username) = lower($1)', [username]);
    if (!target.rowCount) throw new HttpError(404, 'User not found');
    const friendId = target.rows[0].id;
    if (friendId === req.userId) throw new HttpError(400, 'You cannot add yourself');
    const existing = await pool.query(
        `SELECT user_id, friend_id, status FROM friendships
         WHERE (user_id = $1 AND friend_id = $2) OR (user_id = $2 AND friend_id = $1)`,
        [req.userId, friendId],
    );
    if (existing.rows.some((row) => row.status === 'accepted')) {
        throw new HttpError(409, 'You are already friends');
    }
    if (existing.rowCount) throw new HttpError(409, 'A friend request is already pending');
    await pool.query(
        `INSERT INTO friendships (user_id, friend_id, status)
         VALUES ($1, $2, 'pending') ON CONFLICT (user_id, friend_id)
         DO UPDATE SET status = 'pending'`,
        [req.userId, friendId],
    );
    res.status(201).json({ sent: true });
}));

app.post('/api/friends/:friendId/accept', authenticate, asyncHandler(async (req, res) => {
    const friendId = validAppId(req.params.friendId);
    if (!friendId || friendId === req.userId) throw new HttpError(400, 'Invalid friend request');
    const client = await pool.connect();
    try {
        await client.query('BEGIN');
        const result = await client.query(
            `UPDATE friendships SET status = 'accepted'
             WHERE user_id = $1 AND friend_id = $2 AND status = 'pending'
             RETURNING user_id`,
            [friendId, req.userId],
        );
        if (!result.rowCount) throw new HttpError(404, 'Friend request not found');
        await client.query(
            `INSERT INTO friendships (user_id, friend_id, status)
             VALUES ($1, $2, 'accepted')
             ON CONFLICT (user_id, friend_id) DO UPDATE SET status = 'accepted'`,
            [req.userId, friendId],
        );
        await client.query('COMMIT');
        res.status(204).end();
    } catch (error) {
        try {
            await client.query('ROLLBACK');
        } catch (rollbackError) {
            console.error('Could not roll back friend acceptance:', rollbackError);
        }
        throw error;
    } finally {
        client.release();
    }
}));

app.get('/api/friends', authenticate, asyncHandler(async (req, res) => {
    const result = await pool.query(
        `WITH relations AS (
            SELECT friend_id AS id, status, true AS outgoing
            FROM friendships WHERE user_id = $1
            UNION ALL
            SELECT user_id AS id, status, false AS outgoing
            FROM friendships WHERE friend_id = $1
        ), unique_relations AS (
            SELECT DISTINCT ON (id) id, status, outgoing FROM relations
            ORDER BY id, (status = 'accepted') DESC, outgoing
        )
        SELECT u.id, u.username, r.status, r.outgoing,
               COALESCE(json_agg(json_build_object(
                   'app_id', g.app_id, 'name', g.name,
                   'header_image', 'https://cdn.cloudflare.steamstatic.com/steam/apps/' || g.app_id || '/header.jpg'
               )) FILTER (WHERE g.app_id IS NOT NULL), '[]'::json) AS shared_games
        FROM unique_relations r JOIN users u ON u.id = r.id
        LEFT JOIN user_watchlist mine ON mine.user_id = $1
        LEFT JOIN user_watchlist theirs ON r.status = 'accepted'
            AND theirs.user_id = u.id AND theirs.app_id = mine.app_id
        LEFT JOIN games g ON g.app_id = theirs.app_id
        GROUP BY u.id, u.username, r.status, r.outgoing
        ORDER BY u.username`,
        [req.userId],
    );
    res.json({ friends: result.rows });
}));

app.use((error, req, res, next) => {
    if (res.headersSent) return next(error);
    if (error instanceof HttpError) {
        return res.status(error.status).json({ error: error.message });
    }
    if (error.response) {
        const status = error.response.status || 502;
        const message = error.response.data?.detail || 'Prediction service is unavailable';
        return res.status(status).json({ error: message });
    }
    console.error('Request failed:', error);
    return res.status(500).json({ error: 'The request could not be completed' });
});

app.listen(PORT, () => {
    console.log(`Backend server running on port ${PORT}`);
});
