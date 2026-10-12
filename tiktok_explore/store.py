"""Save scrape results to SQLite (for trend tracking) and JSONL (raw export)."""
import json
import sqlite3
from pathlib import Path

OBS_COLS = ("run_id, video_id, url, category, scraped_at, created_at, caption, hashtags, plays, "
            "likes, shares, comments, author_id, sound_id, sound_title, sound_author, "
            "sound_original, duration_s, is_ad")

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    run_id TEXT, video_id TEXT, url TEXT, category TEXT, scraped_at TEXT,
    created_at TEXT, caption TEXT, hashtags TEXT, plays INTEGER, likes INTEGER,
    shares INTEGER, comments INTEGER, author_id TEXT, sound_id TEXT,
    sound_title TEXT, sound_author TEXT, sound_original INTEGER,
    duration_s INTEGER, is_ad INTEGER,
    PRIMARY KEY (run_id, video_id, category)
);
CREATE TABLE IF NOT EXISTS errors (
    run_id TEXT, scraped_at TEXT, category TEXT, error_code TEXT, error TEXT
);
-- One row per hashtag/sound page visit: the totals TikTok shows on that page.
CREATE TABLE IF NOT EXISTS pages (
    run_id TEXT, scraped_at TEXT, kind TEXT, key TEXT, title TEXT,
    video_count INTEGER, view_count INTEGER,
    PRIMARY KEY (run_id, kind, key)
);
CREATE INDEX IF NOT EXISTS obs_time ON observations (scraped_at);
CREATE INDEX IF NOT EXISTS pages_key ON pages (kind, key, scraped_at);
"""


def _migrate(db):
    """Older databases keyed observations on (run_id, video_id) only."""
    row = db.execute("SELECT sql FROM sqlite_master WHERE name='observations'").fetchone()
    if row and "PRIMARY KEY (run_id, video_id)" in row[0]:
        db.executescript("ALTER TABLE observations RENAME TO observations_old;")
        db.executescript(SCHEMA)
        db.execute(f"INSERT INTO observations ({OBS_COLS}) SELECT {OBS_COLS} FROM observations_old")
        db.executescript("DROP TABLE observations_old;")
        db.commit()


class Store:
    def __init__(self, data_dir):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.dir / "tiktok.db")
        _migrate(self.db)
        self.db.executescript(SCHEMA)

    def save(self, run_id, records, errors, pages=()):
        rows = [
            (run_id, r["video_id"], r["url"], r["category"], r["scraped_at"], r["created_at"],
             r["caption"], json.dumps(r["hashtags"], ensure_ascii=False), r["plays"], r["likes"],
             r["shares"], r["comments"], r["author_id"], r["sound_id"], r["sound_title"],
             r["sound_author"], r["sound_original"], r["duration_s"], r["is_ad"])
            for r in records
        ]
        self.db.executemany(
            f"INSERT OR REPLACE INTO observations ({OBS_COLS}) VALUES ({','.join('?' * 19)})", rows)
        self.db.execute("DELETE FROM errors WHERE run_id=?", (run_id,))  # save() can repeat
        self.db.executemany(
            "INSERT INTO errors VALUES (?,?,?,?,?)",
            [(run_id, e["scraped_at"], e["category"], e["errorCode"], e["error"]) for e in errors])
        self.db.executemany(
            "INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?,?)",
            [(run_id, p["scraped_at"], p["kind"], p["key"], p["title"], p["video_count"],
              p["view_count"]) for p in pages])
        self.db.commit()
        out = self.dir / "runs" / f"{run_id}.jsonl"
        out.parent.mkdir(exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps({"type": "video", **r}, ensure_ascii=False) + "\n")
            for p in pages:
                f.write(json.dumps({"type": "page", **p}, ensure_ascii=False) + "\n")
            for e in errors:
                f.write(json.dumps({"type": "error", **e}, ensure_ascii=False) + "\n")
        return out
