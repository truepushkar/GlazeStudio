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

## Standalone (no backend)

The whole editor runs client-side, so you can host the `static/` folder
on any static host (GitHub Pages, Netlify, S3, or just open
`static/index.html` directly):

```bash
cd static && python -m http.server 8000   # or deploy the folder as-is
```

Upload, paste, drag-drop, all styling, the bundled wallpapers, and PNG/WebM
export work without a server. **Post import by URL** is the only feature
that needs `app.py` running (it proxies post data and images); without the
backend the app says so and everything else keeps working.

## Features

**Input** — upload, drag-drop, paste (Ctrl+V), or import by URL.

**Import by URL**

Paste a link to a supported post and it renders as a clean card; paste **any
other URL** and Glaze captures a full screenshot of that page instead.

| Source | Method | Reliability |
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
| **Any website** | Screenshot (thum.io → mShots fallback) | Good; sites that block bots may fail |

Supported posts render as a card (light/dark theme) drawn on canvas; a plain
website drops in as its screenshot, ready to style like any upload.

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
