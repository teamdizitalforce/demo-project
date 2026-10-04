#!/usr/bin/env python3
"""Grab Unsplash photos for a video scene.

Examples:
  python tools/unsplash/grab_unsplash.py "sunset beach" --count 5
  python tools/unsplash/grab_unsplash.py "city night" --count 8 --orientation portrait --width 1080 --height 1920
  python tools/unsplash/grab_unsplash.py "coffee" --random --count 3 --out assets/scene2

Writes the images plus credits.json / credits.txt (attribution for your video description).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from unsplash_client import SIZES, UnsplashClient, UnsplashError, attribution  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description="Download Unsplash photos for video scenes.")
    p.add_argument("query", help="What to search for, e.g. 'mountain sunrise'")
    p.add_argument("--count", type=int, default=5, help="How many photos (max 30)")
    p.add_argument("--orientation", choices=["landscape", "portrait", "squarish"], default="landscape",
                   help="landscape for 16:9 videos, portrait for Reels/Shorts/TikTok")
    p.add_argument("--size", choices=SIZES, default="full")
    p.add_argument("--width", type=int, help="Crop/resize to this width (e.g. 1920)")
    p.add_argument("--height", type=int, help="Crop/resize to this height (e.g. 1080)")
    p.add_argument("--color", help="Filter by color: black_and_white, black, white, yellow, orange, red, "
                                   "purple, magenta, green, teal, blue")
    p.add_argument("--random", action="store_true", help="Random matching photos instead of top results")
    p.add_argument("--out", default="assets/unsplash", help="Output folder")
    args = p.parse_args(argv)

    try:
        client = UnsplashClient()
        if args.random:
            photos = client.random_photos(query=args.query, count=args.count, orientation=args.orientation)
        else:
            photos = client.search_photos(args.query, per_page=args.count, orientation=args.orientation,
                                          color=args.color)
    except UnsplashError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not photos:
        print(f"No photos found for '{args.query}'.", file=sys.stderr)
        return 1

    out = Path(args.out)
    credits = []
    for photo in photos[: args.count]:
        path = client.download(photo, out, size=args.size, width=args.width, height=args.height)
        credit = attribution(photo)
        credit["file"] = path.name
        credits.append(credit)
        print(f"Saved {path}  ({credit['text']})")

    (out / "credits.json").write_text(json.dumps(credits, indent=2))
    (out / "credits.txt").write_text("\n".join(f"{c['text']}: {c['photo_url']}" for c in credits) + "\n")
    print(f"\n{len(credits)} photo(s) saved to {out}/ — credits in {out}/credits.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
