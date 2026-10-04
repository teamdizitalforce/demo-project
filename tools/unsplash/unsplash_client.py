"""Minimal Unsplash API client (stdlib only) for grabbing stock photos for videos.

Only the Access Key is needed: every call here uses Unsplash "Public" permissions.
The Secret Key is only for OAuth user actions and must never be committed.

Docs: https://unsplash.com/documentation
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_ROOT = "https://api.unsplash.com"
APP_NAME = os.environ.get("UNSPLASH_APP_NAME", "pankajs_app")

# Sizes Unsplash returns under photo["urls"].
SIZES = ("raw", "full", "regular", "small", "thumb")


class UnsplashError(RuntimeError):
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


class UnsplashClient:
    def __init__(self, access_key=None, timeout=30):
        if access_key is None:
            load_dotenv()
            access_key = os.environ.get("UNSPLASH_ACCESS_KEY")
        if not access_key:
            raise UnsplashError(
                "Missing Unsplash access key. Set UNSPLASH_ACCESS_KEY or add it to tools/unsplash/.env"
            )
        self.access_key = access_key
        self.timeout = timeout

    # -- HTTP -----------------------------------------------------------------

    def _get(self, path, params=None):
        query = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"{API_ROOT}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Client-ID {self.access_key}",
                "Accept-Version": "v1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise UnsplashError(f"Unsplash API {e.code} for {path}: {body}") from e
        except urllib.error.URLError as e:
            raise UnsplashError(f"Could not reach Unsplash: {e.reason}") from e

    # -- API ------------------------------------------------------------------

    def search_photos(self, query, per_page=10, page=1, orientation=None, color=None,
                      order_by="relevant", content_filter="high"):
        """Search photos. orientation: landscape | portrait | squarish."""
        data = self._get("/search/photos", {
            "query": query,
            "per_page": min(int(per_page), 30),
            "page": page,
            "orientation": orientation,
            "color": color,
            "order_by": order_by,
            "content_filter": content_filter,
        })
        return data.get("results", [])

    def random_photos(self, query=None, count=1, orientation=None, content_filter="high"):
        data = self._get("/photos/random", {
            "query": query,
            "count": min(int(count), 30),
            "orientation": orientation,
            "content_filter": content_filter,
        })
        return data if isinstance(data, list) else [data]

    def get_photo(self, photo_id):
        return self._get(f"/photos/{photo_id}")

    def track_download(self, photo):
        """Required by the Unsplash API guidelines whenever a photo is downloaded/used."""
        location = photo["links"]["download_location"]
        path = urllib.parse.urlsplit(location)
        self._get(path.path, dict(urllib.parse.parse_qsl(path.query)))

    def download(self, photo, dest_dir, size="full", width=None, height=None):
        """Download one photo to dest_dir and return the saved Path.

        width/height (optional) use Unsplash's imgix params on the raw URL, e.g.
        width=1920, height=1080 for a 1080p video frame.
        """
        if size not in SIZES:
            raise ValueError(f"size must be one of {SIZES}")
        self.track_download(photo)

        if width or height:
            url = _with_params(photo["urls"]["raw"], {
                "w": width, "h": height, "fit": "crop", "crop": "entropy", "fm": "jpg", "q": 85,
            })
        else:
            url = photo["urls"][size]

        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        slug = _slugify(photo.get("alt_description") or photo.get("description") or "")
        name = f"{photo['id']}-{slug}.jpg" if slug else f"{photo['id']}.jpg"
        out = dest_dir / name
        with urllib.request.urlopen(url, timeout=self.timeout) as resp, open(out, "wb") as f:
            f.write(resp.read())
        return out


# -- Attribution ----------------------------------------------------------------

def attribution(photo):
    """Credit info Unsplash asks you to show (e.g. in the video description/end card)."""
    utm = f"utm_source={APP_NAME}&utm_medium=referral"
    user = photo["user"]
    return {
        "id": photo["id"],
        "photographer": user["name"],
        "photographer_url": f"{user['links']['html']}?{utm}",
        "photo_url": f"{photo['links']['html']}?{utm}",
        "unsplash_url": f"https://unsplash.com/?{utm}",
        "text": f"Photo by {user['name']} on Unsplash",
        "description": photo.get("alt_description") or photo.get("description"),
        "width": photo.get("width"),
        "height": photo.get("height"),
    }


def _with_params(url, params):
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query))
    query.update({k: str(v) for k, v in params.items() if v is not None})
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def _slugify(text, max_len=40):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len].rstrip("-")
