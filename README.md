# TikTok Explore scraper

Our own logged-out scraper for TikTok's Explore page. It opens the page in a
real browser, picks a category, scrolls, and saves the video data TikTok loads.
Every run is stored in `data/tiktok.db` so trends can be tracked over time, plus
a raw `data/runs/<run_id>.jsonl` export.

## Setup (once, in Terminal)

    cd ~/Desktop/"Personal Code"/tiktokanalyser
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python -m playwright install chromium

## Run

    source .venv/bin/activate
    python -m tiktok_explore.scraper                      # "All" feed, 50 videos
    python -m tiktok_explore.scraper --all                # every Explore category, 50 each
    python -m tiktok_explore.scraper "Comedy" "Singing & Dancing" --max-items 50
    python -m tiktok_explore.scraper --show               # watch the browser (use if results are empty)
    python -m tiktok_explore.report                       # top hashtags and sounds from the latest run

## Scheduled runs (11:00 and 23:00 daily)

    bash scripts/install_schedule.sh       # install
    bash scripts/uninstall_schedule.sh     # remove

Log: `~/Library/Logs/tiktokanalyser.log`. If the Mac is asleep at run time, the
job runs when it wakes; if it's shut down, that run is skipped.

## Fields per video

video_id, url, category, scraped_at, created_at, caption, hashtags, plays,
likes, shares, comments, author_id (only to de-duplicate), sound_id,
sound_title, sound_author, sound_original, duration_s, is_ad.

Failures are saved as error entries (`CATEGORY_NOT_FOUND`, `EXPLORE_EMPTY`,
`SCRAPE_FAILED`) instead of being skipped.

Keep it gentle: logged out, a couple of runs a day.
