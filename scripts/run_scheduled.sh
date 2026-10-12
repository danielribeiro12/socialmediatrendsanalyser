#!/bin/bash
# Called by the scheduled job. Scrapes every Explore category.
set -u
cd "$(dirname "$0")/.." || exit 1
source .venv/bin/activate || exit 1
echo "=== $(date) ==="
python -m tiktok_explore.scraper --all --track --max-items 50 --fallback-show
echo "=== done $(date) ==="
