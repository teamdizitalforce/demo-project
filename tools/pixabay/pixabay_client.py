"""Minimal Pixabay API client (stdlib only) for grabbing stock videos and images.

Docs: https://pixabay.com/api/docs/

Pixabay asks that API responses are cached for 24 hours, so search results are
cached on disk (see CACHE_DIR). Downloaded files are kept locally because
permanent hotlinking of Pixabay URLs is not allowed.
"""

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_ROOT = "https://pixabay.com/api/"
CACHE_DIR = Path(os.environ.get("PIXABAY_CACHE_DIR", Path(__file__).resolve().parent / ".cache"))
CACHE_TTL = 24 * 60 * 60

# Video renditions from largest to smallest. "large" (usually 4K) may be missing.
VIDEO_SIZES = ("large", "medium", "small", "tiny")
CATEGORIES = (
    "backgrounds", "fashion", "nature", "science", "education", "feelings", "health", "people",
    "religion", "places", "animals", "industry", "computer", "food", "sports", "transportation",
    "travel", "buildings", "business", "music",
)


class PixabayError(RuntimeError):
    pass


def load_dotenv(path=None):
    """Load KEY=VALUE lines from a .env file into os.environ (existing vars win)."""
    path = Path(path) if path else Path(__file__).resolve().parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class PixabayClient:
    def __init__(self, api_key=None, timeout=60, use_cache=True):
        if api_key is None:
            load_dotenv()
            api_key = os.environ.get("PIXABAY_API_KEY")
        if not api_key:
            raise PixabayError(
                "Missing Pixabay API key. Set PIXABAY_API_KEY or add it to tools/pixabay/.env"
            )
        self.api_key = api_key
        self.timeout = timeout
        self.use_cache = use_cache
        self.rate_limit = {}

    # -- HTTP -----------------------------------------------------------------

    def _get(self, endpoint, params):
        query = {k: _param(v) for k, v in params.items() if v is not None}
        cache_file = self._cache_file(endpoint, query)
        if cache_file and cache_file.is_file() and time.time() - cache_file.stat().st_mtime < CACHE_TTL:
            return json.loads(cache_file.read_text())

        url = API_ROOT + endpoint + "?" + urllib.parse.urlencode({"key": self.api_key, **query})
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                self.rate_limit = {
                    "limit": resp.headers.get("X-RateLimit-Limit"),
                    "remaining": resp.headers.get("X-RateLimit-Remaining"),
                    "reset": resp.headers.get("X-RateLimit-Reset"),
                }
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace").strip()
            if e.code == 429:
                raise PixabayError(f"Pixabay rate limit exceeded (100 requests/60s): {body}") from e
            raise PixabayError(f"Pixabay API {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise PixabayError(f"Could not reach Pixabay: {e.reason}") from e

        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data))
        return data

    def _cache_file(self, endpoint, query):
        if not self.use_cache:
            return None
        raw = json.dumps([endpoint, sorted(query.items())])
        return CACHE_DIR / (hashlib.sha256(raw.encode()).hexdigest()[:32] + ".json")

    # -- API ------------------------------------------------------------------

    def search_videos(self, query=None, per_page=20, page=1, video_type="all", category=None,
                      min_width=None, min_height=None, editors_choice=False, safesearch=True,
                      order="popular", lang="en"):
        """Search stock videos. video_type: all | film | animation."""
        data = self._get("videos/", {
            "q": _query(query),
            "lang": lang,
            "video_type": video_type,
            "category": category,
            "min_width": min_width,
            "min_height": min_height,
            "editors_choice": editors_choice,
            "safesearch": safesearch,
            "order": order,
            "page": page,
            "per_page": _per_page(per_page),
        })
        return data.get("hits", [])

    def get_video(self, video_id):
        hits = self._get("videos/", {"id": video_id}).get("hits", [])
        if not hits:
            raise PixabayError(f"No Pixabay video with id {video_id}")
        return hits[0]

    def search_images(self, query=None, per_page=20, page=1, image_type="photo", orientation="all",
                      category=None, min_width=None, min_height=None, colors=None,
                      editors_choice=False, safesearch=True, order="popular", lang="en"):
        """Search images. orientation: all | horizontal | vertical."""
        data = self._get("", {
            "q": _query(query),
            "lang": lang,
            "image_type": image_type,
            "orientation": orientation,
            "category": category,
            "min_width": min_width,
            "min_height": min_height,
            "colors": colors,
            "editors_choice": editors_choice,
            "safesearch": safesearch,
            "order": order,
            "page": page,
            "per_page": _per_page(per_page),
        })
        return data.get("hits", [])

    # -- Downloads ------------------------------------------------------------

    def download_video(self, video, dest_dir, size="medium"):
        """Download a video rendition, falling back to the next smaller size if missing."""
        rendition = pick_rendition(video, size)
        name = f"pixabay-{video['id']}-{_slugify(video.get('tags', ''))}-{rendition['width']}x{rendition['height']}.mp4"
        return self._save(rendition["url"], Path(dest_dir) / name.replace("--", "-"))

    def download_image(self, image, dest_dir):
        url = image.get("imageURL") or image.get("fullHDURL") or image["largeImageURL"]
        ext = Path(urllib.parse.urlsplit(url).path).suffix or ".jpg"
        name = f"pixabay-{image['id']}-{_slugify(image.get('tags', ''))}{ext}"
        return self._save(url, Path(dest_dir) / name.replace("--", "-"))

    def _save(self, url, out):
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".part")
        with urllib.request.urlopen(url, timeout=self.timeout) as resp, open(tmp, "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
        tmp.replace(out)
        return out


# -- Helpers --------------------------------------------------------------------

def pick_rendition(video, size="medium"):
    """Return the requested rendition, or the next smaller one that has a URL."""
    if size not in VIDEO_SIZES:
        raise ValueError(f"size must be one of {VIDEO_SIZES}")
    for name in VIDEO_SIZES[VIDEO_SIZES.index(size):]:
        rendition = video.get("videos", {}).get(name) or {}
        if rendition.get("url"):
            return {**rendition, "name": name}
    raise PixabayError(f"Video {video.get('id')} has no downloadable rendition at or below '{size}'")


def orientation_of(video, size="medium"):
    r = video.get("videos", {}).get(size) or pick_rendition(video, "large")
    if r["width"] > r["height"]:
        return "landscape"
    return "portrait" if r["height"] > r["width"] else "square"


def attribution(item, kind="video"):
    """Credit info Pixabay asks you to show wherever its media is used."""
    user, user_id = item.get("user", ""), item.get("user_id", "")
    return {
        "id": item["id"],
        "type": kind,
        "creator": user,
        "creator_url": f"https://pixabay.com/users/{user}-{user_id}/",
        "source_url": item.get("pageURL"),
        "tags": item.get("tags"),
        "duration": item.get("duration"),
        "text": f"{'Video' if kind == 'video' else 'Image'} by {user} from Pixabay",
    }


def _query(q):
    if q and len(q) > 100:
        raise ValueError("Pixabay search terms may not exceed 100 characters")
    return q


def _per_page(n):
    return max(3, min(int(n), 200))


def _param(v):
    return str(v).lower() if isinstance(v, bool) else v


def _slugify(text, max_len=40):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len].rstrip("-")
