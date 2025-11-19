import React, { useState, useEffect } from 'react';
import './App.css';

const BACKEND_URL = "";

function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [userName, setUserName] = useState("");
  const [spotifyUrl, setSpotifyUrl] = useState("");
  const [customWords, setCustomWords] = useState("");
  const [selectedLists, setSelectedLists] = useState(["en"]);
  const [defaultWordLists, setDefaultWordLists] = useState({});
  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState({ percent: 0, current_track: "" });
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");
  const [showWordLists, setShowWordLists] = useState(false);

  useEffect(() => {
    checkLoginStatus();
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('logged_in') === 'true') {
      window.history.replaceState({}, document.title, "/");
      checkLoginStatus();
    }
  }, []);

  const checkLoginStatus = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/me`, { credentials: 'include' });
      const data = await response.json();
      if (data.logged_in) {
        setLoggedIn(true);
        setUserName(data.name);
        setDefaultWordLists(data.default_word_lists || {});
      }
    } catch (err) {
      console.error("Login check failed:", err);
    }
  };

  const handleLogin = () => {
    window.location.href = `${BACKEND_URL}/login`;
  };

  const handleLogout = async () => {
    await fetch(`${BACKEND_URL}/logout`, { credentials: 'include' });
    setLoggedIn(false);
    setUserName("");
    setResults(null);
  };

  const toggleList = (langCode) => {
    setSelectedLists(prev =>
      prev.includes(langCode)
        ? prev.filter(l => l !== langCode)
        : [...prev, langCode]
    );
  };

  const toggleAll = () => {
    if (selectedLists.length === Object.keys(defaultWordLists).length) {
      setSelectedLists([]);
    } else {
      setSelectedLists(Object.keys(defaultWordLists));
    }
  };

  const handleAnalyze = async () => {
    setError("");
    setResults(null);

    if (!spotifyUrl.trim()) {
      setError("Please enter a Spotify URL");
      return;
    }

    if (!customWords.trim() && selectedLists.length === 0) {
      setError("Please select at least one word list or provide custom words");
      return;
    }

    setAnalyzing(true);
    setProgress({ percent: 0, current_track: "Starting analysis..." });

    const progressInterval = setInterval(async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/progress`, { credentials: 'include' });
        const data = await response.json();
        setProgress(data);
      } catch (err) {
        console.error("Progress check failed:", err);
      }
    }, 500);

    try {
      const response = await fetch(`${BACKEND_URL}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          url: spotifyUrl,
          custom_words: customWords,
          selected_defaults: selectedLists
        })
      });

      const data = await response.json();

      if (response.ok) {
        setResults(data);
      } else {
        setError(data.error || "Analysis failed");
      }
    } catch (err) {
      setError("Network error. Please try again.");
    } finally {
      clearInterval(progressInterval);
      setAnalyzing(false);
      setProgress({ percent: 0, current_track: "" });
    }
  };

  const getLanguageName = (code) => {
    const names = {
      'ar': 'Arabic', 'zh': 'Chinese', 'cs': 'Czech', 'da': 'Danish',
      'nl': 'Dutch', 'en': 'English', 'eo': 'Esperanto', 'fil': 'Filipino',
      'fi': 'Finnish', 'fr': 'French', 'fr-CA-u-sd-caqc': 'French (Quebec)',
      'de': 'German', 'hi': 'Hindi', 'hu': 'Hungarian', 'it': 'Italian',
      'ja': 'Japanese', 'kab': 'Kabyle', 'tlh': 'Klingon', 'ko': 'Korean',
      'no': 'Norwegian', 'fa': 'Persian', 'pl': 'Polish', 'pt': 'Portuguese',
      'ru': 'Russian', 'es': 'Spanish', 'sv': 'Swedish', 'th': 'Thai', 'tr': 'Turkish'
    };
    return names[code] || code;
  };

  if (!loggedIn) {
    return (
      <div className="app">
        <div className="login-container">
          <div className="login-card">
            <div className="logo-section">
              <h1 className="app-title">FCC Song Checker</h1>
              <p className="app-subtitle">Analyze Spotify tracks for explicit content</p>
            </div>
            <button className="btn-spotify" onClick={handleLogin}>
              <svg viewBox="0 0 24 24" fill="currentColor" width="24" height="24">
                <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/>
              </svg>
              Login with Spotify
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <h1 className="app-logo">FCC Song Checker</h1>
          <div className="user-section">
            <span className="user-name">Hi, {userName}</span>
            <button className="btn-logout" onClick={handleLogout}>Logout</button>
          </div>
        </div>
      </header>

      <main className="main-content">
        <div className="container">
          <section className="input-section">
            <h2 className="section-title">Analyze a Track, Album, or Playlist</h2>

            <div className="input-group">
              <label className="input-label">Spotify URL</label>
              <input
                type="text"
                className="input-field"
                placeholder="Paste Spotify URL here..."
                value={spotifyUrl}
                onChange={(e) => setSpotifyUrl(e.target.value)}
                disabled={analyzing}
              />
            </div>

            <div className="word-lists-section">
              <div className="section-header">
                <label className="input-label">Flagged Words</label>
                <button
                  className="btn-toggle-lists"
                  onClick={() => setShowWordLists(!showWordLists)}
                >
                  {showWordLists ? 'Hide' : 'Show'} Word Lists
                  <svg
                    className={`chevron ${showWordLists ? 'up' : 'down'}`}
                    width="16"
                    height="16"
                    viewBox="0 0 16 16"
                    fill="currentColor"
                  >
                    <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="2" fill="none"/>
                  </svg>
                </button>
              </div>

              {showWordLists && (
                <div className="word-lists-grid">
                  <div className="lists-header">
                    <span className="lists-count">
                      {selectedLists.length} of {Object.keys(defaultWordLists).length} selected
                    </span>
                    <button className="btn-toggle-all" onClick={toggleAll}>
                      {selectedLists.length === Object.keys(defaultWordLists).length ? 'Deselect All' : 'Select All'}
                    </button>
                  </div>
                  <div className="checkbox-grid">
                    {Object.keys(defaultWordLists).sort((a, b) =>
                      getLanguageName(a).localeCompare(getLanguageName(b))
                    ).map(langCode => (
                      <label key={langCode} className="checkbox-label">
                        <input
                          type="checkbox"
                          className="checkbox-input"
                          checked={selectedLists.includes(langCode)}
                          onChange={() => toggleList(langCode)}
                        />
                        <span className="checkbox-custom"></span>
                        <span className="checkbox-text">
                          {getLanguageName(langCode)}
                          <span className="word-count">({defaultWordLists[langCode]?.length || 0})</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <div className="input-group">
                <label className="input-label">Custom Words (optional)</label>
                <textarea
                  className="input-field textarea"
                  placeholder="Enter custom words separated by commas..."
                  value={customWords}
                  onChange={(e) => setCustomWords(e.target.value)}
                  disabled={analyzing}
                  rows="3"
                />
              </div>
            </div>

            {error && (
              <div className="error-message">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M10 0C4.48 0 0 4.48 0 10s4.48 10 10 10 10-4.48 10-10S15.52 0 10 0zm1 15H9v-2h2v2zm0-4H9V5h2v6z"/>
                </svg>
                {error}
              </div>
            )}

            <button
              className="btn-analyze"
              onClick={handleAnalyze}
              disabled={analyzing}
            >
              {analyzing ? (
                <>
                  <div className="spinner"></div>
                  Analyzing...
                </>
              ) : (
                <>
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                    <path d="M8 0L10 6L16 8L10 10L8 16L6 10L0 8L6 6L8 0Z"/>
                  </svg>
                  Analyze
                </>
              )}
            </button>
          </section>

          {analyzing && (
            <section className="progress-section">
              <div className="progress-container">
                <div className="progress-info">
                  <span className="progress-text">{progress.current_track || "Processing..."}</span>
                  <span className="progress-percent">{progress.percent}%</span>
                </div>
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${progress.percent}%` }}
                  ></div>
                </div>
              </div>
            </section>
          )}

          {results && (
            <section className="results-section">
              <div className="results-header">
                <div>
                  <h2 className="results-title">{results.name}</h2>
                  <p className="results-subtitle">
                    {results.artist || results.owner} • {results.type}
                  </p>
                </div>
                {results.album_cover && (
                  <img src={results.album_cover} alt="Album cover" className="album-cover" />
                )}
              </div>

              <div className="results-summary">
                <div className="summary-stat">
                  <span className="stat-value">{results.tracks?.length || 0}</span>
                  <span className="stat-label">Total Tracks</span>
                </div>
                <div className="summary-stat">
                  <span className="stat-value">
                    {results.tracks?.filter(t => t.status === "Explicit").length || 0}
                  </span>
                  <span className="stat-label">Explicit</span>
                </div>
                <div className="summary-stat">
                  <span className="stat-value">
                    {results.tracks?.filter(t => t.status === "Clean").length || 0}
                  </span>
                  <span className="stat-label">Clean</span>
                </div>
              </div>

              <div className="tracks-list">
                {results.tracks?.map((track, index) => (
                  <div key={index} className={`track-item ${track.status.toLowerCase().replace(' ', '-')}`}>
                    <div className="track-number">{track.track_number}</div>
                    <div className="track-info">
                      <div className="track-name">{track.track_name}</div>
                      {track.flagged_words && track.flagged_words.length > 0 && (
                        <div className="flagged-words">
                          {Array.isArray(track.flagged_words[0])
                            ? track.flagged_words.map((fw, i) => (
                                <span key={i} className="flagged-word">
                                  {typeof fw === 'object' ? fw.context : fw}
                                  {typeof fw === 'object' && fw.timestamp && (
                                    <span className="timestamp">
                                      {Math.floor(fw.timestamp / 60)}:{String(Math.floor(fw.timestamp % 60)).padStart(2, '0')}
                                    </span>
                                  )}
                                </span>
                              ))
                            : track.flagged_words.map((word, i) => (
                                <span key={i} className="flagged-word">
                                  {typeof word === 'object' ? word.context : word}
                                  {typeof word === 'object' && word.timestamp && (
                                    <span className="timestamp">
                                      {Math.floor(word.timestamp / 60)}:{String(Math.floor(word.timestamp % 60)).padStart(2, '0')}
                                    </span>
                                  )}
                                </span>
                              ))
                          }
                        </div>
                      )}
                    </div>
                    <div className={`track-status status-${track.status.toLowerCase().replace(' ', '-')}`}>
                      {track.status}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
