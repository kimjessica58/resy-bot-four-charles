#!/usr/bin/env bash
# Wrapper that ensures the Mac stays awake during the entire snipe session.
# Usage: snipe.sh "Restaurant Name"

RESTAURANT="$1"
PROJECT_DIR="/Users/jessicakim/Documents/ResyBot"
PYTHON="$PROJECT_DIR/.venv/bin/python3"
CONFIG="$PROJECT_DIR/config.yaml"
LOG="$PROJECT_DIR/logs/cron.log"

echo "$(date '+%Y-%m-%d %H:%M:%S') [CRON] Starting snipe for: $RESTAURANT" >> "$LOG"

# caffeinate -i prevents idle sleep for the duration of the python process
/usr/bin/caffeinate -i "$PYTHON" -m resybot -c "$CONFIG" --restaurant "$RESTAURANT" >> "$LOG" 2>&1
EXIT_CODE=$?

echo "$(date '+%Y-%m-%d %H:%M:%S') [CRON] Finished: $RESTAURANT (exit=$EXIT_CODE)" >> "$LOG"
