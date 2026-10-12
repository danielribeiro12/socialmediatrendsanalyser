"""Quick look at the latest run: top hashtags and sounds."""
import argparse
import json
import sqlite3
from collections import Counter, defaultdict

# Tags people add to everything; they never signal a specific trend.
GENERIC_TAGS = {
    "fyp", "foryou", "foryoupage", "fy", "fypage", "fypシ", "fypシ゚viral", "viral", "viralvideo",
    "trending", "trend", "goviral", "explore", "explorepage", "tiktok", "funny", "funnyvideos",
    "comedy", "humor", "humour", "meme", "memes", "capcut", "xyzbca", "parati", "pourtoi",
    "fürdich", "foryourpage", "4u", "4you", "relatable", "lol", "blowthisup",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/tiktok.db")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    db = sqlite3.connect(args.db)
    run = db.execute("SELECT MAX(run_id) FROM observations").fetchone()[0]
    if not run:
        print("No data yet. Run the scraper first.")
        return
    rows = db.execute("SELECT hashtags, sound_id, sound_title, sound_author, sound_original, "
                      "author_id, plays FROM observations WHERE run_id=? AND is_ad=0", (run,)).fetchall()

    tag_authors, tag_plays = defaultdict(set), Counter()
    sound_authors, sound_plays, sound_names = defaultdict(set), Counter(), {}
    for tags, sid, title, sauthor, orig, author, plays in rows:
        for t in json.loads(tags):
            if t in GENERIC_TAGS or t.startswith("fyp"):
                continue
            tag_authors[t].add(author)
            tag_plays[t] += plays or 0
        if sid:
            sound_authors[sid].add(author)
            sound_plays[sid] += plays or 0
            sound_names[sid] = f"{title} - {sauthor}" + (" (original)" if orig else "")

    print(f"Run {run}: {len(rows)} videos\n\nTop hashtags (by number of different creators using them)")
    for t, a in sorted(tag_authors.items(), key=lambda kv: (-len(kv[1]), -tag_plays[kv[0]]))[:args.top]:
        print(f"  {len(a):>3} creators  {tag_plays[t]:>14,} plays  #{t}")
    print("\nTop sounds")
    for s, a in sorted(sound_authors.items(), key=lambda kv: (-len(kv[1]), -sound_plays[kv[0]]))[:args.top]:
        print(f"  {len(a):>3} creators  {sound_plays[s]:>14,} plays  {sound_names[s][:60]}")


if __name__ == "__main__":
    main()
