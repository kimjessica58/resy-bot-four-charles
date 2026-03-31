#!/usr/bin/env bash
#
# install_cron.sh — Add a ResyBot cron entry.
#
# Usage:
#   ./cron/install_cron.sh "Tatiana" "08:59"
#   ./cron/install_cron.sh "Don Angie" "08:59" "/path/to/config.yaml"
#
# This schedules: at HH:MM every day, run resybot for the given restaurant.
# Set the time to ~1 minute before the restaurant's snipe_time so the bot
# can sleep until the exact second.

set -euo pipefail

RESTAURANT="${1:?Usage: $0 <restaurant-name> <HH:MM> [config-path]}"
CRON_TIME="${2:?Usage: $0 <restaurant-name> <HH:MM> [config-path]}"
CONFIG="${3:-config.yaml}"

MINUTE="${CRON_TIME##*:}"
HOUR="${CRON_TIME%%:*}"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"

CRON_CMD="${MINUTE} ${HOUR} * * * cd ${PROJECT_DIR} && ${PYTHON} -m resybot -c ${CONFIG} --restaurant \"${RESTAURANT}\" >> logs/cron.log 2>&1"

# Check if entry already exists
if crontab -l 2>/dev/null | grep -F "resybot" | grep -qF "${RESTAURANT}"; then
    echo "Cron entry for '${RESTAURANT}' already exists. Remove it first with: crontab -e"
    exit 1
fi

# Append to existing crontab
(crontab -l 2>/dev/null; echo "${CRON_CMD}") | crontab -

echo "Installed cron entry:"
echo "  ${CRON_CMD}"
echo ""
echo "Verify with: crontab -l"
