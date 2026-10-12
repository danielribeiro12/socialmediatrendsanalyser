"""Logged-out TikTok scraper: Explore categories, plus hashtag and sound pages.

Opens pages in a real browser and captures the JSON TikTok's own page loads
(no request signing to reverse).
"""
import argparse
import json
import random
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from .parse import parse_item
from .store import Store
from .tracking import load_watchlist, pick_sounds, pick_tags

BASE = "https://www.tiktok.com"
EXPLORE_URL = f"{BASE}/explore"

ALL_CATEGORIES = [
    "All", "Singing & Dancing", "Comedy", "Sports", "Anime & Comics", "Relationship", "Shows",
    "Lipsync", "Daily Life", "Beauty Care", "Games", "Society", "Outfit", "Cars", "Food",
    "Animals", "Family", "Drama", "Fitness & Health", "Education", "Technology",
]

CATEGORY_SELECTOR = ("[class*='CategoryList'] button, [class*='CategoryItem'], "
                     "[data-e2e*='category'] button, [role='tab']")


# Pauses between pages (seconds). --slow raises them for scheduled runs.
PAUSES = {"explore": (2, 5), "page": (5, 10)}
SLOW_PAUSES = {"explore": (10, 20), "page": (15, 30)}


def pause(kind):
    time.sleep(random.uniform(*PAUSES[kind]))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- JSON helpers

def find_items(obj):
    """Find a list of videos anywhere in a JSON blob (TikTok renames keys sometimes)."""
    if isinstance(obj, dict):
        for key in ("itemList", "item_list", "items"):
            val = obj.get(key)
            if isinstance(val, list) and val and isinstance(val[0], dict) and "id" in val[0]:
                return val
        for val in obj.values():
            found = find_items(val)
            if found:
                return found
    elif isinstance(obj, list):
        for val in obj:
            found = find_items(val)
            if found:
                return found
    return None


def _find_key(obj, key):
    if isinstance(obj, dict):
        if isinstance(obj.get(key), dict):
            return obj[key]
        for val in obj.values():
            found = _find_key(val, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for val in obj:
            found = _find_key(val, key)
            if found is not None:
                return found
    return None


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def find_page_info(kind, blobs):
    """Pull the totals shown on a hashtag or sound page."""
    key = "challengeInfo" if kind == "tag" else "musicInfo"
    for blob in blobs:
        info = _find_key(blob, key)
        if not info:
            continue
        stats = {**(info.get("stats") or {}), **{k: v for k, v in (info.get("statsV2") or {}).items()
                                                 if _num(v) is not None}}
        if kind == "tag":
            meta = info.get("challenge") or {}
            title = meta.get("title")
        else:
            meta = info.get("music") or {}
            title = " - ".join(x for x in (meta.get("title"), meta.get("authorName")) if x) or None
        return {"title": title, "video_count": _num(stats.get("videoCount")),
                "view_count": _num(stats.get("viewCount"))}
    return None


# ---------------------------------------------------------------- browser

CAPTCHA_SELECTORS = (
    "#captcha-verify-image", "#captcha_container", "[id*='captcha' i]",
    "[class*='captcha' i]", "iframe[src*='captcha' i]",
)
CAPTCHA_TEXT = re.compile(r"verify to continue|drag the (slider|puzzle)|select \d+ objects", re.I)


class CaptchaStop(Exception):
    """TikTok showed a CAPTCHA: stop instead of hammering the site."""

class Browser:
    def __init__(self, show):
        self.show = show
        self.items, self.jsons = [], []

    def __enter__(self):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=not self.show)
        ctx = self.browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 900},
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
        )
        self.page = ctx.new_page()
        self.page.on("response", self._on_response)
        return self

    def __exit__(self, *exc):
        self.browser.close()
        self.pw.stop()

    def _on_response(self, resp):
        if "tiktok.com/api/" not in resp.url:
            return
        if "json" not in (resp.headers.get("content-type") or ""):
            return
        try:
            data = resp.json()
        except Exception:
            return
        self.jsons.append(data)
        items = find_items(data)
        if items:
            self.items.extend(items)

    def reset(self):
        self.items.clear()
        self.jsons.clear()

    def open(self, url):
        self.reset()
        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self.page.wait_for_timeout(random.randint(3000, 4500))
        self.check_captcha()
        self.dismiss_popups()

    def captcha_visible(self):
        for sel in CAPTCHA_SELECTORS:
            try:
                if self.page.locator(sel).first.is_visible(timeout=300):
                    return True
            except Exception:
                pass
        try:
            return self.page.get_by_text(CAPTCHA_TEXT).first.is_visible(timeout=300)
        except Exception:
            return False

    def check_captcha(self, wait_s=300):
        """If a CAPTCHA is up: with a visible window, give the person time to solve it
        themselves; otherwise stop the run."""
        if not self.captcha_visible():
            return
        if self.show:
            log(f"  CAPTCHA on screen. Solve it in the browser window if you want the run to "
                f"continue (waiting up to {wait_s // 60} min)...")
            deadline = time.time() + wait_s
            while time.time() < deadline:
                self.page.wait_for_timeout(3000)
                if not self.captcha_visible():
                    log("  CAPTCHA cleared, continuing.")
                    self.page.wait_for_timeout(2000)
                    return
        raise CaptchaStop()

    def page_data(self):
        """The data TikTok embeds in the page's HTML."""
        try:
            txt = self.page.evaluate("""() => {
                for (const id of ['__UNIVERSAL_DATA_FOR_REHYDRATION__', 'SIGI_STATE']) {
                    const el = document.getElementById(id);
                    if (el) return el.textContent;
                }
                return null;
            }""")
            return json.loads(txt) if txt else None
        except Exception:
            return None

    def dismiss_popups(self):
        self.page.keyboard.press("Escape")
        for label in ("Decline optional cookies", "Decline all", "Not now", "Close"):
            try:
                btn = self.page.get_by_role("button", name=label)
                if btn.count():
                    btn.first.click(timeout=1500)
            except Exception:
                pass

    def collect(self, label, max_items, max_idle=6, seen=None):
        """Scroll and gather videos until max_items or nothing new appears."""
        seen = set() if seen is None else seen
        out, idle = [], 0
        while len(out) < max_items and idle < max_idle:
            before = len(out)
            while self.items and len(out) < max_items:
                item = self.items.pop(0)
                vid = str(item.get("id"))
                if vid in seen:
                    continue
                seen.add(vid)
                out.append(parse_item(item, label, now()))
            if len(out) >= max_items:
                break
            idle = idle + 1 if len(out) == before else 0
            self.page.mouse.wheel(0, random.randint(2500, 4000))
            self.page.wait_for_timeout(random.randint(1500, 3000))
            self.check_captcha()
            self.dismiss_popups()
        return out


# ---------------------------------------------------------------- explore

def list_categories(page):
    names = []
    for el in page.locator(CATEGORY_SELECTOR).all():
        try:
            t = el.inner_text(timeout=500).strip()
            if t and t not in names and len(t) < 40:
                names.append(t)
        except Exception:
            pass
    return names


def _try_click(el):
    """Click an element, falling back to force/JS clicks if a popup is in the way."""
    el.scroll_into_view_if_needed(timeout=2000)
    last = None
    for attempt in ("normal", "force", "js"):
        try:
            if attempt == "normal":
                el.click(timeout=3000)
            elif attempt == "force":
                el.click(timeout=3000, force=True)
            else:
                el.evaluate("e => e.click()")
            return None
        except Exception as exc:
            last = exc
    return last


def click_category(page, name):
    """Returns None on success, or a reason string on failure."""
    if name.lower() in ("all", ""):
        return None
    exact = re.compile(rf"^\s*{re.escape(name)}\s*$", re.I)
    locators = (
        page.locator(CATEGORY_SELECTOR).filter(has_text=exact),
        page.get_by_role("button", name=name, exact=True),
        page.get_by_role("tab", name=name, exact=True),
        page.get_by_text(name, exact=True),
    )
    reason = "no matching element"
    for loc in locators:
        try:
            n = loc.count()
        except Exception:
            continue
        for i in range(min(n, 3)):
            el = loc.nth(i)
            try:
                if not el.is_visible():
                    continue
                err = _try_click(el)
                if err is None:
                    return None
                reason = repr(err)[:200]
            except Exception as exc:
                reason = repr(exc)[:200]
    return reason


def scrape_explore(b, categories, max_items, records, errors):
    for category in categories:
        try:
            b.open(EXPLORE_URL)
            reason = click_category(b.page, category)
            if reason:
                avail = list_categories(b.page)
                code = "CATEGORY_CLICK_FAILED" if category in avail else "CATEGORY_NOT_FOUND"
                errors.append({"category": category, "scraped_at": now(), "errorCode": code,
                               "error": f"Couldn't click '{category}' ({reason}). "
                                        f"Seen on page: {avail}"})
                continue
            if category.lower() != "all":
                b.items.clear()  # drop the default feed loaded before the click
            b.page.wait_for_timeout(3000)
            got = b.collect(category, max_items)
            if not got:
                errors.append({"category": category, "scraped_at": now(),
                               "errorCode": "EXPLORE_EMPTY",
                               "error": "No videos captured. TikTok may be blocking the "
                                        "browser; try again with --show."})
            records.extend(got)
            log(f"  {category}: {len(got)} videos")
        except CaptchaStop:
            raise
        except Exception as exc:
            errors.append({"category": category, "scraped_at": now(),
                           "errorCode": "SCRAPE_FAILED", "error": repr(exc)[:300]})
        pause("explore")


# ---------------------------------------------------------------- hashtag / sound pages

def page_url(kind, key):
    return f"{BASE}/tag/{quote(key)}" if kind == "tag" else f"{BASE}/music/sound-{key}"


def scrape_page(b, kind, key, max_items, records, errors, pages):
    label = f"{kind}:{key}"
    try:
        b.open(page_url(kind, key))
        data = b.page_data()
        b.items[:0] = find_items(data) or []
        got = b.collect(label, max_items, max_idle=2)
        info = find_page_info(kind, ([data] if data else []) + b.jsons)
        if info:
            pages.append({"scraped_at": now(), "kind": kind, "key": key, **info})
        records.extend(got)
        if not info and not got:
            errors.append({"category": label, "scraped_at": now(), "errorCode": "PAGE_EMPTY",
                           "error": "No totals or videos found (page missing, or TikTok "
                                    "wanted a login)."})
        count = info["video_count"] if info else None
        log(f"  {label}: {count if count is not None else '?'} total videos, {len(got)} sampled")
    except CaptchaStop:
        raise
    except Exception as exc:
        errors.append({"category": label, "scraped_at": now(), "errorCode": "SCRAPE_FAILED",
                       "error": repr(exc)[:300]})
    pause("page")


# ---------------------------------------------------------------- run

def scrape(categories, max_items=50, show=False, data_dir="data", track=False,
           track_items=15, watchlist="watchlist.txt", n_sounds=20, n_tags=10):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    store = Store(data_dir)
    records, errors, pages = [], [], []

    with Browser(show) as b:
        try:
            if categories:
                log(f"Explore: {len(categories)} categories")
                scrape_explore(b, categories, max_items, records, errors)
                store.save(run_id, records, errors)  # so tracking can pick from this run too

            if track:
                sounds = pick_sounds(store.db, n_new=n_sounds, n_keep=n_sounds)
                tags = pick_tags(store.db, load_watchlist(watchlist), n_new=n_tags, n_keep=n_tags)
                log(f"Tracking: {len(tags)} hashtags, {len(sounds)} sounds")
                for t in tags:
                    scrape_page(b, "tag", t, track_items, records, errors, pages)
                for s in sounds:
                    scrape_page(b, "sound", s, track_items, records, errors, pages)
        except CaptchaStop:
            errors.append({"category": "-", "scraped_at": now(), "errorCode": "CAPTCHA",
                           "error": "TikTok asked for a CAPTCHA, so the run stopped early. "
                                    "Everything collected before that was saved."})

    out = store.save(run_id, records, errors, pages)
    return run_id, records, errors, pages, out


def main():
    ap = argparse.ArgumentParser(description="Scrape TikTok (logged out).")
    ap.add_argument("categories", nargs="*",
                    help='Explore categories, e.g. "Comedy" "Singing & Dancing". Default: All')
    ap.add_argument("--all", action="store_true", help="Scrape every Explore category")
    ap.add_argument("--max-items", type=int, default=50, help="Max videos per category")
    ap.add_argument("--track", action="store_true",
                    help="Also check hashtag and sound pages (watchlist + top recent ones)")
    ap.add_argument("--track-only", action="store_true", help="Only check hashtag/sound pages")
    ap.add_argument("--sounds", type=int, default=20, help="New sounds to start tracking per run")
    ap.add_argument("--tags", type=int, default=10, help="New hashtags to start tracking per run")
    ap.add_argument("--show", action="store_true", help="Show the browser window")
    ap.add_argument("--fallback-show", action="store_true",
                    help="If a hidden-browser run gets nothing, retry with the window shown")
    ap.add_argument("--slow", action="store_true",
                    help="Longer pauses between pages (used by the scheduled runs)")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--watchlist", default="watchlist.txt")
    args = ap.parse_args()

    if args.track_only:
        categories = []
    else:
        categories = ALL_CATEGORIES if args.all else (args.categories or ["All"])
    track = args.track or args.track_only
    if args.slow:
        PAUSES.update(SLOW_PAUSES)

    def run(show):
        if show:
            log("(browser visible)")
        run_id, records, errors, pages, out = scrape(
            categories, args.max_items, show, args.data_dir, track,
            watchlist=args.watchlist, n_sounds=args.sounds, n_tags=args.tags)
        log(f"Run {run_id}: {len(records)} videos, {len(pages)} hashtag/sound totals, "
            f"{len(errors)} errors -> {out}")
        for e in errors:
            log(f"  [{e['errorCode']}] {e['category']}: {e['error']}")
        captcha = any(e["errorCode"] == "CAPTCHA" for e in errors)
        return records or pages or captcha

    got = run(args.show)
    if not got and args.fallback_show and not args.show:
        log("Nothing collected with the hidden browser; retrying with it visible.")
        run(True)


if __name__ == "__main__":
    main()
