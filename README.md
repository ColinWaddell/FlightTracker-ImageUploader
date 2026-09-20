# FlightTracker-ImageUploader

Push images to the [FlightTracker](https://github.com/ColinWaddell/FlightTracker)
LED panel (64x32 RGB matrix) from the command line, via its Image Upload API.

```
./image_uploader.py photo.jpg
./image_uploader.py --ttl 60 --loops 3 anim.gif
./image_uploader.py --test
```

Any format Pillow reads works — PNG, JPEG, WebP, GIF, BMP, TIFF...
Still images are sent as a single frame; animated GIF/WebP files are sent as
multi-frame animations. Frames are scaled to the panel: `--fit cover`
(default) fills the panel and centre-crops the overflow; `--fit contain`
fits inside and letterboxes with black.

## How it works

1. The image is converted to raw RGB — exactly **6144 bytes** per frame
   (64 x 32 x 3), base64-encoded (~8192 chars).
2. The uploader POSTs a JSON payload to `POST /api/image` with your key in
   the `X-API-Key` header:

   ```json
   {
     "ttl": 300,
     "data": ["<base64 frame>", "<base64 frame>"],
     "loops": 3,
     "frame_delay": 150
   }
   ```

   - `ttl` — required, seconds the image stays on screen (1 – 86400)
   - `data` — one entry per frame (1 – 60 frames); longer animations are
     sampled evenly down to the cap
   - `loops` — optional play-throughs; omit to loop until the TTL expires
   - `frame_delay` — optional ms between frames (default 500; animations
     use the source's own duration when available)

3. The panel drops whatever it is showing and displays the image immediately.
   Images live in the tracker's memory only — they are lost on restart.

## The API key

Generate or revoke the key in the Flight Tracker web UI:
**Data Source → Image Upload API**. Only a SHA-256 hash of the key is
stored server-side; generating a new key revokes the old one.

This script resolves the key in this order:

1. `--key`
2. `$FT_IMAGE_API_KEY`
3. `--key-file`
4. `~/.config/ft-image-upload/api_key` (default; written by `--remember-key`)

The key is already provisioned on this machine at the default path. If you
regenerate it in the web UI, update it here in one step:

```
./image_uploader.py --key 'the-new-key' --remember-key
```

## Options

| Flag | Meaning | Default |
|---|---|---|
| `--url` | Flight Tracker base URL | `$FT_IMAGE_URL` or `http://fivepi.local:8584` |
| `--key` | API key inline | - |
| `--key-file` | File containing the API key | - |
| `--remember-key` | Store the provided key in the default key file | - |
| `--ttl` | Seconds the image stays on screen | 300 |
| `--loops` | Animation play-throughs (0 = loop until TTL) | 0 |
| `--frame-delay` | ms between animation frames | source duration or 500 |
| `--fit` | `cover` (fill + crop) or `contain` (fit + letterbox) | cover |
| `--max-frames` | Animation frame cap (API maximum is 60) | 60 |
| `--test` | Push a built-in colour-bars test pattern | - |

## Environment

| Variable | Purpose |
|---|---|
| `FT_IMAGE_URL` | Default Flight Tracker base URL |
| `FT_IMAGE_API_KEY` | Default API key |

## Examples

```bash
# Show a photo for the default 5 minutes
./image_uploader.py holiday.jpg

# Letterboxed instead of cropped, 10 minutes
./image_uploader.py --fit contain --ttl 600 screenshot.png

# Loop a GIF until its TTL expires, 150ms per frame
./image_uploader.py --ttl 120 --frame-delay 150 dance.gif

# Play a GIF exactly twice, then clear
./image_uploader.py --ttl 120 --loops 2 dance.gif

# Quick sanity check (colour bars, 20 seconds)
./image_uploader.py --test --ttl 20

# Talk to a tracker at a specific address
./image_uploader.py --url http://10.0.0.55:8584 pic.jpg
```

## Requirements

- Python 3 (tested on 3.13) with [Pillow](https://pypi.org/project/pillow/)
  — already installed system-wide on this machine
- No other dependencies: HTTP is stdlib `urllib`

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Uploaded successfully |
| 1 | API/HTTP error (message from the tracker is shown) |
| 2 | Local error: missing image, bad options, no key |
| 3 | Could not reach the tracker |

## Troubleshooting

- **403 "no API key has been generated"** — the key was revoked or never
  generated. Generate one in the web UI and update the local copy
  (`--remember-key`).
- **401 "Invalid or missing API key"** — the stored key doesn't match;
  re-provision it as above.
- **fivepi.local doesn't resolve** — use the Pi's IP directly
  (`--url http://<ip>:8584`).
- The panel keeps showing the old image — check you didn't set `--loops`
  higher than intended; the image yields early only when all loops
  complete, otherwise it holds until the TTL passes.