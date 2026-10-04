import io
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import grab_unsplash  # noqa: E402
import unsplash_client  # noqa: E402
from unsplash_client import UnsplashClient, UnsplashError, attribution  # noqa: E402

PHOTO = {
    "id": "abc123",
    "alt_description": "Waves at Sunset, Beach!",
    "width": 6000,
    "height": 4000,
    "urls": {s: f"https://images.unsplash.com/photo-abc?ixid=x&size={s}" for s in unsplash_client.SIZES},
    "links": {
        "html": "https://unsplash.com/photos/abc123",
        "download_location": "https://api.unsplash.com/photos/abc123/download?ixid=x",
    },
    "user": {"name": "Jane Doe", "links": {"html": "https://unsplash.com/@jane"}},
}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(calls):
    def _open(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        calls.append(req)
        if url.startswith("https://api.unsplash.com/search/photos"):
            return FakeResponse(json.dumps({"results": [PHOTO]}).encode())
        if url.startswith("https://api.unsplash.com/photos/abc123/download"):
            return FakeResponse(b'{"url": "x"}')
        if url.startswith("https://images.unsplash.com/"):
            return FakeResponse(b"JPEGDATA")
        raise AssertionError(f"unexpected url {url}")
    return _open


class ClientTests(unittest.TestCase):
    def test_missing_key_raises(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch.object(unsplash_client, "load_dotenv"):
            with self.assertRaises(UnsplashError):
                UnsplashClient()

    def test_search_sends_auth_and_params(self):
        calls = []
        with mock.patch("urllib.request.urlopen", fake_urlopen(calls)):
            results = UnsplashClient("KEY").search_photos("sunset beach", per_page=50, orientation="portrait")
        self.assertEqual(results, [PHOTO])
        req = calls[0]
        self.assertEqual(req.get_header("Authorization"), "Client-ID KEY")
        self.assertEqual(req.get_header("Accept-version"), "v1")
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(req.full_url).query))
        self.assertEqual(q["query"], "sunset beach")
        self.assertEqual(q["per_page"], "30")  # capped at API max
        self.assertEqual(q["orientation"], "portrait")
        self.assertNotIn("color", q)

    def test_download_tracks_and_resizes(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("urllib.request.urlopen", fake_urlopen(calls)):
            path = UnsplashClient("KEY").download(PHOTO, tmp, width=1920, height=1080)
            self.assertEqual(path.name, "abc123-waves-at-sunset-beach.jpg")
            self.assertEqual(path.read_bytes(), b"JPEGDATA")
        self.assertIn("/photos/abc123/download", calls[0].full_url)
        image_url = calls[1]
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(image_url).query))
        self.assertEqual((q["w"], q["h"], q["fit"], q["ixid"]), ("1920", "1080", "crop", "x"))

    def test_attribution(self):
        credit = attribution(PHOTO)
        self.assertEqual(credit["text"], "Photo by Jane Doe on Unsplash")
        self.assertIn("utm_source=", credit["photographer_url"])
        self.assertIn("utm_medium=referral", credit["photo_url"])


class CliTests(unittest.TestCase):
    def test_cli_writes_images_and_credits(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict("os.environ", {"UNSPLASH_ACCESS_KEY": "KEY"}), \
                mock.patch("urllib.request.urlopen", fake_urlopen(calls)), \
                mock.patch("sys.stdout", io.StringIO()):
            rc = grab_unsplash.main(["sunset beach", "--count", "1", "--out", tmp])
            self.assertEqual(rc, 0)
            credits = json.loads((Path(tmp) / "credits.json").read_text())
            self.assertEqual(credits[0]["file"], "abc123-waves-at-sunset-beach.jpg")
            self.assertIn("Jane Doe", (Path(tmp) / "credits.txt").read_text())


if __name__ == "__main__":
    unittest.main()
