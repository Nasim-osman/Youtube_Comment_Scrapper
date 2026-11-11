import re
import unittest
from io import BytesIO
from unittest.mock import patch

from comments import ExtractionResult
from app import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "APP_PASSWORD": "test-password",
                "YOUTUBE_API_KEY": "test-api-key",
                "DATABASE_URL": "postgresql://test:test@localhost/test",
                "SESSION_COOKIE_SECURE": False,
            }
        )
        self.client = self.app.test_client()

    def _csrf_token(self, response):
        match = re.search(
            r'name="csrf_token" value="([^"]+)"',
            response.get_data(as_text=True),
        )
        self.assertIsNotNone(match)
        return match.group(1)

    def _login(self):
        login_page = self.client.get("/login")
        response = self.client.post(
            "/login",
            data={
                "password": "test-password",
                "csrf_token": self._csrf_token(login_page),
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_home_requires_password(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

    def test_login_rejects_bad_csrf_token(self):
        response = self.client.post(
            "/login",
            data={"password": "test-password", "csrf_token": "invalid"},
        )
        self.assertEqual(response.status_code, 400)

    def test_login_and_history_page(self):
        self._login()
        with patch("app.get_history", return_value=[]):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Video history", response.get_data(as_text=True))

    def test_extract_downloads_workbook_and_records_history(self):
        self._login()
        result = ExtractionResult(
            video_id="abcdefghijk",
            video_url="https://www.youtube.com/watch?v=abcdefghijk",
            title="Demo",
            thumbnail_url="https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg",
            filename="Demo.xlsx",
            workbook=BytesIO(b"excel-content"),
        )
        with (
            patch("app.create_youtube_client") as create_client,
            patch("app.extract_video", return_value=result) as extract_video,
            patch("app.add_history") as add_history,
            patch("app.get_history", return_value=[]),
        ):
            home = self.client.get("/")
            response = self.client.post(
                "/extract",
                data={
                    "video_url": "https://youtu.be/abcdefghijk",
                    "csrf_token": self._csrf_token(home),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment; filename=Demo.xlsx", response.headers["Content-Disposition"])
        self.assertEqual(response.data, b"excel-content")
        create_client.assert_called_once_with("test-api-key")
        extract_video.assert_called_once()
        add_history.assert_called_once_with(
            "abcdefghijk",
            "https://www.youtube.com/watch?v=abcdefghijk",
            "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg",
        )

    def test_invalid_video_url_is_reported(self):
        self._login()
        with patch("app.get_history", return_value=[]):
            home = self.client.get("/")
        response = self.client.post(
            "/extract",
            data={
                "video_url": "",
                "csrf_token": self._csrf_token(home),
            },
        )
        self.assertEqual(response.status_code, 302)
        with patch("app.get_history", return_value=[]):
            home = self.client.get("/")
        self.assertIn("Enter a YouTube video URL.", home.get_data(as_text=True))

    def test_login_page_uses_professional_english_copy(self):
        response = self.client.get("/login")
        page = response.get_data(as_text=True)
        self.assertIn('<html lang="en">', page)
        self.assertIn(
            "Welcome to Nasim's personal YouTube comment scraper site",
            page,
        )
        self.assertIn("Enter your app password to access the comment extractor.", page)
        self.assertIn(">Log In</button>", page)


if __name__ == "__main__":
    unittest.main()
