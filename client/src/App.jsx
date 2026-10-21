import { useState } from 'react';
import axios from 'axios';

const GAME_ID = 730;

function App() {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchInsights = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await axios.get(`http://localhost:5000/api/games/${GAME_ID}/insights`);
      setInsights(response.data);
    } catch (requestError) {
      setError(
        requestError.response?.data?.error ||
        'Could not reach the prediction service. Start the backend with docker-compose up.',
      );
    } finally {
      setLoading(false);
    }
  };

  const probability = insights?.predictions?.sale_probability;
  const percent = typeof probability === 'number' ? probability * 100 : null;

  return (
    <main className="page-shell">
      <header className="topbar">
        <a className="wordmark" href="#top" aria-label="Discount Genie home">
          <span className="wordmark-mark">DG</span>
          <span>Discount Genie</span>
        </a>
        <span className="topbar-note">STEAM SALE FORECAST / DEMO</span>
      </header>

      <section className="forecast" id="top" aria-labelledby="game-title">
        <div className="game-art-wrap">
          <img
            className="game-art"
            src="https://cdn.cloudflare.steamstatic.com/steam/apps/730/header.jpg"
            alt="Counter-Strike 2 artwork"
          />
          <span className="art-tag">APP ID 730</span>
        </div>

        <div className="forecast-copy">
          <p className="eyebrow"><span className="live-dot" /> GAME ON DECK</p>
          <h1 id="game-title">Counter-Strike 2</h1>
          <p className="game-meta">Valve <span>/</span> Developer &amp; publisher</p>
          <p className="intro-copy">
            Pull the latest game snapshot and run it through the demo forecasting pipeline.
          </p>

          <button className="predict-button" onClick={fetchInsights} disabled={loading}>
            <span>{loading ? 'Grabbing Counter-Strike 2 data...' : 'Grab Counter-Strike 2 data'}</span>
            <span className="button-arrow" aria-hidden="true">↗</span>
          </button>
          {error && <p className="error-message" role="alert">{error}</p>}
          <p className="demo-note">Demo game and article inputs; model scores are placeholders.</p>
        </div>
      </section>

      <section className="results" aria-live="polite" aria-labelledby="results-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">FORECAST OUTPUT</p>
            <h2 id="results-heading">Sale outlook</h2>
          </div>
          {insights && (
            <span className="save-state">
              {insights.cached ? 'MOST RECENT SAVED' : 'JUST CALCULATED'}
            </span>
          )}
        </div>

        <div className="outlook-grid">
          <div className="probability-block">
            <span className="metric-label">Chance of a sale</span>
            <div className="probability-value">
              <strong>{percent === null ? '--' : `${percent.toFixed(1)}%`}</strong>
              <span className="probability-caption">demo probability</span>
            </div>
            <div className="probability-track" aria-label={percent === null ? 'No prediction yet' : `${percent}% chance`}>
              <span style={{ width: `${percent ?? 0}%` }} />
            </div>
          </div>
          <div className="timing-block">
            <span className="metric-label">Predicted timing</span>
            <strong>{insights?.predictions?.predicted_sale_window || 'Run forecast to see timing'}</strong>
            {insights?.game && (
              <span className="price-caption">
                Demo price: ${Number(insights.game.current_price).toFixed(2)}
                {` / ${Number(insights.game.discount_percent).toFixed(0)}% off`}
              </span>
            )}
          </div>
        </div>
      </section>

      {insights?.models && (
        <section className="models" aria-labelledby="models-heading">
          <div className="section-heading model-heading">
            <div>
              <p className="eyebrow">UNDER THE HOOD</p>
              <h2 id="models-heading">Model handoff</h2>
            </div>
            <span className="model-note">Inputs and outputs are ready to replace</span>
          </div>
          <div className="model-grid">
            <article className="model-stage historical-stage">
              <span className="stage-index">01 / HISTORY</span>
              <h3>Historical sales</h3>
              <p>{insights.models.historical?.inputs?.history_observations ?? 0} stored price periods</p>
              <strong>{Math.round((insights.models.historical?.sale_probability ?? 0) * 100)}% likelihood</strong>
            </article>
            <article className="model-stage nlp-stage">
              <span className="stage-index">02 / NLP</span>
              <h3>News &amp; entities</h3>
              <p>{insights.models.nlp?.article_count ?? 0} placeholder articles · {insights.models.nlp?.inputs?.developer || 'Developer'} / {insights.models.nlp?.inputs?.publisher || 'Publisher'}</p>
              <strong>{Math.round((insights.models.nlp?.sentiment_score ?? 0.5) * 100)}% neutral sentiment</strong>
            </article>
            <article className="model-stage fusion-stage">
              <span className="stage-index">03 / FUSION</span>
              <h3>Final forecast</h3>
              <p>{Math.round((insights.models.fusion?.inputs?.historical_weight ?? 0) * 100)}% history · {Math.round((insights.models.fusion?.inputs?.news_weight ?? 0) * 100)}% news</p>
              <strong>{insights.models.fusion?.model || 'Waiting for model run'}</strong>
            </article>
          </div>
        </section>
      )}

      <footer className="page-footer">
        <span>DISCOUNT GENIE</span>
        <span>DEMO BUILD · NOT A LIVE FINANCIAL FORECAST</span>
      </footer>
    </main>
  );
}

export default App;