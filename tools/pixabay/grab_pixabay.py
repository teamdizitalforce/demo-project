#!/usr/bin/env python3
"""Grab Pixabay stock videos (or images) for a video project.

Examples:
  python tools/pixabay/grab_pixabay.py "ocean waves" --count 5
  python tools/pixabay/grab_pixabay.py "city night" --count 4 --orientation portrait --size large
  python tools/pixabay/grab_pixabay.py "coffee" --max-duration 15 --category food --out assets/scene2
  python tools/pixabay/grab_pixabay.py "mountains" --images --count 6 --orientation landscape

Writes the files plus credits.json / credits.txt (attribution for your video description).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pixabay_client import (  # noqa: E402
    CATEGORIES, VIDEO_SIZES, PixabayClient, PixabayError, attribution, orientation_of, pick_rendition,
)


def main(argv=None):
    p = argparse.ArgumentParser(description="Download Pixabay stock videos or images.")
    p.add_argument("query", help="What to search for, e.g. 'ocean waves'")
    p.add_argument("--count", type=int, default=5, help="How many files to download")
    p.add_argument("--images", action="store_true", help="Download images instead of videos")
    p.add_argument("--orientation", choices=["any", "landscape", "portrait"], default="any",
                   help="landscape for 16:9 videos, portrait for Reels/Shorts/TikTok")
    p.add_argument("--size", choices=VIDEO_SIZES, default="medium",
                   help="Video rendition: large (~4K), medium (~1080p), small (~720p), tiny (~540p)")
    p.add_argument("--min-duration", type=int, help="Minimum clip length in seconds")
    p.add_argument("--max-duration", type=int, help="Maximum clip length in seconds")
    p.add_argument("--video-type", choices=["all", "film", "animation"], default="all")
    p.add_argument("--category", choices=CATEGORIES)
    p.add_argument("--min-width", type=int)
    p.add_argument("--min-height", type=int)
    p.add_argument("--order", choices=["popular", "latest"], default="popular")
    p.add_argument("--editors-choice", action="store_true")
    p.add_argument("--no-safesearch", action="store_true")
    p.add_argument("--out", default=None, help="Output folder (default assets/pixabay/videos or /images)")
    args = p.parse_args(argv)

    out = Path(args.out or f"assets/pixabay/{'images' if args.images else 'videos'}")
    try:
        client = PixabayClient()
        if args.images:
            items = _find_images(client, args)
        else:
            items = _find_videos(client, args)
    except PixabayError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not items:
        print(f"No {'images' if args.images else 'videos'} found for '{args.query}'.", file=sys.stderr)
        return 1

    credits = []
    for item in items:
        try:
            if args.images:
                path = client.download_image(item, out)
            else:
                path = client.download_video(item, out, size=args.size)
        except Exception as e:  # keep going if one file fails
            print(f"Skipped {item['id']}: {e}", file=sys.stderr)
            continue
        credit = attribution(item, "image" if args.images else "video")
        credit["file"] = path.name
        credits.append(credit)
        extra = f", {item['duration']}s" if not args.images else ""
        print(f"Saved {path}  ({credit['text']}{extra})")

    if not credits:
        return 1
    (out / "credits.json").write_text(json.dumps(credits, indent=2))
    (out / "credits.txt").write_text("\n".join(f"{c['text']}: {c['source_url']}" for c in credits) + "\n")
    print(f"\n{len(credits)} file(s) saved to {out}/ — credits in {out}/credits.txt")
    if client.rate_limit.get("remaining"):
        print(f"Pixabay requests left this minute: {client.rate_limit['remaining']}")
    return 0


def _find_videos(client, args):
    # Orientation and duration aren't API filters for videos, so fetch extra and filter here.
    want_filter = args.orientation != "any" or args.min_duration or args.max_duration
    hits = client.search_videos(
        args.query,
        per_page=min(200, args.count * 4) if want_filter else args.count,
        video_type=args.video_type,
        category=args.category,
        min_width=args.min_width,
        min_height=args.min_height,
        editors_choice=args.editors_choice,
        safesearch=not args.no_safesearch,
        order=args.order,
    )
    picked = []
    for v in hits:
        if args.orientation != "any" and orientation_of(v) != args.orientation:
            continue
        if args.min_duration and v.get("duration", 0) < args.min_duration:
            continue
        if args.max_duration and v.get("duration", 0) > args.max_duration:
            continue
        try:
            pick_rendition(v, args.size)
        except PixabayError:
            continue
        picked.append(v)
        if len(picked) == args.count:
            break
    return picked


def _find_images(client, args):
    orientation = {"any": "all", "landscape": "horizontal", "portrait": "vertical"}[args.orientation]
    hits = client.search_images(
        args.query,
        per_page=args.count,
        orientation=orientation,
        category=args.category,
        min_width=args.min_width,
        min_height=args.min_height,
        editors_choice=args.editors_choice,
        safesearch=not args.no_safesearch,
        order=args.order,
    )
    return hits[: args.count]


if __name__ == "__main__":
    sys.exit(main())
