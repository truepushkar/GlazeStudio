# Glaze — Screenshot Studio

A CleanShot X–style screenshot beautifier with social post import,
wrapped in a glass UI with light/dark mode.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

Optional: `export GITHUB_TOKEN=ghp_...` raises the GitHub rate limit
from 60 to 5,000 requests/hour.

## Features

**Input** — upload, drag-drop, paste (Ctrl+V), or import a post by URL.

**Post import (9 platforms)**

| Platform | Method | Reliability |
|---|---|---|
| X / Twitter | Public syndication endpoint | Good for public posts |
| Bluesky | Public AT Protocol API | Very good |
| Reddit | Public `.json` API | Very good; may rate-limit |
| Mastodon | Public status API (any instance) | Very good for public posts |
| YouTube | oEmbed + thumbnail endpoints | Very good |
| TikTok | oEmbed | Good (use full video links) |
| GitHub | REST API (repo cards) | Good; 60 req/hr unauthenticated |
| Instagram | OpenGraph scrape (best effort) | Spotty — IG blocks most anonymous access |
| Threads | OpenGraph scrape (best effort) | Spotty — same as Instagram |

Each post renders as a clean card (light/dark theme) drawn on canvas.

**Backgrounds** — 11 presets, transparent, custom 2-color gradient maker
(linear/radial + angle), or upload your own image (cover-fit).

**Animation** — Drift, Hue shift, or Breathe styles; export a 4-second
WebM loop.

**Geometry** — padding, size, corner radius, rotation (±15°), shadow,
border width + color.

**Frames** — macOS light/dark (traffic lights), Windows light/dark
(caption buttons).

**Finishes** — film grain, vignette, glass glare, custom watermark text.

**Export** — PNG at 1×/2×/3×, copy to clipboard, or animated WebM.

## Notes

- Everything renders client-side on `<canvas>`; the server only fetches post data.
- Post images are proxied through `/api/img` (with an SSRF guard) so exports stay un-tainted.
- Be a good citizen: this makes share-cards of public posts; heavy automated use will get you rate-limited by these platforms.
