"""Choose which hashtag and sound pages to check on a tracking run."""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .parse import is_generic

EXPLORE_ONLY = "category NOT LIKE 'sound:%' AND category NOT LIKE 'tag:%'"


def _since(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def load_watchlist(path="watchlist.txt"):
    p = Path(path)
    if not p.exists():
        return []
    tags = []
    for line in p.read_text(encoding="utf-8").splitlines():
        t = line.strip().lstrip("#").strip().lower()
        if t and not line.strip().startswith("# ") and t not in tags:
            tags.append(t)
    return tags


def _recently_tracked(db, kind, days, limit):
    """Keep checking pages we started tracking recently, so they get a continuous history."""
    rows = db.execute(
        "SELECT key, MIN(scraped_at) AS first FROM pages WHERE kind=? GROUP BY key "
        "HAVING first >= ? ORDER BY first DESC LIMIT ?", (kind, _since(days), limit)).fetchall()
    return [r[0] for r in rows]


def pick_sounds(db, n_new=40, n_keep=40, days=3, keep_days=7):
    """Sounds from recent Explore runs used by the most different creators."""
    rows = db.execute(
        f"SELECT sound_id, COUNT(DISTINCT author_id) AS creators, SUM(COALESCE(plays,0)) AS plays "
        f"FROM observations WHERE {EXPLORE_ONLY} AND is_ad=0 AND sound_id IS NOT NULL "
        f"AND scraped_at >= ? GROUP BY sound_id ORDER BY creators DESC, plays DESC",
        (_since(days),)).fetchall()
    keep = _recently_tracked(db, "sound", keep_days, n_keep)
    picks = list(keep)
    for sid, _, _ in rows:
        if len(picks) >= len(keep) + n_new:
            break
        if sid not in picks:
            picks.append(sid)
    return picks


def pick_tags(db, watchlist, n_new=20, n_keep=20, days=3, keep_days=7):
    """Watchlist tags, plus non-generic tags from recent Explore runs used by the most creators."""
    rows = db.execute(
        f"SELECT hashtags, author_id FROM observations WHERE {EXPLORE_ONLY} AND is_ad=0 "
        f"AND scraped_at >= ?", (_since(days),)).fetchall()
    creators = defaultdict(set)
    for tags, author in rows:
        for t in json.loads(tags or "[]"):
            if not is_generic(t):
                creators[t].add(author)
    ranked = sorted(creators, key=lambda t: -len(creators[t]))
    picks = list(watchlist)
    for t in _recently_tracked(db, "tag", keep_days, n_keep):
        if t not in picks:
            picks.append(t)
    limit = len(picks) + n_new
    for t in ranked:
        if len(picks) >= limit:
            break
        if t not in picks:
            picks.append(t)
    return picks
