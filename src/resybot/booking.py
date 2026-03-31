from __future__ import annotations

import logging
import time

from .client import AvailableSlot, BookingConfirmation, ResyClient
from .config import RestaurantConfig, SlotPreference

logger = logging.getLogger(__name__)


def match_best_slot(
    available: list[AvailableSlot],
    preferences: list[SlotPreference],
) -> AvailableSlot | None:
    for pref in preferences:
        for slot in available:
            time_match = slot.time == pref.time
            type_match = pref.table_type is None or slot.table_type == pref.table_type
            if time_match and type_match:
                return slot
    return None


def attempt_booking(
    client: ResyClient,
    restaurant: RestaurantConfig,
    dry_run: bool = False,
    cached_payment_method_id: int | None = None,
    cached_book_tokens: dict[str, str] | None = None,
) -> BookingConfirmation | None:
    """Single attempt: find -> match -> [details] -> book.

    If cached_book_tokens has a token for the matched time, we skip
    the details call entirely (~60ms saved on the critical path).
    Falls back to normal details call if cache misses.
    """
    date = restaurant.get_date()
    t_start = time.perf_counter()

    slots = client.find_reservations(
        venue_id=restaurant.venue_id,
        date=date,
        party_size=restaurant.party_size,
    )
    t_find = time.perf_counter()

    if not slots:
        logger.debug("find: 0 slots in %dms", (t_find - t_start) * 1000)
        return None

    available_times = [s.time for s in slots]
    logger.debug("find: %d slots in %dms — %s", len(slots), (t_find - t_start) * 1000, available_times)

    best = match_best_slot(slots, restaurant.preferences)
    if best is None:
        logger.debug("match: no preference matched available times")
        return None

    logger.debug("match: %s %s", best.time, best.table_type)

    # Try cached book_token first (skips details call)
    book_token = None
    used_cache = False
    if cached_book_tokens:
        book_token = cached_book_tokens.get(best.time)
        if book_token:
            used_cache = True
            logger.debug("cache HIT for %s — skipping details call", best.time)

    if book_token is None:
        details = client.get_details(
            config_id=best.config_id,
            date=date,
            party_size=restaurant.party_size,
        )
        t_details = time.perf_counter()
        logger.debug("cache MISS — details in %dms", (t_details - t_find) * 1000)
        book_token = details.book_token
        if cached_payment_method_id is None:
            cached_payment_method_id = details.payment_method_id

    if dry_run:
        t_end = time.perf_counter()
        logger.info(
            "[DRY RUN] %s | %s %s | %dms | cache=%s",
            restaurant.name, best.time, best.table_type,
            (t_end - t_start) * 1000, used_cache,
        )
        return BookingConfirmation(
            reservation_id="DRY_RUN",
            message=f"Dry run — would book {best.time} {best.table_type}",
        )

    confirmation = client.book(
        book_token=book_token,
        payment_method_id=cached_payment_method_id,
    )
    t_end = time.perf_counter()
    logger.info(
        "BOOKED %s | %s %s | %dms total | cache=%s | token=%s",
        restaurant.name, best.time, best.table_type,
        (t_end - t_start) * 1000, used_cache, confirmation.reservation_id[:20],
    )
    return confirmation
