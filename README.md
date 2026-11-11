# YouTube Comment Extractor

A password-protected Flask app that downloads comments and replies for a YouTube video as an Excel workbook. Successful runs add only the video's canonical URL and thumbnail to the history; comment text and workbooks are not stored by the app.

## Run locally

1. Install Python dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. Set the required environment variables in PowerShell:

   ```powershell
   $env:YOUTUBE_API_KEY = "your-youtube-data-api-key"
   $env:APP_PASSWORD = "choose-a-private-password"
   $env:SECRET_KEY = "a-long-random-session-secret"
   $env:DATABASE_URL = "your-postgresql-connection-string"
   ```

3. Start the app:

   ```powershell
   python app.py
   ```

   Open `http://127.0.0.1:5000`.

The history database is PostgreSQL. The app creates its history table automatically the first time it is used.

## Deploy on Render

1. Create a PostgreSQL database in Render and copy its **internal database URL**.
2. Create a Python web service for this project.
3. Set the build command to `pip install -r requirements.txt`.
4. Set the start command to `gunicorn --bind 0.0.0.0:$PORT "app:create_app()"`.
5. Add these environment variables to the web service:
   - `DATABASE_URL`: the Render PostgreSQL internal database URL
   - `YOUTUBE_API_KEY`: a YouTube Data API v3 key
   - `APP_PASSWORD`: a password only you know
   - `SECRET_KEY`: a long, random value used to sign login sessions
6. Deploy the service and open its URL.

Creating a Render PostgreSQL database and running a web service may incur hosting charges. Keep the YouTube API key and app password in Render's environment settings, not in source files. The key previously embedded in `comments.py` should be rotated before deployment.

## Data and workbook behavior

- Each successful extraction downloads an `.xlsx` file named after the video's title.
- The workbook preserves the existing columns, comment/reply ordering, widths, header style, and wrapped cells.
- History contains the canonical video URL and thumbnail URL, not comments or workbook files.
- History persists across deployments through PostgreSQL.
- Very large videos may exceed a single web request's processing time; background extraction is not included in this initial version.
