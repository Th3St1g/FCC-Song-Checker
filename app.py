from flask import Flask, request, jsonify, session, redirect, send_from_directory
from flask_cors import CORS
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import json
import re
from datetime import datetime
from lyricsgenius import Genius # Make sure Genius is imported
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
if not GENIUS_ACCESS_TOKEN:
    print("⚠️ WARNING: GENIUS_API_TOKEN environment variable not set. Genius lookup will fail.", flush=True)
    genius = None # Set genius to None if key is missing
else:
    try:
        genius = Genius(
            GENIUS_ACCESS_TOKEN,
            skip_non_songs=True,
            excluded_terms=["(Live)"],
            remove_section_headers=True,
            verbose=False # Set verbose to False to reduce library's own console noise
        )
        print("✅ Genius client initialized.", flush=True)
    except Exception as e:
        print(f"❌ Error initializing Genius client: {e}", flush=True)
        genius = None # Set genius to None on initialization error

# --- Load multiple default word lists from subfolder ---
DEFAULT_WORD_LISTS = {}
WORD_LIST_FOLDER = "List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words"

DEFAULT_LIST_FILES = {
    'ar': os.path.join(WORD_LIST_FOLDER, 'default_ar.txt'),
    'zh': os.path.join(WORD_LIST_FOLDER, 'default_zh.txt'),
    'cs': os.path.join(WORD_LIST_FOLDER, 'default_cs.txt'),
    'da': os.path.join(WORD_LIST_FOLDER, 'default_da.txt'),
    'nl': os.path.join(WORD_LIST_FOLDER, 'default_nl.txt'),
    'en': os.path.join(WORD_LIST_FOLDER, 'default_en.txt'),
    'eo': os.path.join(WORD_LIST_FOLDER, 'default_eo.txt'),
    'fil': os.path.join(WORD_LIST_FOLDER, 'default_fil.txt'),
    'fi': os.path.join(WORD_LIST_FOLDER, 'default_fi.txt'),
    'fr': os.path.join(WORD_LIST_FOLDER, 'default_fr.txt'),
    'fr-CA-u-sd-caqc': os.path.join(WORD_LIST_FOLDER, 'default_fr-CA-u-sd-caqc.txt'),
    'de': os.path.join(WORD_LIST_FOLDER, 'default_de.txt'),
    'hi': os.path.join(WORD_LIST_FOLDER, 'default_hi.txt'),
    'hu': os.path.join(WORD_LIST_FOLDER, 'default_hu.txt'),
    'it': os.path.join(WORD_LIST_FOLDER, 'default_it.txt'),
    'ja': os.path.join(WORD_LIST_FOLDER, 'default_ja.txt'),
    'kab': os.path.join(WORD_LIST_FOLDER, 'default_kab.txt'),
    'tlh': os.path.join(WORD_LIST_FOLDER, 'default_tlh.txt'),
    'ko': os.path.join(WORD_LIST_FOLDER, 'default_ko.txt'),
    'no': os.path.join(WORD_LIST_FOLDER, 'default_no.txt'),
    'fa': os.path.join(WORD_LIST_FOLDER, 'default_fa.txt'),
    'pl': os.path.join(WORD_LIST_FOLDER, 'default_pl.txt'),
    'pt': os.path.join(WORD_LIST_FOLDER, 'default_pt.txt'),
    'ru': os.path.join(WORD_LIST_FOLDER, 'default_ru.txt'),
    'es': os.path.join(WORD_LIST_FOLDER, 'default_es.txt'),
    'sv': os.path.join(WORD_LIST_FOLDER, 'default_sv.txt'),
    'th': os.path.join(WORD_LIST_FOLDER, 'default_th.txt'),
    'tr': os.path.join(WORD_LIST_FOLDER, 'default_tr.txt'),
}

print("Loading default word lists...", flush=True)
loaded_list_count = 0
for lang_code, filepath in DEFAULT_LIST_FILES.items():
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                words = [line.strip().lower() for line in f if line.strip()]
                if words:
                    DEFAULT_WORD_LISTS[lang_code] = words
                    print(f"✅ Loaded {len(words)} words for '{lang_code}' from {filepath}.", flush=True)
                    loaded_list_count += 1
                else:
                    print(f"⚠️ Warning: {filepath} for '{lang_code}' is empty.", flush=True)
        except Exception as e:
            print(f"❌ Error loading {filepath} for '{lang_code}': {e}", flush=True)
    else:
        print(f"⚠️ Warning: Default list file not found: {filepath} for '{lang_code}'.", flush=True)

if loaded_list_count == 0:
    print("❌ WARNING: No default word lists were loaded successfully! Check file paths and names.", flush=True)
# --- End of word list loading ---


# Store progress per session
progress_store = {}

# --- Helper Functions ---

def parse_spotify_url(url):
    match = re.search(r"open\.spotify\.com/(track|album|playlist)/([a-zA-Z0-9]+)", url)
    return match.groups() if match else (None, None)

def refresh_token_if_needed():
    token_info = session.get("token_info")
    if not token_info: return None
    now = datetime.now().timestamp()
    expires_at = token_info.get("expires_at", 0)
    # Refresh if expires_at is missing or token is expired/expiring soon (e.g., within 60 seconds)
    if not expires_at or now >= expires_at - 60:
        try:
            print(f"Refreshing Spotify token (Expires at: {expires_at}, Now: {now})", flush=True)
            token_info = sp_oauth.refresh_access_token(token_info.get("refresh_token")) # Use get() for safety
            session["token_info"] = token_info
            print("Token refreshed successfully.", flush=True)
        except Exception as e:
            print(f"❌ Error refreshing Spotify token: {e}", flush=True)
            session.clear() # Clear session on refresh failure
            return None
    return token_info


def clean_track_title(title):
    # Remove featuring artists more robustly
    title = re.sub(r"\s+\(feat\.[^)]+\)", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+\[feat\.[^]]+\]", "", title, flags=re.IGNORECASE)
    # Remove various suffixes like (Remix), (Live), - From ..., etc.
    title = re.sub(r"\s+\((Remix|Live|Acoustic|Radio Edit)\)", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+-\s+(Remix|Live|Acoustic|Radio Edit|From .*|Mono|Stereo)", "", title, flags=re.IGNORECASE)
    # Remove version indicators like (Pt. 1), (Vol. 2)
    title = re.sub(r"\s+\((Pt\.|Vol\.)\s*\d+\)", "", title, flags=re.IGNORECASE)
    # Remove trailing hyphens or spaces left after cleaning
    title = title.strip(' -')
    return title.strip()


def get_lyrics_from_lrclib(title, artist, album, duration):
    # (No changes needed here for now)
    url = "https://lrclib.net/api/get"
    params = { "track_name": title, "artist_name": artist, "album_name": album, "duration": int(duration) }
    headers = {"User-Agent": "FCCSongChecker/1.0 (Backend)"} # Add User-Agent
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"LRCLIB request for '{title}' status: {response.status_code}", flush=True) # Log status
        if response.status_code != 200: return None, None
        data = response.json()
        synced = data.get("syncedLyrics")
        if not synced:
            print(f"LRCLIB found entry for '{title}' but no synced lyrics.", flush=True)
            # Still return the URL if found, even without synced lyrics
            lrclib_url = f"https.lrclib.net/track/{data.get('id')}" if data.get('id') else None
            return None, lrclib_url # Return None for lines, but keep URL
        lines = [(int(m) * 60 + float(s), txt.strip()) for m, s, txt in re.findall(r"\[(\d+):(\d+\.\d+)\]\s*(.*)", synced)]
        lrclib_url = f"https.lrclib.net/track/{data.get('id')}" if data.get('id') else None
        print(f"LRCLIB SUCCESS for '{title}' - Found {len(lines)} lines.", flush=True)
        return lines, lrclib_url
    except Exception as e:
        print(f"⚠️ LRCLIB fetch EXCEPTION for '{title}': {e}", flush=True)
        return None, None

# --- get_lyrics_from_genius with detailed logging ---
def get_lyrics_from_genius(title, artist):
    if genius is None: # Check if genius client initialized correctly
        print("Genius client not available (check API key or initialization).", flush=True)
        return None, None
    try:
        # Log exactly what is being searched
        print(f"Attempting Genius search with Title: '{title}', Artist: '{artist}'", flush=True)
        song = genius.search_song(title, artist)

        # Log the result of the search
        if song:
            print(f"Genius found song object: ID={song.id}, Title='{song.title}', Artist='{song.artist}'", flush=True)
            if song.lyrics:
                print(f"Genius SUCCESS: Lyrics found for '{title}'.", flush=True)
                # Return lowercase lyrics and URL
                return (song.lyrics.lower(), song.url)
            else:
                print(f"Genius WARNING: Found song object for '{title}' but lyrics attribute is empty.", flush=True)
                return None, song.url # Return None for lyrics, but keep URL if found
        else:
            print(f"Genius FAILED: No song object found for Title: '{title}', Artist: '{artist}'", flush=True)
            return None, None

    except Exception as e:
        # Log the specific error encountered
        print(f"❌ Genius search EXCEPTION for Title: '{title}', Artist: '{artist}': {type(e).__name__} - {e}", flush=True)
        return None, None
# --- End of modification ---

def analyze_track_lyrics(track_obj, track_number, flagged_words):
    """Analyzes a single track object for a given list of flagged words."""
    if not track_obj:
        return {"track_number": track_number, "track_name": "Track not available", "status": "Error", "flagged_words": [], "genius_url": None, "lrclib_url": None}

    # Ensure essential track info exists
    track_name = track_obj.get("name", "Unknown Track")
    main_artist = track_obj.get("artists", [{}])[0].get("name", "Unknown Artist")
    album_name = track_obj.get("album", {}).get("name", "")
    duration = track_obj.get("duration_ms", 0) / 1000

    # Clean title specifically for searching lyrics providers
    title_clean_search = clean_track_title(track_name)
    print(f"--- Analyzing Track {track_number}: '{track_name}' by '{main_artist}' (Cleaned: '{title_clean_search}') ---", flush=True)

    # --- Add DEBUG print before LRCLIB call ---
    print(f"DEBUG: Starting lyric search for '{track_name}'", flush=True)
    lrclib_lines, lrclib_url = get_lyrics_from_lrclib(title_clean_search, main_artist, album_name, duration)

    if lrclib_lines is not None and len(lrclib_lines) > 0: # Explicitly check for non-empty list
        print(f"Processing LRCLIB results for '{track_name}'.", flush=True)
        flagged_entries = []
        flagged_set = set(flagged_words)
        for time_sec, line_text in lrclib_lines:
            line_lower = line_text.lower()
            phrases_found_in_line = set()
            for phrase in flagged_set:
                if ' ' in phrase and phrase in line_lower:
                    flagged_entries.append({"timestamp": round(time_sec, 3), "context": phrase})
                    phrases_found_in_line.add(phrase)
            words_in_line = re.findall(r'\b\w+\b', line_lower)
            for word in words_in_line:
                if word in flagged_set and ' ' not in word:
                    part_of_found_phrase = False
                    for found_phrase in phrases_found_in_line:
                        if word in found_phrase.split():
                           part_of_found_phrase = True; break
                    if not part_of_found_phrase:
                        flagged_entries.append({"timestamp": round(time_sec, 3), "context": word})
        unique_flagged = [dict(t) for t in {tuple(sorted(d.items())) for d in flagged_entries}]
        status = "Explicit" if unique_flagged else "Clean"
        print(f"LRCLIB Result for '{track_name}': Status={status}, Found={len(unique_flagged)}.", flush=True)
        return {"track_number": track_number, "track_name": track_name, "status": status,
                 "flagged_words": unique_flagged, "genius_url": None, "lrclib_url": lrclib_url}

    # --- If LRCLIB failed or returned empty, try Genius ---
    print(f"LRCLIB failed or returned no lines for '{track_name}', trying Genius...", flush=True)
    lyrics, genius_url = get_lyrics_from_genius(title_clean_search, main_artist)

    if lyrics is None:
        print(f"Genius also failed for '{track_name}'. Reporting 'Lyrics Not Found'.", flush=True)
        # Return "Lyrics Not Found" only if BOTH fail
        return {"track_number": track_number, "track_name": track_name, "status": "Lyrics Not Found",
                 "flagged_words": [], "genius_url": genius_url, "lrclib_url": lrclib_url} # Keep URLs if found

    # --- Found lyrics on Genius ---
    print(f"Processing Genius results for '{track_name}'.", flush=True)
    # Ensure lyrics is a string before searching
    if not isinstance(lyrics, str):
        print(f"Genius WARNING: Lyrics found but are not a string for '{track_name}'. Type: {type(lyrics)}", flush=True)
        return {"track_number": track_number, "track_name": track_name, "status": "Lyrics Format Error",
                 "flagged_words": [], "genius_url": genius_url, "lrclib_url": None}

    found_words = [w for w in flagged_words if re.search(rf"\b{re.escape(w)}\b", lyrics, re.IGNORECASE)]
    status = "Explicit" if found_words else "Clean"
    simple_found = list(set(found_words))
    print(f"Genius Result for '{track_name}': Status={status}, Found={len(simple_found)}.", flush=True)
    return {"track_number": track_number, "track_name": track_name, "status": status,
             "flagged_words": simple_found, "genius_url": genius_url, "lrclib_url": None}


# --- Flask Routes ---

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    build_path = os.path.join(os.path.dirname(__file__), "build")
    if not os.path.exists(build_path):
        return "Build folder not found. Make sure the React app is built and placed correctly.", 500

    if path != "" and os.path.exists(os.path.join(build_path, path)):
        return send_from_directory(build_path, path)
    elif os.path.exists(os.path.join(build_path, "index.html")):
        return send_from_directory(build_path, "index.html")
    else:
        return "index.html not found in build folder.", 404

@app.route("/login")
def login():
    auth_url = sp_oauth.get_authorize_url()
    print(f"Redirecting user to Spotify login: {auth_url}", flush=True)
    return redirect(auth_url)

@app.route("/callback")
def callback():
    try:
        code = request.args.get("code")
        if not code:
            return "Error: No authorization code received from Spotify.", 400
        print("Received callback code from Spotify.", flush=True)
        token_info = sp_oauth.get_access_token(code, as_dict=True)
        session["token_info"] = token_info
        print("Spotify token obtained and stored in session.", flush=True)
        frontend_url = os.getenv('FRONTEND_URL', 'http://127.0.0.1:5000') # Default for local dev
        redirect_url = f"{frontend_url}?logged_in=true"
        print(f"Redirecting back to frontend: {redirect_url}", flush=True)
        return redirect(redirect_url)
    except Exception as e:
        print(f"❌ Error during Spotify callback: {e}", flush=True)
        return f"Error during Spotify login callback: {str(e)}", 500


@app.route("/logout")
def logout():
    session.clear()
    print("User session cleared (logout).", flush=True)
    return jsonify({"logged_out": True})

@app.route("/me")
def me():
    token_info = refresh_token_if_needed()
    if not token_info:
        print("GET /me: No valid token, user not logged in.", flush=True)
        return jsonify({"logged_in": False}), 401 # Return 401 Unauthorized
    try:
        sp = spotipy.Spotify(auth=token_info["access_token"])
        user_profile = sp.current_user()
        # Store user ID in session if available, for a more stable progress key
        user_id = user_profile.get("id")
        if user_id:
             session["user_id"] = user_id
        print(f"GET /me: User '{user_profile.get('display_name')}' logged in (ID: {user_id}).", flush=True)
        return jsonify({
            "logged_in": True,
            "id": user_id,
            "name": user_profile.get("display_name", "Unknown"),
            "default_word_lists": DEFAULT_WORD_LISTS
        })
    except Exception as e:
        print(f"❌ Error fetching user profile from Spotify: {e}", flush=True)
        if isinstance(e, spotipy.exceptions.SpotifyException) and e.http_status in [401, 403]:
             print("Spotify token invalid or expired, clearing session.", flush=True)
             session.clear()
             return jsonify({"logged_in": False, "error": "Spotify token invalid, session cleared."}), 401
        return jsonify({"logged_in": False, "error": f"Failed to fetch Spotify profile: {str(e)}"}), 500


# --- SEARCH ROUTE ---
@app.route("/search", methods=["POST"])
def search():
    token_info = refresh_token_if_needed()
    if not token_info: return jsonify({"error": "User not logged in."}), 401

    data = request.get_json()
    query = data.get("query")
    if not query: return jsonify({"error": "No query provided."}), 400
    print(f"POST /search: Query='{query}'", flush=True)

    sp = spotipy.Spotify(auth=token_info["access_token"])
    search_query = query

    try:
        results = sp.search(q=search_query, type='track,album', limit=5, market='US')
        formatted_results = []

        if results.get('tracks'):
            print(f"Found {len(results['tracks']['items'])} tracks.", flush=True)
            for item in results['tracks']['items']:
                if not item or not item.get('artists'): continue
                formatted_results.append({
                    "type": "Track", "name": item['name'],
                    "artist": item['artists'][0]['name'],
                    "cover": item['album']['images'][-1]['url'] if item.get('album') and item['album']['images'] else None,
                    "url": item['external_urls']['spotify']
                })
        if results.get('albums'):
            print(f"Found {len(results['albums']['items'])} albums.", flush=True)
            for item in results['albums']['items']:
                if not item or not item.get('artists'): continue
                formatted_results.append({
                    "type": "Album", "name": item['name'],
                    "artist": item['artists'][0]['name'],
                    "cover": item['images'][-1]['url'] if item.get('images') and item['images'] else None,
                    "url": item['external_urls']['spotify']
                })
        print(f"Returning {len(formatted_results)} search results.", flush=True)
        return jsonify(formatted_results[:10]) # Limit total results
    except Exception as e:
        print(f"❌ POST /search: Spotify API Error: {str(e)}", flush=True)
        error_message = f"Spotify API error during search: {str(e)}"
        if isinstance(e, spotipy.exceptions.SpotifyException):
             error_message = f"Spotify API error ({e.http_status}) during search: {e.msg}"
             return jsonify({"error": error_message}), e.http_status or 500
        return jsonify({"error": error_message}), 500


@app.route("/progress")
def progress():
    session_key = session.get("user_id") or session.get("token_info", {}).get("access_token")
    if not session_key:
        return jsonify({"percent": 0, "current_track": ""})
    return jsonify(progress_store.get(session_key, {"percent": 0, "current_track": ""}))

@app.route("/analyze", methods=["POST"])
def analyze():
    token_info = refresh_token_if_needed()
    if not token_info: return jsonify({"error": "User not logged in. Please log in again."}), 401

    data = request.get_json()
    url = data.get("url")
    custom_words_str = data.get("custom_words", "")
    selected_defaults = data.get("selected_defaults", [])

    if not url: return jsonify({"error": "No URL provided."}), 400
    print(f"\n--- POST /analyze: URL='{url}' ---", flush=True)

    user_id = session.get("user_id")
    session_key = user_id or token_info["access_token"]
    progress_store[session_key] = {"percent": 0, "current_track": ""}

    # Determine the final word list
    flagged_words_to_use = set()

    if custom_words_str.strip():
        print("Using custom word list provided by user.", flush=True)
        processed_str = custom_words_str.replace(",", "\n")
        custom_list = [
            line.strip().lower() for line in processed_str.splitlines() if line.strip()
        ]
        flagged_words_to_use.update(custom_list)
    else:
        print(f"Using selected default lists: {selected_defaults}", flush=True)
        for lang_code in selected_defaults:
            if lang_code in DEFAULT_WORD_LISTS:
                flagged_words_to_use.update(DEFAULT_WORD_LISTS[lang_code])
            else:
                print(f"Warning: Requested default list '{lang_code}' not found/loaded on backend.", flush=True)

    final_word_list = list(flagged_words_to_use)

    if not final_word_list:
        print("Error: No flagged words selected or provided.", flush=True)
        if session_key in progress_store: del progress_store[session_key]
        return jsonify({"error": "No flagged words selected or provided."}), 400

    print(f"Analyzing with {len(final_word_list)} unique words.", flush=True)

    url_type, item_id = parse_spotify_url(url)
    if not url_type or not item_id:
         print(f"Error: Invalid Spotify URL format: {url}", flush=True)
         if session_key in progress_store: del progress_store[session_key]
         return jsonify({"error": "Invalid or unsupported Spotify URL format."}), 400

    sp = spotipy.Spotify(auth=token_info["access_token"])
    tracks_to_process = []
    response_data = {"type": url_type}

    try:
        print(f"Fetching '{url_type}' with ID: {item_id} from Spotify...", flush=True)
        if url_type == 'track':
            track_info = sp.track(item_id)
            tracks_to_process = [track_info] if track_info else []
            if tracks_to_process and track_info.get("album"):
                 response_data.update({"name": track_info["album"]["name"], "artist": track_info["artists"][0]["name"], "album_cover": track_info["album"]["images"][0]["url"] if track_info["album"]["images"] else None})
            elif tracks_to_process:
                 response_data.update({"name": track_info["name"], "artist": track_info["artists"][0]["name"], "album_cover": None})

        elif url_type == 'album':
            album_info = sp.album(item_id)
            if not album_info: raise Exception(f"Album ID {item_id} not found or unavailable.")
            album_tracks_results = sp.album_tracks(item_id, limit=50)
            album_track_ids = [t['id'] for t in album_tracks_results['items'] if t and t.get('id')]
            offset = 0; full_track_objects = []
            while offset < len(album_track_ids):
                 batch_ids = album_track_ids[offset:offset+50]; offset += 50
                 if not batch_ids: break
                 try:
                    batch_tracks = sp.tracks(batch_ids)
                    full_track_objects.extend(t for t in batch_tracks['tracks'] if t)
                 except spotipy.exceptions.SpotifyException as batch_error:
                    print(f"Warning: Error fetching batch of album tracks: {batch_error}", flush=True)
            tracks_to_process = full_track_objects
            response_data.update({"name": album_info["name"], "artist": album_info["artists"][0]["name"], "album_cover": album_info["images"][0]["url"] if album_info["images"] else None})

        elif url_type == 'playlist':
            playlist_info = sp.playlist(item_id, fields='name,owner.display_name,images,tracks.total') # Initial fetch minimal
            if not playlist_info: raise Exception(f"Playlist ID {item_id} not found or unavailable.")
            response_data.update({"name": playlist_info["name"], "owner": playlist_info["owner"]["display_name"], "cover": playlist_info["images"][0]["url"] if playlist_info["images"] else None})

            items = []; offset = 0; limit = 100
            while True: # Fetch all pages
                try:
                    results = sp.playlist_items(item_id,
                                                fields='items(is_local,track(id,name,artists,album(name,images),duration_ms,external_urls)),next,offset,total',
                                                limit=limit, offset=offset)
                    current_items = results.get('items', [])
                    items.extend(item for item in current_items
                                 if item and not item.get('is_local') and item.get('track'))
                    # Check if 'next' exists AND if we actually received items in this page
                    # If 'next' is None OR we received 0 items, stop.
                    if results.get('next') is None or len(current_items) == 0:
                        break
                    offset += len(current_items) # Increment offset by items *received*

                except spotipy.exceptions.SpotifyException as page_error:
                     print(f"Warning: Error fetching playlist page (offset {offset}): {page_error}", flush=True)
                     break # Stop fetching pages on error
                time.sleep(0.05) # Small delay between pages
            tracks_to_process = [item["track"] for item in items]

        print(f"Found {len(tracks_to_process)} tracks to process.", flush=True)

    except Exception as e:
        print(f"❌ POST /analyze: Spotify API Error during item fetch: {str(e)}", flush=True)
        if session_key in progress_store: del progress_store[session_key]
        if isinstance(e, spotipy.exceptions.SpotifyException):
             return jsonify({"error": f"Spotify API error ({e.http_status}): {e.msg}"}), e.http_status or 500
        return jsonify({"error": f"Spotify API error: {str(e)}"}), 500


    analysis_results = []
    total_tracks = len(tracks_to_process)
    if total_tracks == 0:
        if url_type == 'track':
             print(f"Error: Could not retrieve track data for ID {item_id}.", flush=True)
             if session_key in progress_store: del progress_store[session_key]
             return jsonify({"error": "Could not retrieve track data. The URL might be invalid or the track unavailable."}), 400
        response_data["tracks"] = []
        if session_key in progress_store: del progress_store[session_key]
        print("Analysis finished: No processable tracks found (e.g., empty playlist).", flush=True)
        return jsonify(response_data) # Return empty results


    for idx, track_obj in enumerate(tracks_to_process, start=1):
        if not track_obj or not track_obj.get('id') or not track_obj.get('name'):
            print(f"Warning: Skipping invalid/incomplete track object at index {idx-1}", flush=True)
            analysis_results.append({
                "track_number": idx, "track_name": "Track Data Unavailable", "status": "Error",
                "flagged_words": [], "genius_url": None, "lrclib_url": None
            })
            continue

        if 'album' not in track_obj or track_obj['album'] is None: track_obj['album'] = {'name': '', 'images': []}
        if 'artists' not in track_obj or not track_obj['artists']: track_obj['artists'] = [{'name': 'Unknown Artist'}]

        current_track_name = track_obj.get("name", f"Track {idx}")
        progress_store[session_key] = {"percent": int((idx / total_tracks) * 100), "current_track": current_track_name}

        try:
            result = analyze_track_lyrics(track_obj, idx, final_word_list)
            analysis_results.append(result)
        except Exception as track_error:
             # Log the full traceback for unexpected errors during analysis
             import traceback
             print(f"❌❌❌ UNEXPECTED Error analyzing track '{current_track_name}' (Index {idx-1}): {track_error}\n{traceback.format_exc()}", flush=True)
             analysis_results.append({
                "track_number": idx, "track_name": current_track_name, "status": "Analysis Error",
                "flagged_words": [], "genius_url": None, "lrclib_url": None
            })

        time.sleep(0.05) # Slightly reduce sleep time

    response_data["tracks"] = analysis_results
    if session_key in progress_store:
        try: del progress_store[session_key]
        except KeyError: pass # Ignore if key already removed
    print("Analysis finished successfully.", flush=True)
    return jsonify(response_data)


if __name__ == "__main__":
    is_production = os.environ.get('RENDER', False)
    if not is_production and not os.path.exists('build'):
        print("WARNING: 'build' folder not found. Frontend may not be served.", flush=True)
    # Use environment variable for port, default to 5000 for local dev
    port = int(os.environ.get('PORT', 5000))
    # Run on 0.0.0.0 to be accessible externally (required by Render)
    app.run(host='0.0.0.0', port=port, debug=not is_production)