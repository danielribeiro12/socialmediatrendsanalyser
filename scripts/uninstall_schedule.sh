#!/bin/bash
for LABEL in com.tiktokanalyser.explore com.tiktokanalyser.track com.tiktokanalyser.scrape; do
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
done
echo "Schedule removed."
