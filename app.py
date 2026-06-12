"""
Glaze Studio — Flask backend
Fetches public post data from X, Reddit, Instagram, Bluesky, YouTube,
TikTok, GitHub, Mastodon, and Threads; proxies images so canvas export
stays un-tainted.

Run:  pip install -r requirements.txt && python app.py
Then open http://localhost:5000
"""
import html as html_mod
import ipaddress
import math
import os
import re
import socket
from urllib.parse import quote, urlparse

import requests
from flask import Flask, Response, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static")

WALLPAPER_DIR = os.path.join(app.static_folder, "wallpaper")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

BROWSER_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
PLAIN_UA = {"User-Agent": "glaze-studio/2.0 (screenshot beautifier)"}
TIMEOUT = 12


class PostError(Exception):
    pass


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def home():
    return send_from_directory("static", "index.html")


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


@app.route("/wallpapers.json")
def list_wallpapers():
    try:
        files = sorted(
            (f for f in os.listdir(WALLPAPER_DIR) if f.lower().endswith(IMAGE_EXTS)),
            key=_natural_key,
        )
    except OSError:
        files = []
    return jsonify([{"id": os.path.splitext(f)[0], "url": f"wallpaper/{f}"} for f in files])


@app.route("/wallpaper/<path:filename>")
def serve_wallpaper(filename):
    return send_from_directory(WALLPAPER_DIR, filename)


@app.route("/api/fetch")
def fetch_post():
    url = (request.args.get("url") or "").strip()
    if not url:
        return jsonify({"error": "No URL provided."}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    host = (urlparse(url).hostname or "").lower().removeprefix("www.").removeprefix("m.")
    try:
        if host in ("x.com", "twitter.com", "mobile.twitter.com", "fxtwitter.com"):
            return jsonify(fetch_tweet(url))
        if host.endswith("reddit.com") or host == "redd.it":
            return jsonify(fetch_reddit(url))
        if host.endswith("instagram.com"):
            return jsonify(fetch_instagram(url))
        if host == "bsky.app":
            return jsonify(fetch_bluesky(url))
        if host in ("youtube.com", "youtu.be", "music.youtube.com"):
            return jsonify(fetch_youtube(url))
        if host.endswith("tiktok.com"):
            return jsonify(fetch_tiktok(url))
        if host == "github.com":
            return jsonify(fetch_github(url))
        if host in ("threads.net", "threads.com"):
            return jsonify(fetch_threads(url))
        # Mastodon lives on thousands of instances — detect by URL shape
        if re.search(r"/@[\w.]+/\d+", url):
            return jsonify(fetch_mastodon(url))
        # Anything else: capture a screenshot of the page itself.
        return jsonify(fetch_website(url))
    except PostError as e:
        return jsonify({"error": str(e)}), 422
    except requests.RequestException:
        return jsonify({"error": "Couldn't reach that site. Check the URL and your connection."}), 502
    except Exception:
        return jsonify({"error": "Couldn't parse that post. It may be private, deleted, or in an unsupported format."}), 422


# --------------------------------------------------------------------------
# X / Twitter — public syndication endpoint
# --------------------------------------------------------------------------
def _tweet_token(tweet_id: str) -> str:
    num = (int(tweet_id) / 1e15) * math.pi
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    integer, frac = int(num), num - int(num)
    out = ""
    while integer:
        out = digits[integer % 36] + out
        integer //= 36
    out = out or "0"
    for _ in range(11):
        frac *= 36
        d = int(frac)
        out += digits[d]
        frac -= d
    return out.replace("0", "").replace(".", "")


def fetch_tweet(url: str) -> dict:
    m = re.search(r"(?:twitter|x|fxtwitter)\.com/[^/]+/status(?:es)?/(\d+)", url)
    if not m:
        raise PostError("That doesn't look like a post URL (expected .../status/<id>).")
    tid = m.group(1)
    r = requests.get(
        "https://cdn.syndication.twimg.com/tweet-result",
        params={"id": tid, "token": _tweet_token(tid), "lang": "en"},
        headers=BROWSER_UA, timeout=TIMEOUT,
    )
    if r.status_code != 200 or not r.text.strip():
        raise PostError("X wouldn't return this post. It may be deleted, age-restricted, or private.")
    j = r.json()
    if j.get("__typename") == "TweetTombstone":
        raise PostError("This post is unavailable (deleted or restricted).")
    user = j.get("user", {})
    photos = [p.get("url") for p in j.get("photos", []) if p.get("url")]
    return {
        "platform": "x", "kind": "post",
        "author_name": user.get("name", "Unknown"),
        "author_handle": "@" + user.get("screen_name", "unknown"),
        "avatar": (user.get("profile_image_url_https") or "").replace("_normal", "_200x200") or None,
        "verified": bool(user.get("is_blue_verified") or user.get("verified")),
        "text": j.get("text", ""),
        "image": photos[0] if photos else (j.get("video") or {}).get("poster"),
        "is_video": bool(j.get("video")),
        "likes": j.get("favorite_count", 0),
        "comments": j.get("conversation_count", 0),
        "date": j.get("created_at", ""),
    }


# --------------------------------------------------------------------------
# Reddit — public .json endpoint
# --------------------------------------------------------------------------
def fetch_reddit(url: str) -> dict:
    clean = url.split("?")[0].rstrip("/")
    r = requests.get(clean + "/.json", headers=PLAIN_UA, timeout=TIMEOUT, allow_redirects=True)
    if r.status_code == 403:
        raise PostError("Reddit blocked the request (rate-limited). Wait a minute and try again.")
    if r.status_code != 200:
        raise PostError("Couldn't load that Reddit post. Make sure it's a direct post link.")
    d = r.json()[0]["data"]["children"][0]["data"]
    image = None
    if d.get("preview", {}).get("images"):
        image = d["preview"]["images"][0]["source"]["url"].replace("&amp;", "&")
    elif str(d.get("url_overridden_by_dest", "")).lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        image = d["url_overridden_by_dest"]
    selftext = (d.get("selftext") or "").strip()
    if len(selftext) > 500:
        selftext = selftext[:500].rsplit(" ", 1)[0] + "…"
    return {
        "platform": "reddit", "kind": "reddit",
        "subreddit": d.get("subreddit_name_prefixed", "r/unknown"),
        "author_handle": "u/" + d.get("author", "unknown"),
        "title": d.get("title", ""),
        "text": selftext,
        "image": image,
        "is_video": bool(d.get("is_video")),
        "likes": d.get("score", 0),
        "comments": d.get("num_comments", 0),
        "created_utc": d.get("created_utc", 0),
    }


# --------------------------------------------------------------------------
# Bluesky — public AT Protocol API (no auth)
# --------------------------------------------------------------------------
def fetch_bluesky(url: str) -> dict:
    m = re.search(r"bsky\.app/profile/([^/]+)/post/([A-Za-z0-9]+)", url)
    if not m:
        raise PostError("Expected a Bluesky URL like bsky.app/profile/<handle>/post/<id>.")
    handle, rkey = m.groups()
    did = handle
    if not handle.startswith("did:"):
        r = requests.get(
            "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": handle}, headers=PLAIN_UA, timeout=TIMEOUT,
        )
        if r.status_code != 200:
            raise PostError("Couldn't resolve that Bluesky handle.")
        did = r.json()["did"]
    r = requests.get(
        "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread",
        params={"uri": f"at://{did}/app.bsky.feed.post/{rkey}", "depth": 0},
        headers=PLAIN_UA, timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise PostError("Bluesky wouldn't return this post. It may be deleted or restricted.")
    p = r.json()["thread"]["post"]
    author, record, embed = p["author"], p.get("record", {}), p.get("embed", {}) or {}
    image, is_video = None, False
    t = embed.get("$type", "")
    if "images" in t and embed.get("images"):
        image = embed["images"][0].get("fullsize")
    elif "video" in t:
        image, is_video = embed.get("thumbnail"), True
    elif "external" in t:
        image = (embed.get("external") or {}).get("thumb")
    return {
        "platform": "bluesky", "kind": "post",
        "author_name": author.get("displayName") or author.get("handle", "unknown"),
        "author_handle": "@" + author.get("handle", "unknown"),
        "avatar": author.get("avatar"),
        "verified": False,
        "text": record.get("text", ""),
        "image": image, "is_video": is_video,
        "likes": p.get("likeCount", 0),
        "reposts": p.get("repostCount", 0),
        "comments": p.get("replyCount", 0),
        "date": record.get("createdAt", ""),
    }


# --------------------------------------------------------------------------
# Mastodon — public status API on any instance
# --------------------------------------------------------------------------
def _strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>\s*<p>", "\n\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html_mod.unescape(s).strip()


def fetch_mastodon(url: str) -> dict:
    m = re.search(r"https?://([^/]+)/@[\w.@]+/(\d+)", url)
    if not m:
        raise PostError("Expected a Mastodon URL like instance/@user/123456.")
    instance, sid = m.groups()
    r = requests.get(f"https://{instance}/api/v1/statuses/{sid}", headers=PLAIN_UA, timeout=TIMEOUT)
    if r.status_code != 200:
        raise PostError("That instance wouldn't return this post (private, deleted, or not Mastodon).")
    j = r.json()
    acct = j.get("account", {})
    media = j.get("media_attachments") or []
    image, is_video = None, False
    if media:
        m0 = media[0]
        image = m0.get("url") if m0.get("type") == "image" else m0.get("preview_url")
        is_video = m0.get("type") in ("video", "gifv")
    return {
        "platform": "mastodon", "kind": "post",
        "author_name": acct.get("display_name") or acct.get("username", "unknown"),
        "author_handle": "@" + (acct.get("acct") or acct.get("username", "unknown")),
        "avatar": acct.get("avatar"),
        "verified": False,
        "text": _strip_html(j.get("content", "")),
        "image": image, "is_video": is_video,
        "likes": j.get("favourites_count", 0),
        "reposts": j.get("reblogs_count", 0),
        "comments": j.get("replies_count", 0),
        "date": j.get("created_at", ""),
    }


# --------------------------------------------------------------------------
# YouTube — public oEmbed + thumbnail endpoints
# --------------------------------------------------------------------------
def fetch_youtube(url: str) -> dict:
    r = requests.get(
        "https://www.youtube.com/oembed",
        params={"url": url, "format": "json"}, headers=PLAIN_UA, timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise PostError("YouTube wouldn't return this video. It may be private or removed.")
    j = r.json()
    vid = None
    m = (re.search(r"youtu\.be/([\w-]{6,})", url)
         or re.search(r"[?&]v=([\w-]{6,})", url)
         or re.search(r"/shorts/([\w-]{6,})", url)
         or re.search(r"/embed/([\w-]{6,})", url))
    if m:
        vid = m.group(1)
    return {
        "platform": "youtube", "kind": "video",
        "title": j.get("title", ""),
        "author_name": j.get("author_name", ""),
        "image": f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg" if vid else j.get("thumbnail_url"),
        "image_fallback": j.get("thumbnail_url"),
    }


# --------------------------------------------------------------------------
# TikTok — public oEmbed
# --------------------------------------------------------------------------
def fetch_tiktok(url: str) -> dict:
    r = requests.get("https://www.tiktok.com/oembed", params={"url": url}, headers=PLAIN_UA, timeout=TIMEOUT)
    if r.status_code != 200 or "thumbnail_url" not in r.text:
        raise PostError("TikTok wouldn't return this video. Use a full video link (tiktok.com/@user/video/…).")
    j = r.json()
    return {
        "platform": "tiktok", "kind": "video",
        "title": j.get("title", ""),
        "author_name": j.get("author_name", ""),
        "author_handle": "@" + (j.get("author_unique_id") or j.get("author_name", "")),
        "image": j.get("thumbnail_url"),
    }


# --------------------------------------------------------------------------
# GitHub — public REST API
# --------------------------------------------------------------------------
def fetch_github(url: str) -> dict:
    m = re.search(r"github\.com/([\w.-]+)/([\w.-]+)", url)
    if not m:
        raise PostError("Expected a repository URL like github.com/owner/repo.")
    owner, repo = m.group(1), m.group(2).removesuffix(".git")
    headers = {**PLAIN_UA, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:  # optional: raises the rate limit from 60 to 5000 req/hour
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers, timeout=TIMEOUT)
    if r.status_code == 404:
        raise PostError("Repository not found (or it's private).")
    if r.status_code == 403:
        raise PostError("GitHub rate limit hit. Try again in a few minutes.")
    j = r.json()
    return {
        "platform": "github", "kind": "repo",
        "full_name": j.get("full_name", f"{owner}/{repo}"),
        "description": j.get("description") or "",
        "avatar": (j.get("owner") or {}).get("avatar_url"),
        "stars": j.get("stargazers_count", 0),
        "forks": j.get("forks_count", 0),
        "issues": j.get("open_issues_count", 0),
        "language": j.get("language") or "",
    }


# --------------------------------------------------------------------------
# Any other website — render a screenshot via free, no-key services
# --------------------------------------------------------------------------
SCREENSHOT_W = 1280


def fetch_website(url: str) -> dict:
    """Fall-back for non-social URLs: return screenshot image URLs.

    The rendering is done by public no-key services; the resulting PNG is then
    pulled through /api/img (same SSRF guard + un-tainting as every other
    imported image). thum.io renders synchronously so it's tried first;
    WordPress mShots is the fallback if thum.io errors or times out.
    """
    enc = quote(url, safe="")
    host = (urlparse(url).hostname or url).removeprefix("www.")
    return {
        "platform": "website", "kind": "screenshot",
        "title": host, "url": url,
        "image": f"https://image.thum.io/get/width/{SCREENSHOT_W}/noanimate/{url}",
        "image_fallback": f"https://s.wordpress.com/mshots/v1/{enc}?w={SCREENSHOT_W}",
    }


# --------------------------------------------------------------------------
# Instagram & Threads — best-effort OpenGraph scrape (both block heavily)
# --------------------------------------------------------------------------
def _og_scrape(url: str):
    r = requests.get(url.split("?")[0], headers=BROWSER_UA, timeout=TIMEOUT)
    html = r.text

    def og(prop):
        m = (re.search(r'property="og:%s"\s+content="([^"]*)"' % prop, html)
             or re.search(r'content="([^"]*)"\s+property="og:%s"' % prop, html))
        return html_mod.unescape(m.group(1)) if m else None

    return og


def fetch_instagram(url: str) -> dict:
    og = _og_scrape(url)
    image, desc, title = og("image"), og("description") or "", og("title") or ""
    if not image:
        raise PostError("Instagram is blocking anonymous access to this post. "
                        "Works only for some public posts — or upload a screenshot instead.")
    likes = _count(re.search(r"([\d,.]+[KMkm]?)\s+likes", desc))
    comments = _count(re.search(r"([\d,.]+[KMkm]?)\s+comments", desc))
    username = None
    m = re.search(r"\(@([A-Za-z0-9._]+)\)", title) or re.search(r"-\s*@?([A-Za-z0-9._]+)\s+on", desc)
    if m:
        username = m.group(1)
    caption = ""
    m = re.search(r':\s*[""]([^""]+)[""]', desc)
    if m:
        caption = m.group(1)
    return {
        "platform": "instagram", "kind": "instagram",
        "author_handle": username or "instagram", "avatar": None,
        "image": image, "likes": likes, "comments": comments, "text": caption,
    }


def fetch_threads(url: str) -> dict:
    og = _og_scrape(url)
    image, desc, title = og("image"), og("description") or "", og("title") or ""
    if not (desc or image):
        raise PostError("Threads is blocking anonymous access to this post. "
                        "Works only for some public posts — or upload a screenshot instead.")
    username = None
    m = re.search(r"@([A-Za-z0-9._]+)", title + " " + desc)
    if m:
        username = m.group(1)
    text = desc
    m = re.search(r':\s*[""]?(.+?)[""]?$', desc)
    if m:
        text = m.group(1)
    return {
        "platform": "threads", "kind": "post",
        "author_name": username or "threads", "author_handle": "@" + (username or "threads"),
        "avatar": None, "verified": False,
        "text": text, "image": image, "is_video": False,
        "likes": None, "comments": None, "date": "",
    }


def _count(m) -> int:
    if not m:
        return 0
    s = m.group(1).replace(",", "").strip()
    mult = 1
    if s[-1:].lower() == "k":
        mult, s = 1_000, s[:-1]
    elif s[-1:].lower() == "m":
        mult, s = 1_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


# --------------------------------------------------------------------------
# Image proxy — keeps the canvas un-tainted so PNG/WebM export works
# --------------------------------------------------------------------------
@app.route("/api/img")
def proxy_image():
    u = request.args.get("u", "")
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        return "Bad URL", 400
    try:
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return "Forbidden", 403
    except socket.gaierror:
        return "Unresolvable host", 400
    # Generous timeout: screenshot services (thum.io / mShots) render the page
    # on demand and can take a while; a slow render should fall back, not 500.
    try:
        r = requests.get(u, headers=BROWSER_UA, timeout=30)
    except requests.RequestException:
        return "Upstream error", 502
    if r.status_code != 200:
        return "Upstream error", 502
    if len(r.content) > 25 * 1024 * 1024:
        return "Image too large", 413
    return Response(
        r.content,
        content_type=r.headers.get("Content-Type", "image/jpeg"),
        headers={"Cache-Control": "public, max-age=3600"},
    )


if __name__ == "__main__":
    print("\n  Glaze Studio →  http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
