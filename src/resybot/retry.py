from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

from .booking import attempt_booking
from .client import BookingConfirmation, ResyClient
from .config import RestaurantConfig, Settings

logger = logging.getLogger(__name__)

# Start sniping this many ms BEFORE the exact snipe second.
EARLY_START_MS = 250


def _seconds_until(snipe_time_str: str) -> float:
    """Return seconds until snipe time. If it's already past today, target tomorrow."""
    now = datetime.now()
    h, m, s = (int(x) for x in snipe_time_str.split(":"))
    target = now.replace(hour=h, minute=m, second=s, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _find_nearby_date_with_slots(
    client: ResyClient, venue_id: int, party_size: int, target_date: str,
) -> str | None:
    """Find a nearby date that has available slots to learn the schedule_id."""
    target = date.fromisoformat(target_date)
    for offset in range(1, 10):
        check = (target - timedelta(days=offset)).isoformat()
        try:
            slots = client.find_reservations(venue_id, check, party_size)
            if slots:
                logger.info("PREP nearby_date=%s has %d slots", check, len(slots))
                return check
        except Exception:
            pass
    return None


def retry_booking(
    client: ResyClient,
    restaurant: RestaurantConfig,
    settings: Settings,
) -> BookingConfirmation | None:
    target_date = restaurant.get_date()
    pref_times = [p.time for p in restaurant.preferences]
    t_session_start = time.perf_counter()

    logger.info("=" * 60)
    logger.info("SESSION START: %s", datetime.now().isoformat())
    logger.info("  restaurant:  %s (venue_id=%d)", restaurant.name, restaurant.venue_id)
    logger.info("  target_date: %s", target_date)
    logger.info("  party_size:  %d", restaurant.party_size)
    logger.info("  snipe_time:  %s", restaurant.snipe_time)
    logger.info("  dry_run:     %s", settings.dry_run)
    logger.info("  preferences: %s", pref_times)
    logger.info("  timeout:     %ss", settings.retry_timeout_seconds)
    logger.info("=" * 60)

    # --- PRE-SNIPE PREPARATION ---
    # Use polling sleep instead of one long sleep — survives laptop sleep/wake.
    # Checks the real clock every 5 seconds so we never oversleep.
    wait = _seconds_until(restaurant.snipe_time)
    if wait > 30:
        logger.info("PREP waiting %.0fs until 30s before snipe (polling)", wait - 30)
        while _seconds_until(restaurant.snipe_time) > 30:
            time.sleep(min(5.0, _seconds_until(restaurant.snipe_time) - 30))

    # 1. Warm connection
    t0 = time.perf_counter()
    client.warm_up()
    logger.info("PREP warm_up: %dms", (time.perf_counter() - t0) * 1000)

    # 2. Pre-fetch payment method
    t0 = time.perf_counter()
    cached_pm_id = client.get_payment_method_id()
    logger.info("PREP payment_method: id=%s %dms", cached_pm_id, (time.perf_counter() - t0) * 1000)

    # 3. Learn schedule_id from nearby available date
    cached_book_tokens: dict[str, str] = {}

    t0 = time.perf_counter()
    nearby = _find_nearby_date_with_slots(
        client, restaurant.venue_id, restaurant.party_size, target_date,
    )
    logger.info("PREP find_nearby: date=%s %dms", nearby, (time.perf_counter() - t0) * 1000)

    if nearby:
        t0 = time.perf_counter()
        result = client.learn_schedule_id(
            restaurant.venue_id, restaurant.party_size, nearby,
        )
        schedule_id, table_type = result if result else (None, None)
        logger.info("PREP learn_schedule_id: id=%s type=%s %dms", schedule_id, table_type, (time.perf_counter() - t0) * 1000)

        if schedule_id:
            # 4. Pre-fetch book_tokens for all preferred times
            t0 = time.perf_counter()
            cached_book_tokens = client.prefetch_book_tokens(
                venue_id=restaurant.venue_id,
                schedule_id=schedule_id,
                party_size=restaurant.party_size,
                target_date=target_date,
                times=pref_times,
                table_type=table_type or "Dining Room",
            )
            cached_times = list(cached_book_tokens.keys())
            logger.info("PREP prefetch_tokens: %d/%d cached=%s %dms", len(cached_book_tokens), len(pref_times), cached_times, (time.perf_counter() - t0) * 1000)
    else:
        logger.warning("PREP no nearby date with slots — using normal flow (no cached tokens)")

    # Re-warm connection
    t0 = time.perf_counter()
    client.warm_up()
    logger.info("PREP re-warm: %dms", (time.perf_counter() - t0) * 1000)

    t_prep_done = time.perf_counter()
    logger.info("PREP COMPLETE: total=%dms", (t_prep_done - t_session_start) * 1000)

    # Poll until early start window (also survives sleep/wake)
    early_start = EARLY_START_MS / 1000
    remaining = _seconds_until(restaurant.snipe_time)
    if remaining > early_start:
        logger.info("WAITING %.1fs for snipe time %s", remaining, restaurant.snipe_time)
        while _seconds_until(restaurant.snipe_time) > early_start:
            time.sleep(min(1.0, _seconds_until(restaurant.snipe_time) - early_start))

    # --- SNIPE ---
    t_snipe_start = time.perf_counter()
    snipe_wall_time = datetime.now().isoformat(timespec="milliseconds")
    logger.info("GO! time=%s cached_tokens=%d early_start=%dms", snipe_wall_time, len(cached_book_tokens), EARLY_START_MS)

    deadline = time.monotonic() + settings.retry_timeout_seconds
    attempt = 0
    attempt_log: list[str] = []

    while time.monotonic() < deadline:
        attempt += 1
        t_attempt = time.perf_counter()
        try:
            result = attempt_booking(
                client,
                restaurant,
                dry_run=settings.dry_run,
                cached_payment_method_id=cached_pm_id,
                cached_book_tokens=cached_book_tokens,
            )
            t_done = time.perf_counter()
            elapsed_ms = int((t_done - t_attempt) * 1000)
            offset_ms = int((t_done - t_snipe_start) * 1000)

            if result is not None:
                logger.info("=" * 60)
                logger.info("SUCCESS on attempt %d", attempt)
                logger.info("  result:     %s", result.message)
                logger.info("  attempt_ms: %d", elapsed_ms)
                logger.info("  offset_ms:  %d (since GO)", offset_ms)
                logger.info("  wall_time:  %s", datetime.now().isoformat(timespec="milliseconds"))
                logger.info("  total_attempts: %d", attempt)
                # Dump all attempt timings
                for log_line in attempt_log:
                    logger.info("  %s", log_line)
                logger.info("  #%d: %dms -> SUCCESS", attempt, elapsed_ms)
                logger.info("=" * 60)
                return result

            attempt_log.append(f"#{attempt}: {elapsed_ms}ms @ +{offset_ms}ms -> no_match")

        except Exception as e:
            t_done = time.perf_counter()
            elapsed_ms = int((t_done - t_attempt) * 1000)
            offset_ms = int((t_done - t_snipe_start) * 1000)
            err_str = str(e)[:100]
            attempt_log.append(f"#{attempt}: {elapsed_ms}ms @ +{offset_ms}ms -> ERROR {type(e).__name__}: {err_str}")

            if attempt % 10 == 0:
                logger.exception("Attempt %d failed", attempt)

            # If rate limited (429), exponential backoff
            if "429" in str(e):
                backoff = min(2.0, 0.5 * (2 ** (attempt - 20)))  # 0.5s, 1s, 2s max
                logger.info("Rate limited (429) — backing off %.1fs", backoff)
                time.sleep(backoff)
                continue  # skip the normal delay below

            # If book fails with cached token, it might be stale
            if cached_book_tokens and attempt <= 3:
                logger.info("Clearing cached tokens (may be stale after error)")
                cached_book_tokens = {}

        # 150ms delay between attempts — stays under Resy's ~5 req/s limit
        # even when both local + Render are running simultaneously
        time.sleep(0.15)

    # --- FAILURE ---
    t_end = time.perf_counter()
    logger.error("=" * 60)
    logger.error("FAILED: %s (%s)", restaurant.name, target_date)
    logger.error("  total_attempts: %d in %dms", attempt, (t_end - t_snipe_start) * 1000)
    logger.error("  wall_time: %s", datetime.now().isoformat(timespec="milliseconds"))
    # Dump all attempt timings
    for log_line in attempt_log:
        logger.error("  %s", log_line)
    logger.error("=" * 60)
    return None
