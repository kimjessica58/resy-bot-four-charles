from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    api_key: str
    auth_token: str


class SlotPreference(BaseModel):
    time: str  # "HH:MM:SS" military format
    table_type: str | None = None  # None matches any table type


class RestaurantConfig(BaseModel):
    name: str
    venue_id: int
    date: str | None = None  # "YYYY-MM-DD" — fixed date, or use days_ahead
    days_ahead: int | None = None  # Auto-compute date this many days from today
    party_size: int = Field(ge=1, le=20)
    snipe_time: str  # "HH:MM:SS" when reservations open
    preferences: list[SlotPreference]

    def get_date(self) -> str:
        """Return the target date as YYYY-MM-DD."""
        if self.days_ahead is not None:
            from datetime import date, timedelta

            return (date.today() + timedelta(days=self.days_ahead)).isoformat()
        if self.date is not None:
            return self.date
        raise ValueError(f"Restaurant '{self.name}' needs either 'date' or 'days_ahead'")


class NotificationConfig(BaseModel):
    type: str  # "console", "email"
    smtp_host: str | None = None
    smtp_port: int | None = None
    username: str | None = None
    password: str | None = None
    to: str | None = None


class Settings(BaseModel):
    retry_timeout_seconds: float = 10.0
    retry_interval_seconds: float = 0.5
    dry_run: bool = False


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "logs/resybot.log"


class AppConfig(BaseModel):
    auth: AuthConfig
    settings: Settings = Settings()
    logging: LoggingConfig = LoggingConfig()
    notifications: list[NotificationConfig] = [NotificationConfig(type="console")]
    restaurants: list[RestaurantConfig]


def load_config(path: Path) -> AppConfig:
    """Load and validate config from a YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    return AppConfig(**raw)
