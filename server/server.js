const express = require('express');
const cors = require('cors');
const axios = require('axios');
const app = express();

app.use(express.json());
app.use(cors());

const PORT = process.env.PORT || 5000;
const AI_SERVICE_URL = process.env.AI_SERVICE_URL || 'http://localhost:8000';

// Example route: Get game insights by calling the Python AI service
app.get('/api/games/:appId/insights', async (req, res) => {
    try {
        const { appId } = req.params;
        
        // 1. Fetch game data & history from SQL Database here...
        // 2. Query Python AI Service for predictions
        const aiResponse = await axios.post(`${AI_SERVICE_URL}/predict`, {
            app_id: parseInt(appId),
            days_since_last_sale: 45,
            discount_history_avg: 0.50,
            news_sentiment_score: 0.82
        });

        res.json({
            appId,
            predictions: aiResponse.data
        });
    } catch (err) {
        console.error(err.message);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.listen(PORT, () => {
    console.log(`Backend server running on port ${PORT}`);
});