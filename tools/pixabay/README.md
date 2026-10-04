# Pixabay stock video grabber

Downloads royalty-free **stock videos** (and images) from the [Pixabay API](https://pixabay.com/api/docs/) for your video projects.
It needs only Python 3.8 or newer and no extra packages.

## Setup

```bash
cp tools/pixabay/.env.example tools/pixabay/.env
# edit tools/pixabay/.env -> PIXABAY_API_KEY=...
```
Your key is shown on https://pixabay.com/api/docs/ while you're logged in. You can also export `PIXABAY_API_KEY`.
`.env` is gitignored. Never commit your key.

## Usage

```bash
# 5 stock clips, ~1080p (default "medium" rendition)
python tools/pixabay/grab_pixabay.py "ocean waves" --count 5

# Vertical clips for Reels / Shorts / TikTok, in 4K where available
python tools/pixabay/grab_pixabay.py "city night" --count 4 --orientation portrait --size large

# Short clips only, from a category, into a scene folder
python tools/pixabay/grab_pixabay.py "coffee" --max-duration 15 --category food --out assets/scene2

# Images instead of videos
python tools/pixabay/grab_pixabay.py "mountains" --images --count 6 --orientation landscape
```

### Video sizes (`--size`)
| Size | Typical resolution | Notes |
|---|---|---|
| `large` | 3840×2160 (4K) | Not every clip has it. The tool falls back to `medium` automatically. |
| `medium` | 1920×1080 | Every clip has it. This is the default. |
| `small` | 1280×720 | |
| `tiny` | 960×540 | |

Other filters are `--min-duration`, `--max-duration`, `--video-type film|animation`, `--category`, `--min-width`, `--min-height`, `--order latest` and `--editors-choice`.
The Pixabay API has no orientation or duration filters for videos, so the tool fetches extra results and filters them itself.

Each run saves:
- the files (`pixabay-<id>-<tags>-<WxH>.mp4`)
- `credits.json` and `credits.txt`. Pixabay asks you to show where the media came from, so paste these into your video description.

### From Python

```python
from pixabay_client import PixabayClient, attribution

client = PixabayClient()  # reads PIXABAY_API_KEY
for clip in client.search_videos("forest drone", per_page=5, min_width=1920):
    path = client.download_video(clip, "assets/scene1", size="medium")
    print(path, clip["duration"], "s —", attribution(clip)["text"])
```

### Stitch clips into one video (ffmpeg)

```bash
cd assets/pixabay/videos
for f in *.mp4; do
  ffmpeg -y -i "$f" -vf "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30" \
    -an -c:v libx264 -pix_fmt yuv420p "norm_$f"
done
ls norm_*.mp4 | sed "s/.*/file '&'/" > list.txt
ffmpeg -f concat -safe 0 -i list.txt -c copy stitched.mp4
```

## Pixabay API rules this tool follows

- **Caching:** API responses are cached for 24 hours in `tools/pixabay/.cache/`, as Pixabay requires. Repeat searches don't use up your rate limit.
- **Rate limit:** 100 requests per 60 seconds. A 429 error comes back with a clear message, and the CLI prints how many requests you have left.
- **No hotlinking:** files are downloaded locally instead of linking to Pixabay URLs.
- **Attribution:** credits link to the clip page and the creator's profile.
- **No mass downloading:** Pixabay doesn't allow systematic bulk downloads, so only fetch what you need for a project.

## Tests

```bash
python3 -m unittest discover -s tools/pixabay/tests -v
```
