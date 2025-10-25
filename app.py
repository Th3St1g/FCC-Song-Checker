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

# --- Load multiple default word lists from subfolder ---
DEFAULT_WORD_LISTS = {}
# --- MODIFIED: Define the subfolder path ---
WORD_LIST_FOLDER = "List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words"

# --- MODIFIED: Update filenames to include the subfolder ---
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

print("Loading default word lists...")
for lang_code, filepath in DEFAULT_LIST_FILES.items(): # Use filepath now
    # Check using the full filepath
    if os.path.exists(filepath):
        try:
            # Open using the full filepath
            with open(filepath, "r", encoding="utf-8") as f:
                words = [line.strip().lower() for line in f if line.strip()]
                if words:
                    DEFAULT_WORD_LISTS[lang_code] = words
                    print(f"✅ Loaded {len(words)} words for '{lang_code}' from {filepath}.")
                else:
                    print(f"⚠️ Warning: {filepath} for '{lang_code}' is empty.")
        except Exception as e:
            print(f"❌ Error loading {filepath} for '{lang_code}': {e}")
    else:
        print(f"⚠️ Warning: Default list file not found: {filepath} for '{lang_code}'.")

if not DEFAULT_WORD_LISTS:
    raise ValueError("❌ No default word lists were loaded successfully!")
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
        lrclib_url = f"https.lrclib.net/track/{data.get('id')}" if data.get('id') else None
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
        flagged_set = set(flagged_words) # Use set for efficiency
        for time_sec, line_text in lrclib_lines:
            line_lower = line_text.lower() # Lowercase line once
            phrases_found_in_line = set() # Track phrases found to avoid double-counting words within them

            # Check for multi-word phrases first
            for phrase in flagged_set:
                if ' ' in phrase and phrase in line_lower:
                    flagged_entries.append({"timestamp": round(time_sec, 3), "context": phrase})
                    phrases_found_in_line.add(phrase)

            # Check for single words, ensuring they aren't part of an already found phrase
            words_in_line = re.findall(r'\b\w+\b', line_lower)
            for word in words_in_line:
                if word in flagged_set and ' ' not in word:
                    # Check if this word is part of any phrase already added for this timestamp
                    part_of_found_phrase = False
                    for found_phrase in phrases_found_in_line:
                        # Simple check if word is in the phrase's words
                        if word in found_phrase.split(): 
                           part_of_found_phrase = True
                           break
                    if not part_of_found_phrase:
                        flagged_entries.append({"timestamp": round(time_sec, 3), "context": word})

        # Deduplicate final entries 
        unique_flagged = [dict(t) for t in {tuple(sorted(d.items())) for d in flagged_entries}]
        status = "Explicit" if unique_flagged else "Clean"
        return {"track_number": track_number, "track_name": track_obj["name"], "status": status, "flagged_words": unique_flagged, "genius_url": None, "lrclib_url": lrclib_url}


    lyrics, genius_url = get_lyrics_from_genius(title_clean, main_artist)
    if lyrics is None:
        return {"track_number": track_number, "track_name": track_obj["name"], "status": "Lyrics Not Found", "flagged_words": [], "genius_url": None, "lrclib_url": lrclib_url}

    # Find matches using word boundaries for accuracy
    found_words = [w for w in flagged_words if re.search(rf"\b{re.escape(w)}\b", lyrics, re.IGNORECASE)]
    status = "Explicit" if found_words else "Clean"
    # Convert back to simple list for Genius results for now
    simple_found = list(set(found_words))
    return {"track_number": track_number, "track_name": track_obj["name"], "status": status, "flagged_words": simple_found, "genius_url": genius_url, "lrclib_url": None}


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

    # --- Send the dictionary of default lists ---
    return jsonify({
        "logged_in": True,
        "id": user_profile.get("id"),
        "name": user_profile.get("display_name", "Unknown"),
        "default_word_lists": DEFAULT_WORD_LISTS # Send the dict
    })

# --- SEARCH ROUTE ---
@app.route("/search", methods=["POST"])
def search():
    token_info = refresh_token_if_needed()
    if not token_info: return jsonify({"error": "User not logged in."}), 401

    data = request.get_json()
    query = data.get("query")
    if not query: return jsonify({"error": "No query provided."}), 400

    sp = spotipy.Spotify(auth=token_info["access_token"])
    search_query = query

    try:
        results = sp.search(q=search_query, type='track,album', limit=5, market='US')
        formatted_results = []

        if results.get('tracks'):
            for item in results['tracks']['items']:
                if not item.get('artists'): continue
                formatted_results.append({
                    "type": "Track", "name": item['name'],
                    "artist": item['artists'][0]['name'],
                    "cover": item['album']['images'][-1]['url'] if item.get('album') and item['album']['images'] else None,
                    "url": item['external_urls']['spotify']
                })
        if results.get('albums'):
            for item in results['albums']['items']:
                if not item.get('artists'): continue
                formatted_results.append({
                    "type": "Album", "name": item['name'],
                    "artist": item['artists'][0]['name'],
                    "cover": item['images'][-1]['url'] if item.get('images') and item['images'] else None,
                    "url": item['external_urls']['spotify']
                })
        return jsonify(formatted_results[:10])
    except Exception as e:
        print(f"!!! SEARCH CRASH: {str(e)}")
        error_message = f"Spotify API error: {str(e)}"
        if hasattr(e, 'http_status'): error_message = f"Spotify API error ({e.http_status}): {e.msg}"
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
    selected_defaults = data.get("selected_defaults", []) # Expecting a list like ['en', 'es']

    if not url: return jsonify({"error": "No URL provided."}), 400

    sp = spotipy.Spotify(auth=token_info["access_token"])
    session_id = token_info["access_token"]
    progress_store[session_id] = {"percent": 0, "current_track": ""}

    # Determine the final word list
    flagged_words_to_use = set() # Use a set to automatically handle duplicates

    if custom_words_str.strip():
        print("Using custom word list from text area.")
        processed_str = custom_words_str.replace(",", "\n")
        custom_list = [
            line.strip().lower()
            for line in processed_str.splitlines()
            if line.strip()
        ]
        flagged_words_to_use.update(custom_list)
    else:
        print(f"Using selected default lists: {selected_defaults}")
        for lang_code in selected_defaults:
            if lang_code in DEFAULT_WORD_LISTS:
                flagged_words_to_use.update(DEFAULT_WORD_LISTS[lang_code])
            else:
                print(f"Warning: Requested default list '{lang_code}' not found/loaded.")

    # Convert set back to list for analysis function
    final_word_list = list(flagged_words_to_use)

    if not final_word_list:
        return jsonify({"error": "No flagged words selected or provided."}), 400

    print(f"Analyzing with {len(final_word_list)} unique words.")

    url_type, item_id = parse_spotify_url(url)
    if not url_type: return jsonify({"error": "Invalid or unsupported Spotify URL."}), 400

    tracks_to_process = []
    response_data = {"type": url_type}

    try:
        if url_type == 'track':
            track_info = sp.track(item_id)
            tracks_to_process = [track_info] if track_info else []
            if tracks_to_process:
                 response_data.update({"name": track_info["album"]["name"], "artist": track_info["artists"][0]["name"], "album_cover": track_info["album"]["images"][0]["url"] if track_info["album"]["images"] else None})
        elif url_type == 'album':
            album_info = sp.album(item_id)
            if not album_info: raise Exception("Album not found or unavailable.")
            album_tracks_results = sp.album_tracks(item_id, limit=50)
            album_track_ids = [t['id'] for t in album_tracks_results['items'] if t and t.get('id')] # Ensure IDs exist
            offset = 0
            full_track_objects = []
            while offset < len(album_track_ids):
                 batch_ids = album_track_ids[offset:offset+50]
                 if not batch_ids: break # Avoid empty request
                 try:
                    batch_tracks = sp.tracks(batch_ids)
                    full_track_objects.extend(t for t in batch_tracks['tracks'] if t) # Filter None tracks
                 except spotipy.exceptions.SpotifyException as batch_error:
                    print(f"Warning: Error fetching batch of album tracks: {batch_error}")
                 offset += 50
            tracks_to_process = full_track_objects
            response_data.update({"name": album_info["name"], "artist": album_info["artists"][0]["name"], "album_cover": album_info["images"][0]["url"] if album_info["images"] else None})
        elif url_type == 'playlist':
            playlist_info = sp.playlist(item_id, fields='name,owner.display_name,images,tracks.total,tracks.next')
            if not playlist_info: raise Exception("Playlist not found or unavailable.")
            response_data.update({"name": playlist_info["name"], "owner": playlist_info["owner"]["display_name"], "cover": playlist_info["images"][0]["url"] if playlist_info["images"] else None})

            items = []
            offset = 0
            limit = 100 
            while True:
                try:
                    results = sp.playlist_items(item_id,
                                                fields='items(track(id,name,artists,album(name,images),duration_ms,external_urls)),next,offset,total',
                                                limit=limit, offset=offset)
                    items.extend(item for item in results['items'] if item and item.get('track')) # Filter None items/tracks
                    offset += limit
                    if results['next'] is None: break 
                except spotipy.exceptions.SpotifyException as page_error:
                     print(f"Warning: Error fetching playlist page (offset {offset}): {page_error}")
                     break 
                time.sleep(0.05)

            tracks_to_process = [item["track"] for item in items]

    except Exception as e:
        print(f"!!! Spotify API Error during item fetch: {str(e)}")
        if isinstance(e, spotipy.exceptions.SpotifyException):
             return jsonify({"error": f"Spotify API error ({e.http_status}): {e.msg}"}), 500
        return jsonify({"error": f"Spotify API error: {str(e)}"}), 500


    analysis_results = []
    total_tracks = len(tracks_to_process)
    if total_tracks == 0:
        if url_type == 'track':
             return jsonify({"error": "Could not retrieve track data. The URL might be invalid or the track unavailable."}), 400
        response_data["tracks"] = []
        if session_id in progress_store: del progress_store[session_id]
        return jsonify(response_data) # Return empty results


    for idx, track_obj in enumerate(tracks_to_process, start=1):
        if not track_obj or not track_obj.get('id'): # More robust check
            print(f"Warning: Skipping invalid track object at index {idx-1}")
            analysis_results.append({
                "track_number": idx, "track_name": "Track Data Unavailable", "status": "Error",
                "flagged_words": [], "genius_url": None, "lrclib_url": None
            })
            continue

        progress_store[session_id] = {"percent": int((idx / total_tracks) * 100), "current_track": track_obj.get("name", "Processing...")}
        result = analyze_track_lyrics(track_obj, idx, final_word_list) # Use final list
        analysis_results.append(result)
        time.sleep(0.1) # Keep rate limiting

    response_data["tracks"] = analysis_results
    if session_id in progress_store: # Check if key exists 
        try:
           del progress_store[session_id] # Clear progress 
        except KeyError:
             print(f"Warning: Could not clear progress for session {session_id}, key already removed.")
    return jsonify(response_data)


if __name__ == "__main__":
    is_production = os.environ.get('RENDER', False)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=not is_production)