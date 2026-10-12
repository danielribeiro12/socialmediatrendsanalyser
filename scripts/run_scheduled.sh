#!/bin/bash
# Called by the scheduled jobs.
#   explore  (11:00): every Explore category
#   track    (23:00): hashtag and sound pages
# Kept separate so TikTok never sees one long burst of page loads.
set -u
MODE="${1:-explore}"
cd "$(dirname "$0")/.." || exit 1
source .venv/bin/activate || exit 1
echo "=== $MODE $(date) ==="
case "$MODE" in
  explore) python -m tiktok_explore.scraper --all --max-items 50 --slow --fallback-show ;;
  track)   python -m tiktok_explore.scraper --track-only --slow ;;
  *)       echo "Unknown mode: $MODE"; exit 1 ;;
esac
echo "=== done $(date) ==="
