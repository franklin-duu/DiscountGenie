const express = require('express');
const cors = require('cors');
const axios = require('axios');
const app = express();

app.use(express.json());
app.use(cors());

const PORT = process.env.PORT || 5000;
const AI_SERVICE_URL = process.env.AI_SERVICE_URL || 'http://localhost:8000';

app.get('/api/games/:appId/insights', async (req, res) => {
    try {
        const { appId } = req.params;
        const numericAppId = Number(appId);
        if (!Number.isInteger(numericAppId) || numericAppId <= 0) {
            return res.status(400).json({ error: 'Invalid Steam app ID' });
        }

        const aiResponse = await axios.post(`${AI_SERVICE_URL}/predict`, {
            app_id: numericAppId
        });

        res.json({
            appId: aiResponse.data.app_id,
            game: aiResponse.data.game,
            predictions: aiResponse.data.prediction,
            models: aiResponse.data.models,
            cached: aiResponse.data.cached,
            demo: aiResponse.data.demo,
            updatedAt: aiResponse.data.updated_at
        });
    } catch (err) {
        const status = err.response?.status || 502;
        const message = err.response?.data?.detail || 'Prediction service is unavailable';
        res.status(status).json({ error: message });
    }
});

app.listen(PORT, () => {
    console.log(`Backend server running on port ${PORT}`);
});