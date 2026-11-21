import { createContext, useContext, useEffect, useState } from 'react';
import axios from 'axios';
import {
  BrowserRouter,
  Link,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';

const api = axios.create({ baseURL: 'http://localhost:5000/api' });
const AuthContext = createContext(null);

function authConfig(token) {
  return { headers: { Authorization: `Bearer ${token}` } };
}

function errorText(error) {
  return error.response?.data?.error || 'The local service could not complete this request.';
}

function App() {
  const [token, setToken] = useState(() => localStorage.getItem('discount-genie-token') || '');
  const [user, setUser] = useState(null);
  const [authError, setAuthError] = useState('');

  useEffect(() => {
    setAuthError('');
    if (!token) {
      setUser(null);
      return;
    }
    api.get('/auth/me', authConfig(token))
      .then(({ data }) => setUser(data))
      .catch((error) => {
        if (error.response?.status === 401) {
          localStorage.removeItem('discount-genie-token');
          setToken('');
        } else {
          setAuthError(errorText(error));
        }
      });
  }, [token]);

  const signIn = ({ token: nextToken, user: nextUser }) => {
    localStorage.setItem('discount-genie-token', nextToken);
    setToken(nextToken);
    setUser(nextUser);
    setAuthError('');
  };
  const signOut = () => {
    localStorage.removeItem('discount-genie-token');
    setToken('');
    setUser(null);
    setAuthError('');
  };

  return (
    <AuthContext.Provider value={{ token, user, authError, signIn, signOut }}>
      <BrowserRouter>
        <Site />
      </BrowserRouter>
    </AuthContext.Provider>
  );
}

function Site() {
  const location = useLocation();
  const { token, user, authError, signOut } = useContext(AuthContext);
  const [query, setQuery] = useState('');
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    setQuery('');
    setAccountMenuOpen(false);
  }, [location.pathname, location.search, location.hash]);

  const submitSearch = async (event) => {
    event.preventDefault();
    const search = query.trim();
    if (!search) return;
    if (/^\d+$/.test(search)) {
      navigate(`/game/${search}`);
      return;
    }
    try {
      const { data } = await api.get('/games/search', { params: { q: search } });
      const exact = data.games.find(
        (game) => game.name.toLocaleLowerCase() === search.toLocaleLowerCase(),
      );
      if (exact) {
        navigate(`/game/${exact.app_id}`);
        return;
      }
    } catch {
      // The results page displays service errors if the local API is unavailable.
    }
    navigate(`/search?q=${encodeURIComponent(search)}`);
  };

  return (
    <main className="page-shell">
      <header className="topbar">
        <Link className="wordmark" to="/" aria-label="Discount Genie home">
          <span className="wordmark-mark">DG</span>
          <span>Discount Genie</span>
        </Link>
        <form className="top-search" onSubmit={submitSearch} role="search">
          <input
            aria-label="Search Steam games"
            placeholder="Search Steam games"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit" aria-label="Submit search">Search</button>
        </form>
        <div className="account-control">
          <button
            className="user-button"
            type="button"
            aria-label={user ? `Account menu for ${user.username}` : 'Open account'}
            aria-expanded={accountMenuOpen}
            onClick={() => {
              if (!user) navigate('/auth');
              else setAccountMenuOpen((open) => !open);
            }}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="8" r="3.2" />
              <path d="M5.5 20c.4-3.5 2.8-5.3 6.5-5.3s6.1 1.8 6.5 5.3" />
            </svg>
          </button>
          {accountMenuOpen && user && (
            <nav className="account-menu" aria-label="Account navigation">
              <strong>{user.username}</strong>
              <Link to="/account">Account &amp; friends</Link>
              <Link to="/account#watchlist">Watchlist</Link>
              <button type="button" onClick={signOut}>Log out</button>
            </nav>
          )}
        </div>
      </header>
      {authError && <p className="error-message" role="alert">{authError}</p>}

      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/game/:appId" element={<GamePage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      <footer className="page-footer">
        <span>DISCOUNT GENIE</span>
        <span>STEAM SALE FORECAST / LOCAL DEMO</span>
      </footer>
    </main>
  );
}

function GameGrid({ games, emptyMessage }) {
  if (!games.length) return <p className="empty-state">{emptyMessage}</p>;
  return (
    <div className="game-grid">
      {games.map((game) => (
        <Link className="game-card" key={game.app_id} to={`/game/${game.app_id}`}>
          <img
            src={game.header_image || `https://cdn.cloudflare.steamstatic.com/steam/apps/${game.app_id}/header.jpg`}
            alt=""
            loading="lazy"
          />
          <div className="game-card-copy">
            <h3>{game.name}</h3>
            <span className="card-probability">
              {typeof game.sale_probability === 'number'
                ? `${Math.round(game.sale_probability * 100)}% chance`
                : game.publisher || 'Steam game'}
            </span>
            {game.predicted_sale_window && (
              <span className="card-window">{game.predicted_sale_window}</span>
            )}
          </div>
          <span className="card-arrow" aria-hidden="true">↗</span>
        </Link>
      ))}
    </div>
  );
}

function HomePage() {
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/games/ranked')
      .then(({ data }) => setGames(data.games || []))
      .catch((requestError) => setError(errorText(requestError)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="content-page">
      <p className="eyebrow">STEAM PRICE OUTLOOK</p>
      <div className="page-title-row">
        <div>
          <h1>Games to watch</h1>
          <p className="page-intro">The strongest sale signals from games in the local catalog.</p>
        </div>
        <span className="save-state">RANKED BY SALE CHANCE</span>
      </div>
      {loading && <p className="status-message">Loading the local ranking…</p>}
      {error && <p className="error-message" role="alert">{error}</p>}
      {!loading && !error && (
        <GameGrid games={games} emptyMessage="No Steam games are in the local catalog yet." />
      )}
    </section>
  );
}

function GamePage() {
  const { appId } = useParams();
  const { token, user } = useContext(AuthContext);
  const [insights, setInsights] = useState(null);
  const [watchlisted, setWatchlisted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setInsights(null);
    setError('');
    setLoading(true);
    api.get(`/games/${appId}/insights`)
      .then(({ data }) => setInsights(data))
      .catch((requestError) => setError(errorText(requestError)))
      .finally(() => setLoading(false));
  }, [appId]);

  useEffect(() => {
    if (!token) {
      setWatchlisted(false);
      return;
    }
    api.get('/watchlist', authConfig(token))
      .then(({ data }) => setWatchlisted(data.games.some((game) => String(game.app_id) === appId)))
      .catch((requestError) => setError(errorText(requestError)));
  }, [appId, token]);

  const toggleWatchlist = async () => {
    if (!token) return;
    setSaving(true);
    try {
      if (watchlisted) await api.delete(`/watchlist/${appId}`, authConfig(token));
      else await api.post('/watchlist', { appId: Number(appId) }, authConfig(token));
      setWatchlisted(!watchlisted);
    } catch (requestError) {
      setError(errorText(requestError));
    } finally {
      setSaving(false);
    }
  };

  const game = insights?.game;
  const prediction = insights?.predictions;
  const models = insights?.models;
  const probability = prediction?.sale_probability;
  const article = models?.nlp;
  const weights = insights?.effectiveWeights || models?.fusion?.effective_weights;

  if (loading) return <section className="content-page"><p className="status-message">Loading Steam forecast…</p></section>;
  if (error && !insights) return <section className="content-page"><p className="error-message" role="alert">{error}</p></section>;
  if (!game) return null;

  return (
    <section className="content-page game-page">
      <section className="game-hero">
        <img
          className="hero-art"
          src={`https://cdn.cloudflare.steamstatic.com/steam/apps/${appId}/header.jpg`}
          alt={`${game.name} header artwork`}
        />
        <div className="hero-copy">
          <p className="eyebrow"><span className="live-dot" /> STEAM GAME / APP {appId}</p>
          <h1>{game.name}</h1>
          <p className="game-meta">{game.developer || 'Developer unavailable'} <span>/</span> {game.publisher || 'Publisher unavailable'}</p>
          <p className="intro-copy">
            {game.current_price == null
              ? 'Current price unavailable'
              : `Current price $${Number(game.current_price).toFixed(2)} · ${Number(game.discount_percent || 0).toFixed(0)}% off`}
          </p>
          {user && (
            <button className="action-button" type="button" disabled={saving} onClick={toggleWatchlist}>
              {saving ? 'Saving…' : watchlisted ? 'Remove from watchlist' : 'Add to watchlist'}
            </button>
          )}
          {!user && <Link className="text-link" to="/auth">Sign in to save this game</Link>}
        </div>
      </section>

      <section className="results">
        <div className="section-heading">
          <div><p className="eyebrow">SALE OUTLOOK</p><h2>Prediction</h2></div>
          {insights.cached && <span className="save-state">SAVED FORECAST</span>}
        </div>
        <div className="outlook-grid">
          <div className="probability-block">
            <span className="metric-label">Chance of a sale within 30 days</span>
            <div className="probability-value">
              <strong>{typeof probability === 'number' ? `${(probability * 100).toFixed(1)}%` : '--'}</strong>
              <span className="probability-caption">synthesis model</span>
            </div>
            <div className="probability-track"><span style={{ width: `${(probability || 0) * 100}%` }} /></div>
          </div>
          <div className="timing-block">
            <span className="metric-label">Likely timing</span>
            <strong>{prediction.predicted_sale_window}</strong>
            <span className="price-caption">
              {prediction.expected_discount_percent == null
                ? 'Discount depth unavailable: no sale history'
                : `Typical past discount: ${prediction.expected_discount_percent}%`}
            </span>
          </div>
        </div>
      </section>

      {models && (
        <section className="models">
          <div className="section-heading">
            <div><p className="eyebrow">UNDER THE HOOD</p><h2>How it was made</h2></div>
            {insights.demo && <span className="model-note">Some trained model files are missing</span>}
          </div>
          <div className="model-grid">
            <article className="model-stage">
              <span className="stage-index">01 / HISTORY</span>
              <h3>Historical model</h3>
              <p>{models.historical?.inputs?.history_observations ?? 0} daily price observations</p>
              <strong>{Math.round((models.historical?.sale_probability || 0) * 100)}% likelihood</strong>
            </article>
            <article className="model-stage">
              <span className="stage-index">02 / ARTICLES</span>
              <h3>Steam article model</h3>
              {!article?.applicable ? (
                <>
                  <p>No articles matched this game or publisher.</p>
                  <strong>No articles, article model not used</strong>
                </>
              ) : (
                <>
                  <p>{article.article_count} matched articles · sentiment {Math.round(article.sentiment_score * 100)}%</p>
                  <strong>{Math.round(article.sale_probability * 100)}% article probability</strong>
                  <ul className="phrase-list">
                    {article.matched_phrases.map((item) => (
                      <li key={item.phrase}>{item.phrase} <span>{item.weight > 0 ? '+' : ''}{item.weight}</span></li>
                    ))}
                    {!article.matched_phrases.length && <li>No sale-related phrases found.</li>}
                  </ul>
                </>
              )}
            </article>
            <article className="model-stage">
              <span className="stage-index">03 / SYNTHESIS</span>
              <h3>Combined forecast</h3>
              <p>Historical share {Math.round((weights?.historical || 0) * 100)}% · article share {Math.round((weights?.article || 0) * 100)}%</p>
              <strong>{Math.round((models.fusion?.sale_probability || 0) * 100)}% final likelihood</strong>
            </article>
          </div>
        </section>
      )}
      {error && <p className="error-message" role="alert">{error}</p>}
    </section>
  );
}

function SearchPage() {
  const [params] = useSearchParams();
  const query = params.get('q') || '';
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    api.get('/games/search', { params: { q: query } })
      .then(({ data }) => setGames(data.games || []))
      .catch((requestError) => setError(errorText(requestError)))
      .finally(() => setLoading(false));
  }, [query]);

  return (
    <section className="content-page">
      <p className="eyebrow">STEAM CATALOG</p>
      <h1>Search results</h1>
      <p className="page-intro">Matches for “{query}”</p>
      {loading && <p className="status-message">Searching the local Steam catalog…</p>}
      {error && <p className="error-message" role="alert">{error}</p>}
      {!loading && !error && (
        <GameGrid games={games} emptyMessage="No matching Steam games were found in the local catalog." />
      )}
    </section>
  );
}

function AuthPage() {
  const { signIn } = useContext(AuthContext);
  const navigate = useNavigate();
  const [registering, setRegistering] = useState(false);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const endpoint = registering ? '/auth/register' : '/auth/login';
      const payload = registering ? { username, email, password } : { email, password };
      const { data } = await api.post(endpoint, payload);
      signIn(data);
      navigate('/account');
    } catch (requestError) {
      setError(errorText(requestError));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="content-page auth-page">
      <p className="eyebrow">YOUR ACCOUNT</p>
      <h1>{registering ? 'Create account' : 'Welcome back'}</h1>
      <form className="form-panel" onSubmit={submit}>
        {registering && (
          <label>Username<input value={username} onChange={(event) => setUsername(event.target.value)} required minLength="3" maxLength="50" /></label>
        )}
        <label>Email<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
        <label>Password<input type="password" autoComplete={registering ? 'new-password' : 'current-password'} value={password} onChange={(event) => setPassword(event.target.value)} required minLength="8" maxLength="72" /></label>
        {error && <p className="error-message" role="alert">{error}</p>}
        <button className="action-button" type="submit" disabled={loading}>{loading ? 'Working…' : registering ? 'Register' : 'Log in'}</button>
      </form>
      <button className="plain-button" type="button" onClick={() => { setRegistering(!registering); setError(''); }}>
        {registering ? 'Already have an account? Log in' : 'New here? Create an account'}
      </button>
    </section>
  );
}

function AccountPage() {
  const { token, user } = useContext(AuthContext);
  const [account, setAccount] = useState(null);
  const [games, setGames] = useState([]);
  const [friends, setFriends] = useState([]);
  const [friendName, setFriendName] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    const config = authConfig(token);
    const [accountResponse, watchlistResponse, friendsResponse] = await Promise.all([
      api.get('/auth/me', config),
      api.get('/watchlist', config),
      api.get('/friends', config),
    ]);
    setAccount(accountResponse.data);
    setGames(watchlistResponse.data.games || []);
    setFriends(friendsResponse.data.friends || []);
  };

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    refresh()
      .catch((requestError) => setError(errorText(requestError)))
      .finally(() => setLoading(false));
  }, [token]);

  const requestFriend = async (event) => {
    event.preventDefault();
    setError('');
    setNotice('');
    try {
      await api.post('/friends/requests', { username: friendName }, authConfig(token));
      setFriendName('');
      setNotice('Friend request sent.');
      await refresh();
    } catch (requestError) {
      setError(errorText(requestError));
    }
  };

  const acceptRequest = async (friendId) => {
    try {
      await api.post(`/friends/${friendId}/accept`, {}, authConfig(token));
      await refresh();
    } catch (requestError) {
      setError(errorText(requestError));
    }
  };

  if (!token) {
    return (
      <section className="content-page">
        <p className="eyebrow">YOUR ACCOUNT</p>
        <h1>Sign in to your account</h1>
        <Link className="action-button inline-action" to="/auth">Log in or register</Link>
      </section>
    );
  }
  if (loading) return <section className="content-page"><p className="status-message">Loading account…</p></section>;

  return (
    <section className="content-page account-page">
      <p className="eyebrow">YOUR ACCOUNT</p>
      <h1>{account?.username || user?.username}</h1>
      <p className="page-intro">{account?.email || user?.email} · {account?.watchlist_count || 0} saved games · {account?.friend_count || 0} friends</p>
      {error && <p className="error-message" role="alert">{error}</p>}
      {notice && <p className="status-message" role="status">{notice}</p>}

      <section className="account-section" id="watchlist">
        <div className="section-heading"><div><p className="eyebrow">SAVED GAMES</p><h2>Watchlist</h2></div></div>
        <GameGrid games={games} emptyMessage="Your watchlist is empty." />
      </section>

      <section className="account-section" id="friends">
        <div className="section-heading"><div><p className="eyebrow">COMPARISON</p><h2>Friends</h2></div></div>
        <form className="friend-form" onSubmit={requestFriend}>
          <label htmlFor="friend-username">Send a request by username</label>
          <div><input id="friend-username" value={friendName} onChange={(event) => setFriendName(event.target.value)} required /><button className="action-button" type="submit">Send request</button></div>
        </form>
        {friends.length === 0 && <p className="empty-state">No friends or pending requests yet.</p>}
        <div className="friend-list">
          {friends.map((friend) => (
            <article className="friend-row" key={`${friend.id}-${friend.status}`}>
              <div>
                <h3>{friend.username}</h3>
                <span className="price-caption">
                  {friend.status === 'accepted'
                    ? `${friend.shared_games.length} shared watchlist ${friend.shared_games.length === 1 ? 'game' : 'games'}`
                    : friend.outgoing ? 'Request sent' : 'Incoming request'}
                </span>
                {friend.status === 'accepted' && friend.shared_games.length > 0 && (
                  <p className="shared-games">
                    {friend.shared_games.map((game) => (
                      <Link key={game.app_id} to={`/game/${game.app_id}`}>{game.name}</Link>
                    ))}
                  </p>
                )}
              </div>
              {friend.status === 'pending' && !friend.outgoing && (
                <button className="plain-button" type="button" onClick={() => acceptRequest(friend.id)}>Accept</button>
              )}
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}

function NotFound() {
  return (
    <section className="content-page">
      <p className="eyebrow">NOT FOUND</p>
      <h1>That page is not here.</h1>
      <Link className="text-link" to="/">Return home</Link>
    </section>
  );
}

export default App;
