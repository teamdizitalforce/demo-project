import io
import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import grab_pixabay  # noqa: E402
import pixabay_client  # noqa: E402
from pixabay_client import PixabayClient, PixabayError, attribution, orientation_of, pick_rendition  # noqa: E402


def rendition(name, w, h, url=True):
    return {
        "url": f"https://cdn.pixabay.com/video/125_{name}.mp4" if url else "",
        "width": w if url else 0,
        "height": h if url else 0,
        "size": 100 if url else 0,
        "thumbnail": "",
    }


def video(vid, w=1920, h=1080, duration=12, has_large=True):
    return {
        "id": vid,
        "pageURL": f"https://pixabay.com/videos/id-{vid}/",
        "type": "film",
        "tags": "flowers, yellow, blossom",
        "duration": duration,
        "videos": {
            "large": rendition("large", w * 2, h * 2, url=has_large),
            "medium": rendition("medium", w, h),
            "small": rendition("small", w * 2 // 3, h * 2 // 3),
            "tiny": rendition("tiny", w // 2, h // 2),
        },
        "user_id": 1281706,
        "user": "Coverr-Free-Footage",
    }


IMAGE = {
    "id": 195893,
    "pageURL": "https://pixabay.com/en/blossom-bloom-flower-195893/",
    "tags": "blossom, bloom, flower",
    "largeImageURL": "https://pixabay.com/get/ed6a99fd0a76647_1280.jpg",
    "user_id": 48777,
    "user": "Josch13",
}


class FakeResponse(io.BytesIO):
    headers = {"X-RateLimit-Limit": "100", "X-RateLimit-Remaining": "99", "X-RateLimit-Reset": "60"}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(calls, videos=None):
    def _open(url, timeout=None):
        calls.append(url)
        if url.startswith("https://pixabay.com/api/videos/"):
            return FakeResponse(json.dumps({"total": 1, "totalHits": 1, "hits": videos or []}).encode())
        if url.startswith("https://pixabay.com/api/"):
            return FakeResponse(json.dumps({"hits": [IMAGE]}).encode())
        if url.startswith(("https://cdn.pixabay.com/", "https://pixabay.com/get/")):
            return FakeResponse(b"MEDIA")
        raise AssertionError(f"unexpected url {url}")
    return _open


def query_of(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


class ClientTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(pixabay_client, "CACHE_DIR", Path(tmp.name) / "cache")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_key_raises(self):
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(pixabay_client, "load_dotenv"):
            with self.assertRaises(PixabayError):
                PixabayClient()

    def test_search_videos_params_and_rate_limit(self):
        calls = []
        with mock.patch("urllib.request.urlopen", fake_urlopen(calls, [video(125)])):
            client = PixabayClient("KEY")
            hits = client.search_videos("yellow flowers", per_page=1, category="nature")
        self.assertEqual([h["id"] for h in hits], [125])
        q = query_of(calls[0])
        self.assertEqual(q["key"], "KEY")
        self.assertEqual(q["q"], "yellow flowers")
        self.assertEqual(q["per_page"], "3")  # API minimum
        self.assertEqual(q["safesearch"], "true")
        self.assertEqual(q["category"], "nature")
        self.assertNotIn("min_width", q)
        self.assertEqual(client.rate_limit["remaining"], "99")

    def test_responses_are_cached(self):
        calls = []
        with mock.patch("urllib.request.urlopen", fake_urlopen(calls, [video(125)])):
            client = PixabayClient("KEY")
            client.search_videos("waves")
            client.search_videos("waves")
            client.search_videos("forest")
        self.assertEqual(len(calls), 2)

    def test_rate_limit_error(self):
        err = urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b"API rate limit exceeded"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaisesRegex(PixabayError, "rate limit"):
                PixabayClient("KEY", use_cache=False).search_videos("x")

    def test_network_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("blocked")):
            with self.assertRaisesRegex(PixabayError, "Could not reach Pixabay"):
                PixabayClient("KEY", use_cache=False).search_videos("x")

    def test_query_length_limit(self):
        with self.assertRaises(ValueError):
            PixabayClient("KEY").search_videos("x" * 101)

    def test_pick_rendition_falls_back_when_large_missing(self):
        v = video(1, has_large=False)
        self.assertEqual(pick_rendition(v, "large")["name"], "medium")
        self.assertEqual(pick_rendition(v, "small")["name"], "small")

    def test_orientation(self):
        self.assertEqual(orientation_of(video(1)), "landscape")
        self.assertEqual(orientation_of(video(2, w=1080, h=1920)), "portrait")

    def test_download_video(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch("urllib.request.urlopen", fake_urlopen(calls)):
            path = PixabayClient("KEY").download_video(video(125), tmp, size="medium")
            self.assertEqual(path.name, "pixabay-125-flowers-yellow-blossom-1920x1080.mp4")
            self.assertEqual(path.read_bytes(), b"MEDIA")
            self.assertEqual([p.name for p in Path(tmp).iterdir()], [path.name])  # no .part left over
        self.assertEqual(calls, ["https://cdn.pixabay.com/video/125_medium.mp4"])

    def test_attribution(self):
        credit = attribution(video(125))
        self.assertEqual(credit["text"], "Video by Coverr-Free-Footage from Pixabay")
        self.assertEqual(credit["creator_url"], "https://pixabay.com/users/Coverr-Free-Footage-1281706/")
        self.assertEqual(credit["source_url"], "https://pixabay.com/videos/id-125/")


class CliTests(unittest.TestCase):
    def run_cli(self, argv, videos):
        calls = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.dict("os.environ", {"PIXABAY_API_KEY": "KEY"}), \
                mock.patch.object(pixabay_client, "CACHE_DIR", Path(tmp.name) / "cache"), \
                mock.patch("urllib.request.urlopen", fake_urlopen(calls, videos)), \
                mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            rc = grab_pixabay.main(argv + ["--out", tmp.name])
        return rc, Path(tmp.name), calls

    def test_videos_filtered_by_orientation_and_duration(self):
        vids = [video(1, duration=40), video(2, w=1080, h=1920, duration=10), video(3, duration=8), video(4, duration=9)]
        rc, out, _ = self.run_cli(["waves", "--count", "1", "--orientation", "landscape", "--max-duration", "15"], vids)
        self.assertEqual(rc, 0)
        credits = json.loads((out / "credits.json").read_text())
        self.assertEqual([c["id"] for c in credits], [3])
        self.assertIn("Video by Coverr-Free-Footage from Pixabay", (out / "credits.txt").read_text())

    def test_images_mode(self):
        rc, out, calls = self.run_cli(["flowers", "--images", "--count", "1", "--orientation", "portrait"], [])
        self.assertEqual(rc, 0)
        self.assertEqual(query_of(calls[0])["orientation"], "vertical")
        self.assertTrue((out / "pixabay-195893-blossom-bloom-flower.jpg").is_file())

    def test_no_results(self):
        rc, _, _ = self.run_cli(["nothing"], [])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
