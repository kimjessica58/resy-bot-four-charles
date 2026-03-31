# ResyBot

A Python-based Resy reservation sniper. Automatically books reservations the moment they become available.

## Features

- **Snipe timing** — waits until the exact second reservations drop
- **Priority preferences** — ranked list of preferred times and table types
- **Retry logic** — polls repeatedly within a configurable timeout window
- **Multiple restaurants** — configure several targets in one YAML file
- **Notifications** — console output + email alerts on success/failure
- **Cron-ready** — designed to run as a scheduled cron job
- **Dry run mode** — test without actually booking

## Setup

### 1. Install

```bash
cd ResyBot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your credentials and restaurant details.

#### Getting your API key and auth token

1. Log into [resy.com](https://resy.com) in your browser
2. Open DevTools (F12) → **Network** tab
3. Navigate to a restaurant page — look for requests to `api.resy.com`
4. From any request headers, copy:
   - `Authorization` header → extract the value after `ResyAPI api_key="`
   - `x-resy-auth-token` header → copy the full value

#### Finding a restaurant's venue ID

Look at the network requests when viewing a restaurant on resy.com — the `venue_id` appears in API call parameters.

### 3. Test (dry run)

```bash
# Set dry_run: true in config.yaml, then:
python -m resybot
```

Check `logs/resybot.log` for output. Use `logging.level: DEBUG` to see raw API responses.

### 4. Schedule with cron

The bot should be triggered ~1 minute before reservations drop. The built-in `wait_until_snipe_time` handles second-level precision.

```bash
# Option A: Use the helper script
chmod +x cron/install_cron.sh
./cron/install_cron.sh "Tatiana" "08:59"

# Option B: Manual crontab entry
crontab -e
# Add:
# 59 8 * * * cd /path/to/ResyBot && /path/to/python3 -m resybot --restaurant "Tatiana" >> logs/cron.log 2>&1
```

### 5. Run for a single restaurant

```bash
python -m resybot --restaurant "Tatiana"
```

## Configuration Reference

See [config.example.yaml](config.example.yaml) for a fully commented example.

| Field | Description |
|---|---|
| `auth.api_key` | Resy API key from browser DevTools |
| `auth.auth_token` | Resy auth token from browser DevTools |
| `settings.retry_timeout_seconds` | How long to retry after snipe time (default: 10) |
| `settings.retry_interval_seconds` | Pause between retries (default: 0.5) |
| `settings.dry_run` | Skip the actual booking call (default: false) |
| `restaurants[].venue_id` | Restaurant ID from resy.com |
| `restaurants[].date` | Target date (YYYY-MM-DD) |
| `restaurants[].party_size` | Number of guests |
| `restaurants[].snipe_time` | When reservations drop (HH:MM:SS) |
| `restaurants[].preferences` | Priority-ordered list of time + optional table_type |

## How It Works

1. **Wait** — sleeps until the configured snipe time
2. **Find** — queries Resy API for available slots
3. **Match** — picks the best slot based on your preference priority list
4. **Book** — grabs booking details and completes the reservation
5. **Retry** — if no match, retries every 0.5s for up to 10s
6. **Notify** — sends success/failure notifications
