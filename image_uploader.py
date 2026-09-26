#!/usr/bin/env python3
"""
ft-image-upload - send images to the FlightTracker LED panel.

Converts any image (PNG, JPEG, GIF, WebP, ...) into raw RGB frames for
the 64x32 panel, base64-encodes them, and POSTs them to the Flight
Tracker Image Upload API (POST /api/image).  Animated GIF/WebP images
are sent as multi-frame animations; still images become a single frame.

Requires Pillow:  pip install pillow

Usage:
  image_uploader.py photo.jpg
  image_uploader.py --ttl 60 animation.gif
  image_uploader.py --test                      # push a built-in test pattern
  image_uploader.py --url http://10.0.0.55:8584 --key-file ./key pic.png

Key resolution order:  --key  >  $FT_IMAGE_API_KEY  >  --key-file  >
~/.config/ft-image-upload/api_key (written by --remember-key).
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    from PIL import Image, ImageSequence
except ImportError:  # pragma: no cover - import-time guard
    print("Pillow is required:  pip install pillow", file=sys.stderr)
    sys.exit(2)

PANEL_W, PANEL_H = 64, 32
FRAME_BYTES = PANEL_W * PANEL_H * 3
MAX_FRAMES = 60
DEFAULT_URL = "http://fivepi.local:8584"
DEFAULT_KEY_FILE = Path.home() / ".config/ft-image-upload/api_key"


# ---------------------------------------------------------------------------
# Image conversion
# ---------------------------------------------------------------------------


def to_frame_bytes(img: Image.Image, fit: str) -> bytes:
    """Resize/crop an image to exactly PANEL_W x PANEL_H raw RGB bytes."""
    rgb = img.convert("RGB")
    if fit == "cover":
        # Scale so the image covers the panel, centre-crop the overflow.
        scale = max(PANEL_W / rgb.width, PANEL_H / rgb.height)
        scaled = rgb.resize(
            (max(1, math.ceil(rgb.width * scale)), max(1, math.ceil(rgb.height * scale))),
            Image.LANCZOS,
        )
        left = (scaled.width - PANEL_W) // 2
        top = (scaled.height - PANEL_H) // 2
        frame = scaled.crop((left, top, left + PANEL_W, top + PANEL_H))
    else:  # contain
        # Scale to fit inside the panel, pad the remainder with black.
        scale = min(PANEL_W / rgb.width, PANEL_H / rgb.height)
        scaled = rgb.resize(
            (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))),
            Image.LANCZOS,
        )
        frame = Image.new("RGB", (PANEL_W, PANEL_H), (0, 0, 0))
        frame.paste(
            scaled,
            ((PANEL_W - scaled.width) // 2, (PANEL_H - scaled.height) // 2),
        )
    return frame.tobytes()


def load_frames(path: Path, fit: str, max_frames: int):
    """Return (frames, suggested_frame_ms) from an image file."""
    with Image.open(path) as img:
        n_frames = getattr(img, "n_frames", 1)
        gif_delay = img.info.get("duration")  # ms, if the format supplies one

        if n_frames <= 1:
            return [to_frame_bytes(img, fit)], None

        # Sample evenly if the animation has more frames than the API allows.
        count = min(n_frames, max_frames)
        step = n_frames / count
        frames = []
        for i in range(count):
            img.seek(round(i * step))
            frames.append(to_frame_bytes(img, fit))
        return frames, img.info.get("duration")


def test_pattern() -> bytes:
    """Vertical colour bars with a white border - an unambiguous test card."""
    colours = [
        (255, 255, 255),
        (255, 255, 0),
        (0, 255, 255),
        (0, 255, 0),
        (255, 0, 255),
        (255, 0, 0),
        (0, 0, 255),
        (0, 0, 0),
    ]
    bar_w = PANEL_W // len(colours)
    frame = Image.new("RGB", (PANEL_W, PANEL_H))
    pixels = frame.load()
    for x in range(PANEL_W):
        colour = colours[min(x // bar_w, len(colours) - 1)]
        for y in range(PANEL_H):
            pixels[x, y] = colour
    # White border so it is obvious the whole panel is being addressed.
    for x in range(PANEL_W):
        pixels[x, 0] = pixels[x, PANEL_H - 1] = (255, 255, 255)
    for y in range(PANEL_H):
        pixels[0, y] = pixels[PANEL_W - 1, y] = (255, 255, 255)
    return frame.tobytes()


# ---------------------------------------------------------------------------
# API transport
# ---------------------------------------------------------------------------


def resolve_key(args) -> str:
    if args.key:
        return args.key
    env = os.environ.get("FT_IMAGE_API_KEY", "")
    if env:
        return env
    key_file = Path(args.key_file) if args.key_file else DEFAULT_KEY_FILE
    if key_file.is_file():
        key = key_file.read_text().strip()
        if key:
            return key
    print(
        "No API key found. Generate one in the web UI (Data Source > "
        "Image Upload API), then pass it via --key, $FT_IMAGE_API_KEY, "
        "--key-file, or --remember-key.",
        file=sys.stderr,
    )
    sys.exit(2)


def post_image(url: str, key: str, payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        url.rstrip("/") + "/api/image",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get("error", "")
        except (ValueError, OSError):
            detail = exc.reason
        print(f"API error {exc.code}: {detail}", file=sys.stderr)
        sys.exit(1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Could not reach {url}: {exc.reason}", file=sys.stderr)
        sys.exit(3)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Send images to the FlightTracker LED panel."
    )
    parser.add_argument("image", nargs="?", help="image file to send")
    parser.add_argument(
        "--url",
        default=os.environ.get("FT_IMAGE_URL", DEFAULT_URL),
        help="Flight Tracker base URL (default: %(default)s)",
    )
    parser.add_argument("--key", help="API key (otherwise see key resolution order)")
    parser.add_argument("--key-file", help="file containing the API key")
    parser.add_argument(
        "--remember-key",
        action="store_true",
        help="store --key (or the key from --key-file) in the default key file",
    )
    parser.add_argument(
        "--ttl",
        type=int,
        default=300,
        help=(
            "seconds the image should stay on screen (default: %(default)s); "
            "converted to frame_ms/loops for the API"
        ),
    )
    parser.add_argument(
        "--loops",
        type=int,
        default=0,
        help="animation play-throughs (default: derived from --ttl; 1-100000)",
    )
    parser.add_argument(
        "--frame-ms",
        "--frame-delay",
        dest="frame_ms",
        type=int,
        default=None,
        help=(
            "ms each frame is held (default: source timing for animations, "
            "--ttl for stills)"
        ),
    )
    parser.add_argument(
        "--fit",
        choices=("cover", "contain"),
        default="cover",
        help="cover: fill panel and crop (default); contain: fit and letterbox",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=MAX_FRAMES,
        help=f"animation frames cap (API allows {MAX_FRAMES})",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="push a built-in test pattern instead of an image file",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)

    if args.max_frames > MAX_FRAMES:
        print(f"--max-frames is capped at {MAX_FRAMES}", file=sys.stderr)
        sys.exit(2)
    if not args.test and not args.image:
        print("an image file (or --test) is required", file=sys.stderr)
        sys.exit(2)

    key = resolve_key(args)
    if args.remember_key:
        DEFAULT_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_KEY_FILE.write_text(key + "\n")
        DEFAULT_KEY_FILE.chmod(0o600)
        print(f"Key saved to {DEFAULT_KEY_FILE}")

    if args.test:
        frames = [test_pattern()]
        source_delay = None
    else:
        frames, source_delay = load_frames(
            Path(args.image), args.fit, args.max_frames
        )

    if args.frame_ms is not None:
        frame_ms = args.frame_ms
    elif len(frames) > 1 and source_delay:
        frame_ms = max(10, int(source_delay))
    else:
        # Still image with no explicit timing: hold it for --ttl.
        frame_ms = max(10, min(60000, args.ttl * 1000))

    frame_ms = max(10, min(60000, frame_ms))

    # Screen time is frames x frame_ms x loops.  Derive loops from
    # --ttl unless the caller pinned it with --loops; ceil so the image
    # never leaves the screen early.
    total_ms = args.ttl * 1000
    per_loop_ms = len(frames) * frame_ms
    if args.loops > 0:
        loops = args.loops
    else:
        loops = max(1, math.ceil(total_ms / per_loop_ms))

    payload = {
        "data": [base64.b64encode(f).decode() for f in frames],
        "frame_ms": frame_ms,
        "loops": loops,
    }

    status, response = post_image(args.url, key, payload)
    if response.get("status") == "ok":
        effective = response.get("effective_frame_ms", frame_ms)
        on_screen_s = effective * len(frames) * loops / 1000
        details = (
            f"{response['frames']} frame(s), ~{on_screen_s:.0f}s on screen, "
            f"hold {effective}ms ({response.get('frame_hold')} panel frames), "
            f"loops {loops}"
        )
        print(f"Uploaded ({status}): {details}")
    else:
        print(f"Unexpected response: {response}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()