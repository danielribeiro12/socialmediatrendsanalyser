#!/bin/bash
# Installs two macOS scheduled jobs:
#   11:00  Explore categories   (com.tiktokanalyser.explore)
#   23:00  hashtag/sound pages  (com.tiktokanalyser.track)
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$HOME/Library/Logs/tiktokanalyser.log"
UID_="$(id -u)"
xml() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }

if [ ! -x "$DIR/.venv/bin/python" ]; then
  echo "Set up the .venv first (see README)."; exit 1
fi
chmod +x "$DIR/scripts/run_scheduled.sh"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

# Remove the old single combined job if it's there.
launchctl bootout "gui/$UID_/com.tiktokanalyser.scrape" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.tiktokanalyser.scrape.plist"

install_job() {  # label mode hour
  local label="$1" mode="$2" hour="$3"
  local plist="$HOME/Library/LaunchAgents/$label.plist"
  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$(xml "$DIR/scripts/run_scheduled.sh")</string>
    <string>$mode</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$hour</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$(xml "$LOG")</string>
  <key>StandardErrorPath</key><string>$(xml "$LOG")</string>
</dict>
</plist>
PLIST
  launchctl bootout "gui/$UID_/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_" "$plist"
}

install_job com.tiktokanalyser.explore explore 11
install_job com.tiktokanalyser.track track 23
echo "Scheduled: Explore at 11:00, hashtag/sound tracking at 23:00."
echo "Test now:  launchctl kickstart gui/$UID_/com.tiktokanalyser.track"
echo "Log:       tail -f \"$LOG\""
