import hmac
import json
import os
import secrets

import psycopg
from flask import (
    Flask,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from googleapiclient.errors import HttpError
from psycopg.rows import dict_row

from comments import create_youtube_client, extract_video


def _database_url():
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def _connect():
    database_url = current_app.config["DATABASE_URL"]
    if not database_url:
        raise RuntimeError("The history database is not configured on the server.")
    return psycopg.connect(database_url, row_factory=dict_row)


def _ensure_history_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS video_history (
            id BIGSERIAL PRIMARY KEY,
            video_id VARCHAR(11) NOT NULL,
            video_url TEXT NOT NULL,
            thumbnail_url TEXT NOT NULL DEFAULT '',
            extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def get_history():
    with _connect() as connection:
        with connection.cursor() as cursor:
            _ensure_history_table(cursor)
            cursor.execute(
                """
                SELECT video_url, thumbnail_url
                FROM video_history
                ORDER BY extracted_at DESC, id DESC
                """
            )
            return cursor.fetchall()


def add_history(video_id, video_url, thumbnail_url):
    with _connect() as connection:
        with connection.cursor() as cursor:
            _ensure_history_table(cursor)
            cursor.execute(
                """
                INSERT INTO video_history (video_id, video_url, thumbnail_url)
                VALUES (%s, %s, %s)
                """,
                (video_id, video_url, thumbnail_url),
            )


def _youtube_error_message(error):
    reason = ""
    message = ""
    try:
        payload = json.loads(error.content.decode("utf-8"))
        details = payload.get("error", {})
        errors = details.get("errors", [])
        if errors:
            reason = errors[0].get("reason", "")
        message = details.get("message", "")
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        pass

    if reason == "commentsDisabled":
        return "Comments are disabled for this video."
    if reason in {"quotaExceeded", "dailyLimitExceeded"}:
        return "The YouTube API quota has been exceeded. Please try again later."
    if message:
        return f"The YouTube API request failed: {message}"
    return f"The YouTube API request failed (HTTP {error.status_code})."


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", ""),
        APP_PASSWORD=os.environ.get("APP_PASSWORD", ""),
        YOUTUBE_API_KEY=os.environ.get("YOUTUBE_API_KEY", ""),
        DATABASE_URL=_database_url(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("RENDER", "").lower() == "true",
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("Set the SECRET_KEY environment variable.")

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": csrf_token}

    @app.before_request
    def require_login_and_csrf():
        if request.endpoint == "static":
            return None

        if request.endpoint != "login" and not session.get("authenticated"):
            return redirect(url_for("login"))

        if request.method == "POST":
            submitted_token = request.form.get("csrf_token", "")
            expected_token = session.get("csrf_token", "")
            if not expected_token or not hmac.compare_digest(
                submitted_token, expected_token
            ):
                abort(400, description="Form session expired; refresh and try again.")
        return None

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            configured_password = app.config["APP_PASSWORD"]
            submitted_password = request.form.get("password", "")
            if not configured_password:
                current_app.logger.error("APP_PASSWORD is not configured.")
                flash("The app password is not configured on the server.", "error")
                return render_template("login.html"), 503
            if hmac.compare_digest(submitted_password, configured_password):
                session.clear()
                session["authenticated"] = True
                return redirect(url_for("home"))
            flash("The password is incorrect.", "error")
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def home():
        try:
            history = get_history()
        except psycopg.Error:
            current_app.logger.exception("Could not load extraction history.")
            flash("Could not connect to the history database.", "error")
            return render_template("index.html", history=[]), 503
        except RuntimeError as error:
            flash(str(error), "error")
            return render_template("index.html", history=[]), 503
        return render_template("index.html", history=history)

    @app.post("/extract")
    def extract():
        video_url = request.form.get("video_url", "").strip()
        if not video_url:
            flash("Enter a YouTube video URL.", "error")
            return redirect(url_for("home"))

        try:
            youtube = create_youtube_client(app.config["YOUTUBE_API_KEY"])
            result = extract_video(youtube, video_url)
            add_history(result.video_id, result.video_url, result.thumbnail_url)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("home"))
        except RuntimeError as error:
            flash(str(error), "error")
            return redirect(url_for("home"))
        except HttpError as error:
            flash(_youtube_error_message(error), "error")
            return redirect(url_for("home"))
        except psycopg.Error:
            current_app.logger.exception("Could not save extraction history.")
            flash(
                "Could not save to the history database. The Excel download was not created.",
                "error",
            )
            return redirect(url_for("home"))

        return send_file(
            result.workbook,
            as_attachment=True,
            download_name=result.filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )
