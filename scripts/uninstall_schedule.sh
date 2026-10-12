#!/bin/bash
LABEL="com.tiktokanalyser.scrape"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Schedule removed."
