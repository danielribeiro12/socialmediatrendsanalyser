"""Logged-out TikTok Explore scraper.

Opens tiktok.com/explore in a real browser, clicks a category, scrolls, and
captures the JSON the page itself loads (no request signing to reverse).
"""
import argparse
import random
import re
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

from .parse import parse_item
from .store import Store

EXPLORE_URL = "https://www.tiktok.com/explore"

ALL_CATEGORIES = [
    "All", "Singing & Dancing", "Comedy", "Sports", "Anime & Comics", "Relationship", "Shows",
    "Lipsync", "Daily Life", "Beauty Care", "Games", "Society", "Outfit", "Cars", "Food",
    "Animals", "Family", "Drama", "Fitness & Health", "Education", "Technology",
]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_items(obj):
    """Find item lists anywhere in a JSON response (TikTok renames keys sometimes)."""
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


def dismiss_popups(page):
    page.keyboard.press("Escape")
    for label in ("Decline optional cookies", "Decline all", "Not now", "Close"):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count():
                btn.first.click(timeout=1500)
        except Exception:
            pass


CATEGORY_SELECTOR = ("[class*='CategoryList'] button, [class*='CategoryItem'], "
                     "[data-e2e*='category'] button, [role='tab']")


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


def scrape(categories, max_items=100, show=False, data_dir="data", max_idle_scrolls=6):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    store = Store(data_dir)
    records, errors = [], []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not show)
        ctx = browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 900},
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()
        captured = []

        def on_response(resp):
            if "tiktok.com/api/" not in resp.url:
                return
            if "json" not in (resp.headers.get("content-type") or ""):
                return
            try:
                items = find_items(resp.json())
            except Exception:
                return
            if items:
                captured.extend(items)

        page.on("response", on_response)

        for category in categories:
            captured.clear()
            seen, cat_records = set(), []
            try:
                page.goto(EXPLORE_URL, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)
                dismiss_popups(page)
                reason = click_category(page, category)
                if reason:
                    avail = list_categories(page)
                    code = "CATEGORY_CLICK_FAILED" if category in avail else "CATEGORY_NOT_FOUND"
                    errors.append({"category": category, "scraped_at": now(), "errorCode": code,
                                   "error": f"Couldn't click '{category}' ({reason}). "
                                            f"Seen on page: {avail}"})
                    continue
                if category.lower() != "all":
                    captured.clear()  # drop the default feed loaded before the click
                page.wait_for_timeout(3000)

                idle = 0
                while len(cat_records) < max_items and idle < max_idle_scrolls:
                    before = len(cat_records)
                    while captured:
                        item = captured.pop(0)
                        vid = str(item.get("id"))
                        if vid in seen:
                            continue
                        seen.add(vid)
                        cat_records.append(parse_item(item, category, now()))
                    idle = idle + 1 if len(cat_records) == before else 0
                    page.mouse.wheel(0, random.randint(2500, 4000))
                    page.wait_for_timeout(random.randint(1500, 3000))
                    dismiss_popups(page)

                if not cat_records:
                    errors.append({"category": category, "scraped_at": now(),
                                   "errorCode": "EXPLORE_EMPTY",
                                   "error": "No videos captured. TikTok may be blocking the "
                                            "browser; try again with --show."})
                records.extend(cat_records[:max_items])
                print(f"  {category}: {len(cat_records[:max_items])} videos", flush=True)
            except Exception as exc:
                errors.append({"category": category, "scraped_at": now(),
                               "errorCode": "SCRAPE_FAILED", "error": repr(exc)})
            time.sleep(random.uniform(2, 5))

        browser.close()

    out = store.save(run_id, records, errors)
    return run_id, records, errors, out


def main():
    ap = argparse.ArgumentParser(description="Scrape TikTok Explore categories (logged out).")
    ap.add_argument("categories", nargs="*",
                    help='Explore categories, e.g. "Comedy" "Singing & Dancing". Default: All')
    ap.add_argument("--all", action="store_true", help="Scrape every Explore category")
    ap.add_argument("--max-items", type=int, default=50, help="Max videos per category")
    ap.add_argument("--show", action="store_true", help="Show the browser window")
    ap.add_argument("--fallback-show", action="store_true",
                    help="If a hidden-browser run gets no videos, retry with the window shown")
    ap.add_argument("--data-dir", default="data")
    args = ap.parse_args()
    categories = ALL_CATEGORIES if args.all else (args.categories or ["All"])

    def run(show):
        print(f"Scraping {len(categories)} categor{'y' if len(categories) == 1 else 'ies'}"
              f"{' (browser visible)' if show else ''}...", flush=True)
        run_id, records, errors, out = scrape(categories, args.max_items, show, args.data_dir)
        print(f"Run {run_id}: {len(records)} videos, {len(errors)} errors -> {out}", flush=True)
        for e in errors:
            print(f"  [{e['errorCode']}] {e['category']}: {e['error']}", flush=True)
        return records

    records = run(args.show)
    if not records and args.fallback_show and not args.show:
        print("No videos with the hidden browser; retrying with it visible.", flush=True)
        run(True)


if __name__ == "__main__":
    main()
