FCC Song Checker
================

DESCRIPTION
-----------
FCC Song Checker is a web application built for radio DJs, station managers, and content creators. It allows a user to log in with their Spotify account, paste a Spotify URL (for a track, album, or playlist), and instantly analyze the lyrics against the default FCC-flagged word list or a custom-provided list.

The app clearly identifies which songs are "Explicit" and provides a list of flagged words found. For many tracks, it can even provide the exact timestamps of when the words appear, making it an essential tool for creating a clean broadcast.


FEATURES
--------
- Secure Spotify OAuth 2.0 login.
- Analyze single tracks, full albums, or entire playlists.
- Check against a default FCC word list (`fcc_words.txt`).
- Check against a user-provided custom word list.
- Provides exact timestamps for flagged words (powered by LRCLIB).
- Falls back to Genius for lyric analysis if timestamps are unavailable.
- Real-time progress bar for analyzing large playlists.
- Browser-based history of recent analyses.
- Interactive lyrics modal to view full lyrics with flagged words highlighted.


TECH STACK
----------
* **Backend:** Flask (Python)
* **Frontend:** React (JavaScript)
* **APIs:** Spotipy (Spotify), lyricsgenius (Genius), LRCLIB
* **Deployment:** Gunicorn, Render (or any platform supporting Python WSGI)


HOW TO DEPLOY (Secure Web Application)
--------------------------------------
This project is intended to be deployed as a secure web service to protect your API keys.

1.  **Build the React Frontend:**
    * In your React project folder, run `npm install` and then `npm run build`.

2.  **Organize Project:**
    * Create a new folder for deployment.
    * Place your `app.py` and `fcc_words.txt` in this folder.
    * Move the `build` folder (from step 1) into this same folder.

3.  **Create `requirements.txt`:**
    * Create a file named `requirements.txt` in the root and add the following:
        flask
        flask_cors
        spotipy
        lyricsgenius
        python-dotenv
        requests
        gunicorn

4.  **Code Adjustments:**
    * In `App.js` (before building), set `const BACKEND_URL = "";`
    * In `app.py`, remove the final `if __name__ == "__main__":` block.

5.  **Deploy to a Host (e.g., Render):**
    * Push your project to a GitHub repository (use a `.gitignore` to hide `.env`).
    * On Render, create a new "Web Service" connected to your repo.
    * Set the Build Command: `pip install -r requirements.txt`
    * Set the Start Command: `gunicorn app:app`

6.  **Set Environment Variables:**
    * On your hosting platform, go to "Environment" or "Secrets".
    * Create a "Secret File" named `.env` and paste your API keys into it.
    * Alternatively, add these environment variables one by one:
        * `SPOTIPY_CLIENT_ID`
        * `SPOTIPY_CLIENT_SECRET`
        * `SPOTIPY_REDIRECT_URI` (This MUST be your new URL, e.g., https://your-app.onrender.com/callback)
        * `GENIUS_API_TOKEN`
        * `FLASK_SECRET_KEY` (Create a long, random string for this)
        * `FRONTEND_URL` (Your base URL, e.g., https://your-app.onrender.com)

7.  **Update Spotify Dashboard:**
    * Go to your Spotify Developer Dashboard, open your app settings, and add your new `SPOTIPY_REDIRECT_URI` to the list of allowed URIs.


LICENSE
-------
This project is licensed under the MIT License. See the LICENSE file for details.