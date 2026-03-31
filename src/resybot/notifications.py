from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText

from .client import BookingConfirmation
from .config import NotificationConfig

logger = logging.getLogger(__name__)


class Notifier(ABC):
    @abstractmethod
    def notify_success(self, restaurant_name: str, confirmation: BookingConfirmation) -> None: ...

    @abstractmethod
    def notify_failure(self, restaurant_name: str, reason: str) -> None: ...


class ConsoleNotifier(Notifier):
    def notify_success(self, restaurant_name: str, confirmation: BookingConfirmation) -> None:
        print(f"[SUCCESS] Booked {restaurant_name}: {confirmation.message}")

    def notify_failure(self, restaurant_name: str, reason: str) -> None:
        print(f"[FAILURE] Could not book {restaurant_name}: {reason}")


class EmailNotifier(Notifier):
    def __init__(self, config: NotificationConfig) -> None:
        self.smtp_host = config.smtp_host
        self.smtp_port = config.smtp_port
        self.username = config.username
        self.password = config.password
        self.to = config.to

    def notify_success(self, restaurant_name: str, confirmation: BookingConfirmation) -> None:
        self._send(
            subject=f"ResyBot: Booked {restaurant_name}!",
            body=(
                f"Reservation confirmed.\n"
                f"ID: {confirmation.reservation_id}\n"
                f"{confirmation.message}"
            ),
        )

    def notify_failure(self, restaurant_name: str, reason: str) -> None:
        self._send(
            subject=f"ResyBot: Failed to book {restaurant_name}",
            body=f"Booking failed.\nReason: {reason}",
        )

    def _send(self, subject: str, body: str) -> None:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.username
        msg["To"] = self.to
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            logger.info("Email notification sent to %s", self.to)
        except Exception:
            logger.exception("Failed to send email notification")


def build_notifiers(configs: list[NotificationConfig]) -> list[Notifier]:
    """Build notifier instances from config."""
    notifiers: list[Notifier] = []
    for cfg in configs:
        match cfg.type:
            case "console":
                notifiers.append(ConsoleNotifier())
            case "email":
                notifiers.append(EmailNotifier(cfg))
            case _:
                logger.warning("Unknown notifier type: %s", cfg.type)
    return notifiers


def notify_all(
    notifiers: list[Notifier],
    restaurant_name: str,
    confirmation: BookingConfirmation | None,
    failure_reason: str | None = None,
) -> None:
    """Send success or failure notification to all notifiers."""
    for n in notifiers:
        if confirmation:
            n.notify_success(restaurant_name, confirmation)
        else:
            n.notify_failure(restaurant_name, failure_reason or "Unknown error")
