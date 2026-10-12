"""Turn raw TikTok item JSON into flat records."""
import re
from datetime import datetime, timezone

HASHTAG_RE = re.compile(r"#([\wÀ-￿]+)", re.UNICODE)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def extract_hashtags(item):
    tags = set()
    for ch in item.get("challenges") or []:
        if ch.get("title"):
            tags.add(ch["title"].lower())
    for te in item.get("textExtra") or []:
        if te.get("hashtagName"):
            tags.add(te["hashtagName"].lower())
    for m in HASHTAG_RE.findall(item.get("desc") or ""):
        tags.add(m.lower())
    return sorted(tags)


def parse_item(item, category, scraped_at):
    stats = item.get("stats") or {}
    stats2 = item.get("statsV2") or {}
    author = item.get("author") or {}
    music = item.get("music") or {}
    video = item.get("video") or {}
    vid = str(item.get("id") or "")
    handle = author.get("uniqueId") or ""
    created = _int(item.get("createTime"))

    def stat(key):
        val = _int(stats.get(key))
        return val if val is not None else _int(stats2.get(key))

    return {
        "video_id": vid,
        "url": f"https://www.tiktok.com/@{handle}/video/{vid}" if handle and vid else None,
        "category": category,
        "scraped_at": scraped_at,
        "created_at": datetime.fromtimestamp(created, timezone.utc).isoformat() if created else None,
        "caption": item.get("desc") or "",
        "hashtags": extract_hashtags(item),
        "plays": stat("playCount"),
        "likes": stat("diggCount"),
        "shares": stat("shareCount"),
        "comments": stat("commentCount"),
        "author_id": str(author.get("id") or "") or None,  # kept only to de-duplicate spam
        "sound_id": str(music.get("id") or "") or None,
        "sound_title": music.get("title"),
        "sound_author": music.get("authorName"),
        "sound_original": bool(music.get("original")) if music else None,
        "duration_s": _int(video.get("duration")),
        "is_ad": bool(item.get("isAd")),
    }


# Tags people add to everything; they never signal a specific trend.
GENERIC_TAGS = {
    "fyp", "foryou", "foryoupage", "fy", "fypage", "viral", "viralvideo", "viraltiktok",
    "trending", "trend", "goviral", "explore", "explorepage", "tiktok", "funny", "funnyvideos",
    "comedy", "humor", "humour", "meme", "memes", "capcut", "xyzbca", "parati", "pourtoi",
    "fürdich", "foryourpage", "4u", "4you", "relatable", "lol", "blowthisup", "duet", "stitch",
    "greenscreen", "edit", "edits", "video", "viralvideos", "trendingvideo",
    "creatorsearchinsights", "tiktokviral", "trendingnow", "foryourpage", "xuhuong",
    "xuhuongtiktok", "keşfet", "keşfetteyiz", "рекомендации", "рек", "реки", "рекомендация",
    "врек", "хочуврек", "глобальныерекомендации", "朝", "おすすめ", "おすすめにのりたい",
}


def is_generic(tag):
    return tag in GENERIC_TAGS or tag.startswith("fyp") or tag.startswith("foryou")
