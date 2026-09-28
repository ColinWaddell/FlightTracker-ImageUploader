# FlightTracker-ImageUploader

Command-line client that pushes images to the
[FlightTracker](https://github.com/ColinWaddell/FlightTracker) LED panel
(64x32 RGB matrix) over its Image Upload API.

```
./image_uploader.py photo.jpg
./image_uploader.py --frame-ms 160 --loops 3 anim.gif
./image_uploader.py --test
```

Any format Pillow can read works — PNG, JPEG, WebP, GIF, BMP, TIFF...
Still images are sent as a single frame; animated GIF/WebP files are sent
as multi-frame animations that play on the panel until they have played
through the requested number of loops. Screen time is always
`frames × frame_ms × loops`.

## How it works

1. The image is converted to raw RGB — exactly **6144 bytes** per frame
   (64 x 32 x 3), base64-encoded (~8192 characters).
2. The uploader POSTs a JSON payload to `POST /api/image` with your key in
   the `X-API-Key` header:

   ```json
   {
     "data": ["<base64 frame>", "<base64 frame>"],
     "loops": 3,
     "frame_ms": 160
   }
   ```

   - `data` — one entry per frame (1 – 60 frames); longer animations are
     sampled evenly down to the cap
   - `loops` — optional number of play-throughs (default 1)
   - `frame_ms` — optional, ms each frame is held (default 500; animated
     sources use their own frame duration when available). The panel
     animates at a fixed rate (12.5 fps / 80 ms per frame at default
     display speed), so ms values are rounded to whole refresh cycles —
     the API response reports the effective hold

   The image stays on screen for `frames × frame_ms × loops`, then the
   panel returns to its normal display.

3. The panel drops whatever it is showing and displays the image
   immediately. Submissions are held in the tracker's memory only — they
   are lost on restart.

## Setup

**Requirements:** Python 3.9+ and
[Pillow](https://pypi.org/project/pillow/). There are no other
dependencies — HTTP is handled by the standard library.

Clone the repo and set up a virtual environment:

```bash
git clone https://github.com/ColinWaddell/FlightTracker-ImageUploader.git
cd FlightTracker-ImageUploader
python3 -m venv .venv
source .venv/bin/activate
pip install pillow
```

To use the uploader later without activating the venv first:

```bash
.venv/bin/python image_uploader.py photo.jpg
```

**Flight Tracker address:** by default the uploader talks to
`http://fivepi.local:8584`. Point it at your own tracker with `--url` or
the `FT_IMAGE_URL` environment variable.

**API key:** generate one in the Flight Tracker web UI under
**Data Source → Image Upload API → Generate Key** (you can view the
current key there any time; generating a new key revokes the old one).
Give the key to this script once and let it remember:

```bash
./image_uploader.py --key 'your-key-here' --remember-key
```

The key is stored at `~/.config/ft-image-upload/api_key` (mode 600). You
can instead pass it per-run with `--key`, keep it in a file and point at
it with `--key-file`, or export it as `FT_IMAGE_API_KEY`.

## Examples

```bash
# Show a photo — held for the default 5 minutes (--ttl 300)
./image_uploader.py holiday.jpg

# Loop a GIF at 160ms per frame (2 panel refresh cycles), three
# play-throughs, then clear
./image_uploader.py --frame-ms 160 --loops 3 anim.gif

# Play a GIF exactly once at its own embedded frame timing, then clear
./image_uploader.py --loops 1 dance.gif

# Letterbox a screenshot instead of cropping (held for the default 5 minutes)
./image_uploader.py --fit contain screenshot.png

# Convenience: keep an image up for ~10 minutes — --ttl is a client-side
# target that gets converted to frame_ms/loops (the API itself takes no ttl)
./image_uploader.py --ttl 600 holiday.jpg

# Quick sanity check (colour bars, 20 seconds)
./image_uploader.py --test --ttl 20

# Talk to a tracker at a specific address
./image_uploader.py --url http://mytracker.local:8584 pic.jpg
```

## Command-line options

| Flag | Meaning | Default |
|---|---|---|
| `--url` | Flight Tracker base URL | `$FT_IMAGE_URL` or `http://fivepi.local:8584` |
| `--key` | API key inline | - |
| `--key-file` | File containing the API key | - |
| `--remember-key` | Store the provided key for future runs | - |
| `--frame-ms` | ms each frame is held (alias: `--frame-delay`) | source timing for animations; `--ttl`-derived hold for stills |
| `--loops` | Animation play-throughs (0 = derive from `--ttl`) | 0 |
| `--ttl` | Convenience: target seconds on screen, converted client-side to `frame_ms`/`loops` — the API itself takes no ttl | 300 |
| `--fit` | `cover` (fill + crop) or `contain` (fit + letterbox) | cover |
| `--max-frames` | Animation frame cap (API maximum is 60) | 60 |
| `--test` | Push a built-in colour-bars test pattern | - |

The key is resolved in this order: `--key`, then `$FT_IMAGE_API_KEY`,
then `--key-file`, then the default key file
(`~/.config/ft-image-upload/api_key`).

## Environment variables

| Variable | Purpose |
|---|---|
| `FT_IMAGE_URL` | Default Flight Tracker base URL |
| `FT_IMAGE_API_KEY` | Default API key |

## Fit modes

- `cover` (default) — scales the image until it fills the whole panel,
  then centre-crops the overflow. Best for photos on a panel whose aspect
  ratio differs from the image.
- `contain` — scales the image to fit entirely inside the panel and pads
  the remainder with black. Keeps the whole image visible.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Uploaded successfully |
| 1 | API/HTTP error (the tracker's message is shown) |
| 2 | Local error: missing image, bad options, no key |
| 3 | Could not reach the tracker |

## Troubleshooting

- **403 "no API key has been generated"** — no key exists on the tracker
  yet, or it was revoked. Generate one in the web UI and re-provision the
  client (`--remember-key`).
- **401 "Invalid or missing API key"** — the key this client sends doesn't
  match the one the tracker expects. Re-provision it as above.
- **Host name doesn't resolve** — pass the tracker's IP address directly
  with `--url http://<ip>:8584`.
- **Image clears earlier than expected** — screen time is
  `frames × frame_ms × loops` and the image yields as soon as its loops
  complete. Pin `--loops`, or give a total like `--ttl 600` and let the
  uploader derive the loop count. Note a pinned `--loops` ignores
  `--ttl`.

## See also

- [FlightTracker](https://github.com/ColinWaddell/FlightTracker) — the LED
  panel flight tracker this client talks to. The Image Upload API is built
  into it; keys are managed in its web UI on the Data Source page.