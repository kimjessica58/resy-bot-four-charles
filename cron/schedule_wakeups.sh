#!/usr/bin/env bash
# Schedule macOS wake-ups 2 minutes before each snipe time.
# Run this once daily (or after every reboot).
# pmset can only hold one scheduled wake, so we use repeating entries.

# Cancel any existing scheduled wakeups
sudo pmset repeat cancel 2>/dev/null

# Schedule wake at 8:57 AM, 11:57 AM, and 11:57 PM daily
# pmset repeat only supports one wake time, so we use launchd instead.
# For now, let's set the most critical one.
echo "Note: pmset repeat only supports one wake time."
echo "Setting wake for 8:57 AM (4 Charles)."
echo "For Ha's and Odo, keep Amphetamine running."
sudo pmset repeat wakeorpoweron MTWRFSU 08:57:00
echo "Wake scheduled. Verify with: pmset -g sched"
