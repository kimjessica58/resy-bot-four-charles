from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

try:
    import orjson
    _loads = orjson.loads
except ImportError:
    import json
    _loads = json.loads

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AvailableSlot:
    config_id: str
    time: str  # "HH:MM:SS"
    table_type: str


@dataclass(slots=True)
class BookingDetails:
    book_token: str
    payment_method_id: int


@dataclass(slots=True)
class BookingConfirmation:
    reservation_id: str
    message: str


class ResyApiError(Exception):
    """Raised when a Resy API call fails."""


class ResyClient:
    BASE_URL = "https://api.resy.com"

    def __init__(self, api_key: str, auth_token: str, timeout: float = 10.0) -> None:
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            http2=True,  # ~50% faster than HTTP/1.1 on warm connections
            headers={
                "Authorization": f'ResyAPI api_key="{api_key}"',
                "x-resy-auth-token": auth_token,
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Origin": "https://resy.com",
                "Referer": "https://resy.com/",
            },
            timeout=timeout,
        )
        # Pre-built params and headers for hot path (avoid dict alloc per call)
        self._book_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://widgets.resy.com",
            "Referer": "https://widgets.resy.com/",
        }

    def find_reservations(
        self, venue_id: int, date: str, party_size: int
    ) -> list[AvailableSlot]:
        """GET /4/find — search available reservation slots."""
        resp = self._client.get(
            "/4/find",
            params={
                "lat": 0,
                "long": 0,
                "day": date,
                "party_size": party_size,
                "venue_id": venue_id,
            },
        )
        resp.raise_for_status()
        return self._parse_find_response(_loads(resp.content))

    def get_details(
        self, config_id: str, date: str, party_size: int
    ) -> BookingDetails:
        """GET /3/details — get book token (and payment method as fallback)."""
        resp = self._client.get(
            "/3/details",
            params={
                "config_id": config_id,
                "day": date,
                "party_size": party_size,
            },
        )
        resp.raise_for_status()
        return self._parse_details_response(_loads(resp.content))

    def book(self, book_token: str, payment_method_id: int) -> BookingConfirmation:
        """POST /3/book — finalize the reservation."""
        resp = self._client.post(
            "/3/book",
            data={
                "book_token": book_token,
                "struct_payment_method": f'{{"id":{payment_method_id}}}',
            },
            headers=self._book_headers,
        )
        resp.raise_for_status()
        return self._parse_book_response(_loads(resp.content))

    def warm_up(self) -> None:
        """Pre-warm TCP/TLS + HTTP/2 connection before snipe time."""
        try:
            self._client.get("/1/diagnostics")
            logger.info("Connection pre-warmed (HTTP/2)")
        except Exception:
            logger.debug("Warm-up request failed (non-critical)")

    def get_payment_method_id(self) -> int | None:
        """Pre-fetch payment method ID so we skip parsing it at snipe time."""
        try:
            resp = self._client.get("/2/user")
            resp.raise_for_status()
            pm_id = _loads(resp.content)["payment_methods"][0]["id"]
            logger.info("Pre-fetched payment method ID: %s", pm_id)
            return pm_id
        except Exception:
            logger.debug("Could not pre-fetch payment method")
            return None

    def learn_schedule_id(self, venue_id: int, party_size: int, nearby_date: str) -> str | None:
        """Learn the schedule_id from a nearby available date.

        The config_id token format is:
          rgs://resy/{venue_id}/{schedule_id}/{party_size}/{date}/{date}/{time}/{party_size}/{type}
        The schedule_id changes per venue/date but can be reused
        across dates for speculative details calls.
        """
        try:
            resp = self._client.get("/4/find", params={
                "lat": 0, "long": 0,
                "day": nearby_date,
                "party_size": party_size,
                "venue_id": venue_id,
            })
            resp.raise_for_status()
            data = _loads(resp.content)
            venues = data.get("results", {}).get("venues", [])
            if venues and venues[0].get("slots"):
                token = venues[0]["slots"][0]["config"]["token"]
                schedule_id = token.split("/")[4]
                table_type = venues[0]["slots"][0]["config"].get("type", "Dining Room")
                logger.info("Learned schedule_id=%s, table_type=%s from %s", schedule_id, table_type, nearby_date)
                return schedule_id, table_type
        except Exception:
            logger.debug("Could not learn schedule_id from %s", nearby_date)
        return None, None

    def prefetch_book_tokens(
        self,
        venue_id: int,
        schedule_id: str,
        party_size: int,
        target_date: str,
        times: list[str],
        table_type: str = "Dining Room",
    ) -> dict[str, str]:
        """Pre-fetch book_tokens for preferred times using a known schedule_id.

        Returns a dict of {time: book_token} for times that succeeded.
        These tokens expire in ~5 hours so must be used within the session.
        """
        tokens: dict[str, str] = {}
        for t in times:
            config_id = f"rgs://resy/{venue_id}/{schedule_id}/{party_size}/{target_date}/{target_date}/{t}/{party_size}/{table_type}"
            try:
                resp = self._client.get("/3/details", params={
                    "config_id": config_id,
                    "day": target_date,
                    "party_size": party_size,
                })
                if resp.status_code == 200:
                    bt = _loads(resp.content)["book_token"]["value"]
                    tokens[t] = bt
                    logger.debug("Pre-fetched book_token for %s", t)
            except Exception:
                pass
        logger.info("Pre-fetched %d/%d book tokens", len(tokens), len(times))
        return tokens

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ResyClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # -- Response parsers (kept lean for hot path) --

    @staticmethod
    def _parse_find_response(data: dict) -> list[AvailableSlot]:
        slots: list[AvailableSlot] = []
        try:
            venues = data["results"]["venues"]
            if not venues:
                return slots
            for slot in venues[0]["slots"]:
                config = slot["config"]
                raw_start = slot["date"]["start"]
                slots.append(
                    AvailableSlot(
                        config_id=config["token"],
                        time=raw_start[11:],  # "YYYY-MM-DD HH:MM:SS" -> "HH:MM:SS"
                        table_type=config.get("type", ""),
                    )
                )
        except (KeyError, IndexError, TypeError) as exc:
            logger.error("Failed to parse /4/find response: %s", exc)
        return slots

    @staticmethod
    def _parse_details_response(data: dict) -> BookingDetails:
        try:
            return BookingDetails(
                book_token=data["book_token"]["value"],
                payment_method_id=data["user"]["payment_methods"][0]["id"],
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ResyApiError(f"Failed to parse /3/details: {exc}") from exc

    @staticmethod
    def _parse_book_response(data: dict) -> BookingConfirmation:
        resy_token = data.get("resy_token", "")
        return BookingConfirmation(
            reservation_id=resy_token,
            message=f"Reservation confirmed (token: {resy_token})",
        )
