"""Quick look at the data: latest Explore run, plus which hashtags/sounds are growing."""
import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime

from .parse import is_generic
from .tracking import EXPLORE_ONLY


def _ts(s):
    return datetime.fromisoformat(s)


def explore_section(db, top):
    run = db.execute(f"SELECT MAX(run_id) FROM observations WHERE {EXPLORE_ONLY}").fetchone()[0]
    if not run:
        print("No Explore data yet.")
        return
    rows = db.execute(
        f"SELECT hashtags, sound_id, sound_title, sound_author, sound_original, author_id, plays "
        f"FROM observations WHERE run_id=? AND is_ad=0 AND {EXPLORE_ONLY}", (run,)).fetchall()

    tag_authors, tag_plays = defaultdict(set), Counter()
    sound_authors, sound_plays, sound_names = defaultdict(set), Counter(), {}
    for tags, sid, title, sauthor, orig, author, plays in rows:
        for t in json.loads(tags):
            if is_generic(t):
                continue
            tag_authors[t].add(author)
            tag_plays[t] += plays or 0
        if sid:
            sound_authors[sid].add(author)
            sound_plays[sid] += plays or 0
            sound_names[sid] = f"{title} - {sauthor}" + (" (original)" if orig else "")

    print(f"Latest Explore run {run}: {len(rows)} videos\n")
    print("Top hashtags (by number of different creators)")
    for t, a in sorted(tag_authors.items(), key=lambda kv: (-len(kv[1]), -tag_plays[kv[0]]))[:top]:
        print(f"  {len(a):>3} creators  {tag_plays[t]:>14,} plays  #{t}")
    print("\nTop sounds")
    for s, a in sorted(sound_authors.items(), key=lambda kv: (-len(kv[1]), -sound_plays[kv[0]]))[:top]:
        print(f"  {len(a):>3} creators  {sound_plays[s]:>14,} plays  {sound_names[s][:60]}")


def growth(db, kind, min_hours=6):
    """For each tracked page: latest total vs the previous check, as videos added per day."""
    hist = defaultdict(list)
    for key, title, at, count in db.execute(
            "SELECT key, title, scraped_at, video_count FROM pages WHERE kind=? "
            "AND video_count IS NOT NULL ORDER BY scraped_at", (kind,)):
        hist[key].append((at, count, title))
    out = []
    for key, pts in hist.items():
        latest_at, latest, title = pts[-1]
        prev = next((p for p in reversed(pts[:-1])
                     if (_ts(latest_at) - _ts(p[0])).total_seconds() >= min_hours * 3600), None)
        if not prev:
            out.append((key, title, latest, None, None, pts[0][0]))
            continue
        hours = (_ts(latest_at) - _ts(prev[0])).total_seconds() / 3600
        per_day = (latest - prev[1]) / hours * 24
        pct = (latest - prev[1]) / prev[1] * 100 if prev[1] else None
        out.append((key, title, latest, per_day, pct, pts[0][0]))
    return out


def growth_section(db, kind, top):
    has_pages = db.execute("SELECT 1 FROM sqlite_master WHERE name='pages'").fetchone()
    rows = growth(db, kind) if has_pages else []
    name = "hashtags" if kind == "tag" else "sounds"
    if not rows:
        print(f"\nNo {name} tracked yet (run the scraper with --track).")
        return
    measured = [r for r in rows if r[3] is not None]
    print(f"\nFastest-growing {name} ({len(rows)} tracked, {len(measured)} with 2+ checks)")
    if not measured:
        print("  Needs a second check at least 6 hours later to measure growth.")
    for key, title, latest, per_day, pct, first in sorted(measured, key=lambda r: -r[3])[:top]:
        label = f"#{key}" if kind == "tag" else (title or key)
        pct_s = f"{pct:+.1f}%" if pct is not None else "  new"
        print(f"  {per_day:>+10,.0f}/day  {pct_s:>8}  {latest:>11,} videos  "
              f"{label[:55]}  (tracked since {first[:10]})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/tiktok.db")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    db = sqlite3.connect(args.db)
    try:
        explore_section(db, args.top)
        growth_section(db, "sound", args.top)
        growth_section(db, "tag", args.top)
    except sqlite3.OperationalError as exc:
        print(f"No data yet ({exc}). Run the scraper first.")


if __name__ == "__main__":
    main()
