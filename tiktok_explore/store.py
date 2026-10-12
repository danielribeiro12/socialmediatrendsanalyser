"""Save scrape results to SQLite (for trend tracking) and JSONL (raw export)."""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    run_id TEXT, video_id TEXT, url TEXT, category TEXT, scraped_at TEXT,
    created_at TEXT, caption TEXT, hashtags TEXT, plays INTEGER, likes INTEGER,
    shares INTEGER, comments INTEGER, author_id TEXT, sound_id TEXT,
    sound_title TEXT, sound_author TEXT, sound_original INTEGER,
    duration_s INTEGER, is_ad INTEGER,
    PRIMARY KEY (run_id, video_id)
);
CREATE TABLE IF NOT EXISTS errors (
    run_id TEXT, scraped_at TEXT, category TEXT, error_code TEXT, error TEXT
);
"""


class Store:
    def __init__(self, data_dir):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.dir / "tiktok.db")
        self.db.executescript(SCHEMA)

    def save(self, run_id, records, errors):
        rows = [
            (run_id, r["video_id"], r["url"], r["category"], r["scraped_at"], r["created_at"],
             r["caption"], json.dumps(r["hashtags"], ensure_ascii=False), r["plays"], r["likes"],
             r["shares"], r["comments"], r["author_id"], r["sound_id"], r["sound_title"],
             r["sound_author"], r["sound_original"], r["duration_s"], r["is_ad"])
            for r in records
        ]
        self.db.executemany(
            "INSERT OR REPLACE INTO observations VALUES (" + ",".join("?" * 19) + ")", rows)
        self.db.executemany(
            "INSERT INTO errors VALUES (?,?,?,?,?)",
            [(run_id, e["scraped_at"], e["category"], e["errorCode"], e["error"]) for e in errors])
        self.db.commit()
        out = self.dir / "runs" / f"{run_id}.jsonl"
        out.parent.mkdir(exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for r in records + errors:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return out
