import React, { useState } from 'react';
import axios from 'axios';

function App() {
  const [gameInsights, setGameInsights] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Test function to verify the full frontend -> backend -> AI service pipeline
  const fetchInsights = async (appId) => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get(`http://localhost:5000/api/games/${appId}/insights`);
      setGameInsights(response.data);
    } catch (err) {
      console.error("Error fetching data:", err);
      setError("Failed to fetch AI insights. Make sure Docker containers are running (docker-compose up).");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ fontFamily: 'Arial, sans-serif', maxWidth: '800px', margin: '40px auto', padding: '20px' }}>
      <header style={{ textAlign: 'center', marginBottom: '30px' }}>
        <h1 style={{ color: '#1b2838' }}>Steam Sale Predictor</h1>
        <p style={{ color: '#66c0f4' }}>AI-Powered Sale & Discount Forecasting Dashboard</p>
      </header>

      <div style={{ background: '#f8f9fa', padding: '20px', borderRadius: '8px', border: '1px solid #dee2e6' }}>
        <h2>Pipeline Connection Test</h2>
        <p>Click below to test data flow from React $\rightarrow$ Express Backend $\rightarrow$ Python AI Microservice:</p>
        
        <button 
          onClick={() => fetchInsights(730)} // Example: App ID 730
          style={{
            background: '#2a475e',
            color: 'white',
            border: 'none',
            padding: '10px 20px',
            borderRadius: '4px',
            cursor: 'pointer',
            fontWeight: 'bold',
            marginTop: '10px'
          }}
        >
          Test AI Prediction (App ID: 730)
        </button>

        {loading && <p style={{ marginTop: '15px', color: '#555' }}>Querying AI models...</p>}
        {error && <p style={{ color: '#d9534f', marginTop: '15px' }}>{error}</p>}

        {gameInsights && (
          <div style={{ marginTop: '20px', background: 'white', padding: '15px', borderRadius: '6px', border: '1px solid #ccc' }}>
            <h3>Prediction Results for App ID: {gameInsights.appId}</h3>
            <p><strong>Sale Probability:</strong> {(gameInsights.predictions.sale_probability * 100).toFixed(1)}%</p>
            <p><strong>Predicted Window:</strong> {gameInsights.predictions.predicted_window}</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;