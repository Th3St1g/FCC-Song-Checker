from flask import Flask, request, jsonify, session, redirect, send_from_directory
from flask_cors import CORS
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import json
import re
from datetime import datetime
from lyricsgenius import Genius
from dotenv import load_dotenv
import time
import webbrowser
import requests

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder="build", static_url_path="/")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "defaultsecret")

CORS(app, supports_credentials=True)

app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True

# --- Spotify OAuth setup ---
sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    scope="user-read-private"
)

# --- Genius API setup ---
GENIUS_ACCESS_TOKEN = os.getenv("GENIUS_API_TOKEN")
genius = Genius(
    GENIUS_ACCESS_TOKEN,
    skip_non_songs=True,
    excluded_terms=["(Live)"],
    remove_section_headers=True
)

# --- Load FCC flagged words ---
FCC_WORDS_FILE = "fcc_words.txt"
if not os.path.exists(FCC_WORDS_FILE):
    raise FileNotFoundError("⚠️ fcc_words.txt not found!")

with open(FCC_WORDS_FILE, "r", encoding="utf-8") as f:
    FCC_FLAGGED_WORDS = [line.strip().lower() for line in f if line.strip()]

if not FCC_FLAGGED_WORDS:
    raise ValueError("⚠️ fcc_words.txt is empty!")

print(f"✅ Loaded {len(FCC_FLAGGED_WORDS)} FCC flagged words.")

# Store progress per session
progress_store = {}

# --- Helper Functions ---

def parse_spotify_url(url):
    match = re.search(r"open\.spotify\.com/(track|album|playlist)/([a-zA-Z0-9]+)", url)
    return match.groups() if match else (None, None)

def refresh_token_if_needed():
    token_info = session.get("token_info")
    if not token_info: return None
    if datetime.now().timestamp() >= token_info.get("expires_at", 0):
        try:
            token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
            session["token_info"] = token_info
        except Exception as e:
            print(f"Error refreshing token: {e}")
            session.clear()
            return None
    return token_info

def clean_track_title(title):
    title = re.sub(r"\(feat[^\)]*\)", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\(Remix\)", "Remix", title, flags=re.IGNORECASE)
    title = re.sub(r"\(Live\)", "", title, flags=re.IGNORECASE)
    title = re.sub(r"- From .*", "", title, flags=re.IGNORECASE)
    return title.strip()

def get_lyrics_from_lrclib(title, artist, album, duration):
    url = "https://lrclib.net/api/get"
    params = { "track_name": title, "artist_name": artist, "album_name": album, "duration": int(duration) }
    headers = {"User-Agent": "FCCSongChecker/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200: return None, None
        data = response.json()
        synced = data.get("syncedLyrics")
        if not synced: return None, None
        lines = [(int(m) * 60 + float(s), txt.strip()) for m, s, txt in re.findall(r"\[(\d+):(\d+\.\d+)\]\s*(.*)", synced)]
        lrclib_url = f"https://lrclib.net/track/{data.get('id')}" if data.get('id') else None
        return lines, lrclib_url
    except Exception as e:
        print(f"⚠️ LRCLIB fetch error for '{title}': {e}")
        return None, None

def get_lyrics_from_genius(title, artist):
    try:
        song = genius.search_song(title, artist)
        return (song.lyrics.lower(), song.url) if song and song.lyrics else (None, None)
    except Exception:
        return None, None

def analyze_track_lyrics(track_obj, track_number, flagged_words):
    """Analyzes a single track object for a given list of flagged words."""
    if not track_obj:
        return {"track_number": track_number, "track_name": "Track not available", "status": "Error", "flagged_words": [], "genius_url": None, "lrclib_url": None}

    title_clean = clean_track_title(track_obj["name"])
    main_artist = track_obj["artists"][0]["name"] if track_obj.get("artists") else "Unknown"
    album_name = track_obj.get("album", {}).get("name", "")
    duration = track_obj.get("duration_ms", 0) / 1000

    lrclib_lines, lrclib_url = get_lyrics_from_lrclib(title_clean, main_artist, album_name, duration)
    if lrclib_lines:
        flagged_entries = []
        for time_sec, line_text in lrclib_lines:
            for word in flagged_words:
                if re.search(rf"\b{re.escape(word)}\b", line_text, re.IGNORECASE):
                    flagged_entries.append({"timestamp": round(time_sec, 3), "context": word})
        status = "Explicit" if flagged_entries else "Clean"
        return {"track_number": track_number, "track_name": track_obj["name"], "status": status, "flagged_words": flagged_entries, "genius_url": None, "lrclib_url": lrclib_url}

    lyrics, genius_url = get_lyrics_from_genius(title_clean, main_artist)
    if lyrics is None:
        return {"track_number": track_number, "track_name": track_obj["name"], "status": "Lyrics Not Found", "flagged_words": [], "genius_url": None, "lrclib_url": lrclib_url}

    found_words = [w for w in flagged_words if re.search(rf"\b{re.escape(w)}\b", lyrics, re.IGNORECASE)]
    status = "Explicit" if found_words else "Clean"
    return {"track_number": track_number, "track_name": track_obj["name"], "status": status, "flagged_words": found_words, "genius_url": genius_url, "lrclib_url": None}


# --- Flask Routes ---

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    build_path = os.path.join(app.root_path, "build")
    if os.path.exists(build_path) and path != "" and os.path.exists(os.path.join(build_path, path)):
        return send_from_directory(build_path, path)
    elif os.path.exists(os.path.join(build_path, "index.html")):
        return send_from_directory(build_path, "index.html")
    else:
        return "✅ FCC Song Checker Backend is running! React UI not found.", 200

@app.route("/login")
def login():
    return redirect(sp_oauth.get_authorize_url())

@app.route("/callback")
def callback():
    try:
        token_info = sp_oauth.get_access_token(request.args.get("code"), as_dict=True)
        session["token_info"] = token_info
        return redirect(f"{os.getenv('FRONTEND_URL', 'http://127.0.0.1:5000')}?logged_in=true")
    except Exception as e:
        return f"Error during Spotify login: {str(e)}", 500

@app.route("/logout")
def logout():
    session.clear()
    return jsonify({"logged_out": True})

@app.route("/me")
def me():
    token_info = refresh_token_if_needed()
    if not token_info: return jsonify({"logged_in": False}), 401
    sp = spotipy.Spotify(auth=token_info["access_token"])
    user_profile = sp.current_user()
    return jsonify({"logged_in": True, "id": user_profile.get("id"), "name": user_profile.get("display_name", "Unknown")})

# --- SEARCH ROUTE (Tracks and Albums Only, Improved Relevance) ---
@app.route("/search", methods=["POST"])
def search():
    token_info = refresh_token_if_needed()
    if not token_info: return jsonify({"error": "User not logged in."}), 401

    data = request.get_json()
    query = data.get("query")
    if not query: return jsonify({"error": "No query provided."}), 400

    sp = spotipy.Spotify(auth=token_info["access_token"])

    # Use the original query without wildcard for better relevance
    search_query = query

    try:
        # Changed type to exclude playlists and added market
        results = sp.search(q=search_query, type='track,album', limit=5, market='US')

        formatted_results = []

        # Format tracks
        if results.get('tracks'):
            for item in results['tracks']['items']:
                # Skip tracks with no artist (rare edge case)
                if not item.get('artists'): continue
                formatted_results.append({
                    "type": "Track",
                    "name": item['name'],
                    "artist": item['artists'][0]['name'],
                    "cover": item['album']['images'][-1]['url'] if item.get('album') and item['album']['images'] else None,
                    "url": item['external_urls']['spotify']
                })

        # Format albums
        if results.get('albums'):
            for item in results['albums']['items']:
                 # Skip albums with no artist (rare edge case)
                if not item.get('artists'): continue
                formatted_results.append({
                    "type": "Album",
                    "name": item['name'],
                    "artist": item['artists'][0]['name'],
                    "cover": item['images'][-1]['url'] if item.get('images') and item['images'] else None,
                    "url": item['external_urls']['spotify']
                })

        # Return max 10 total results (5 tracks + 5 albums)
        return jsonify(formatted_results[:10])

    except Exception as e:
        print(f"!!! SEARCH CRASH: {str(e)}")
        error_message = f"Spotify API error: {str(e)}"
        if hasattr(e, 'http_status'):
             error_message = f"Spotify API error ({e.http_status}): {e.msg}"
        return jsonify({"error": error_message}), 400


@app.route("/progress")
def progress():
    session_id = session.get("token_info", {}).get("access_token")
    if not session_id: return jsonify({"percent": 0, "current_track": ""})
    return jsonify(progress_store.get(session_id, {"percent": 0, "current_track": ""}))

@app.route("/analyze", methods=["POST"])
def analyze():
    token_info = refresh_token_if_needed()
    if not token_info: return jsonify({"error": "User not logged in. Please log in again."}), 401

    data = request.get_json()
    url = data.get("url")
    custom_words_str = data.get("custom_words", "")
    if not url: return jsonify({"error": "No URL provided."}), 400

    sp = spotipy.Spotify(auth=token_info["access_token"])
    session_id = token_info["access_token"]
    progress_store[session_id] = {"percent": 0, "current_track": ""}

    # Decide which word list to use
    if custom_words_str.strip():
        flagged_words_to_use = [line.strip().lower() for line in custom_words_str.splitlines() if line.strip()]
    else:
        flagged_words_to_use = FCC_FLAGGED_WORDS

    url_type, item_id = parse_spotify_url(url)
    if not url_type: return jsonify({"error": "Invalid or unsupported Spotify URL."}), 400

    tracks_to_process = []
    response_data = {"type": url_type}

    try:
        if url_type == 'track':
            track_info = sp.track(item_id)
            tracks_to_process = [track_info]
            response_data.update({"name": track_info["album"]["name"], "artist": track_info["artists"][0]["name"], "album_cover": track_info["album"]["images"][0]["url"] if track_info["album"]["images"] else None})
        elif url_type == 'album':
            album_info = sp.album(item_id)
            tracks_to_process = sp.album_tracks(item_id)["items"]
            response_data.update({"name": album_info["name"], "artist": album_info["artists"][0]["name"], "album_cover": album_info["images"][0]["url"] if album_info["images"] else None})
        elif url_type == 'playlist':
            playlist_info = sp.playlist(item_id)
            items = sp.playlist_items(item_id)["items"]
            next_page = sp.playlist_items(item_id).get("next")
            while next_page:
                page = sp.next(next_page)
                items.extend(page["items"])
                next_page = page.get("next")
            tracks_to_process = [item["track"] for item in items if item.get("track")]
            response_data.update({"name": playlist_info["name"], "owner": playlist_info["owner"]["display_name"], "cover": playlist_info["images"][0]["url"] if playlist_info["images"] else None})
    except Exception as e:
        return jsonify({"error": f"Spotify API error: {str(e)}"}), 500

    analysis_results = []
    total_tracks = len(tracks_to_process)
    for idx, track_obj in enumerate(tracks_to_process, start=1):
        progress_store[session_id] = {"percent": int((idx / total_tracks) * 100), "current_track": track_obj["name"] if track_obj else "Processing..."}
        result = analyze_track_lyrics(track_obj, idx, flagged_words_to_use)
        analysis_results.append(result)
        time.sleep(0.1)

    response_data["tracks"] = analysis_results
    progress_store[session_id] = {"percent": 100, "current_track": ""}
    return jsonify(response_data)