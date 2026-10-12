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
    python -m tiktok_explore.scraper --all --track        # + check hashtag and sound pages
    python -m tiktok_explore.scraper --track-only         # only the hashtag/sound pages
    python -m tiktok_explore.report                       # latest run + fastest-growing sounds/hashtags

## Tracking hashtags and sounds

With `--track`, each run also opens TikTok's page for a set of hashtags and
sounds and records the total number of videos shown there. Comparing those
totals between runs shows what's spreading. Pages checked each run:

- every hashtag in `watchlist.txt` (edit it freely);
- the 10 non-generic hashtags and 20 sounds used by the most different
  creators in the last 3 days of Explore data;
- anything first tracked in the last 7 days, so it keeps a continuous history.

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
`PAGE_EMPTY`, `SCRAPE_FAILED`) instead of being skipped.

Keep it gentle: logged out, a couple of runs a day.

## CAPTCHAs

If TikTok shows a CAPTCHA, the run stops and saves what it already collected
(error code `CAPTCHA`). With `--show`, it waits up to 5 minutes so you can
solve it yourself in the window, then carries on. It doesn't try to get past
CAPTCHAs on its own; if they keep appearing, scrape less often or fewer pages.
