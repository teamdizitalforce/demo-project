# Unsplash photo grabber

Pulls stock photos from the [Unsplash API](https://unsplash.com/documentation) so you can use them in videos.
It needs only Python 3.8 or newer and no extra packages.

> Unsplash serves **photos only, not video clips**. For stock video footage, use the Pexels or Pixabay APIs.

## Setup

1. Copy the example env file and add your **Access Key**:
   ```bash
   cp tools/unsplash/.env.example tools/unsplash/.env
   # edit tools/unsplash/.env -> UNSPLASH_ACCESS_KEY=...
   ```
   You can also export `UNSPLASH_ACCESS_KEY` in your shell or CI secrets.
   `.env` is gitignored. Never commit your keys. This tool doesn't use the Secret Key.

## Usage

```bash
# 5 landscape photos (16:9 videos)
python tools/unsplash/grab_unsplash.py "sunset beach" --count 5

# Vertical 1080x1920 frames for Reels / Shorts / TikTok
python tools/unsplash/grab_unsplash.py "city night" --count 8 --orientation portrait --width 1080 --height 1920

# Exact 1080p frames, random picks, custom folder
python tools/unsplash/grab_unsplash.py "coffee" --random --count 3 --width 1920 --height 1080 --out assets/scene2
```

Each run saves:
- the images (`<id>-<description>.jpg`)
- `credits.json` and `credits.txt`, which hold the photographer credits. Paste these into your video description or end card.

### From Python

```python
from unsplash_client import UnsplashClient, attribution

client = UnsplashClient()  # reads UNSPLASH_ACCESS_KEY
for photo in client.search_photos("mountain sunrise", per_page=3, orientation="landscape"):
    path = client.download(photo, "assets/scene1", width=1920, height=1080)
    print(path, attribution(photo)["text"])
```

### Turn photos into a quick slideshow video (ffmpeg)

```bash
ffmpeg -framerate 1/3 -pattern_type glob -i 'assets/unsplash/*.jpg' \
  -vf "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=yuv420p" \
  -r 30 -c:v libx264 slideshow.mp4
```

## Unsplash API rules this tool follows

- **Download tracking:** each download hits the photo's `download_location`, as the API guidelines require.
- **Hotlinking:** image URLs come from `photo.urls`, and resizing uses Unsplash's own URL parameters.
- **Attribution:** credits include `utm_source=<app>&utm_medium=referral` links.
- **Rate limit:** demo apps get 50 requests/hour. Apply for production on your Unsplash dashboard to get 5,000/hour.
  Each photo costs 2 requests: one for the search and one for download tracking.

## Tests

```bash
python3 -m unittest discover -s tools/unsplash/tests -v
```
