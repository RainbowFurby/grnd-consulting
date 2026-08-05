"""
Configuration loading.

Two sources, deliberately separated:

  .env         — secrets only (Telegram token, chat id). Never committed.
  config.json  — behaviour: which groups to watch, filters, thresholds.
                 Safe to commit, safe to share, safe to tweak often.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .matching import (
    DEFAULT_EXCLUSIONS,
    DEFAULT_ORGANISER_SIGNALS,
    DEFAULT_VENDOR_KEYWORDS,
)
from .venues import PRIORITY_VENUES

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


class ConfigError(RuntimeError):
    """Raised when configuration is missing or unusable."""


@dataclass
class Config:
    # --- secrets (from .env) ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- sources ---
    facebook_groups: list[str] = field(default_factory=list)

    # --- filter vocabulary ---
    vendor_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_VENDOR_KEYWORDS))
    organiser_signals: list[str] = field(default_factory=lambda: list(DEFAULT_ORGANISER_SIGNALS))
    exclusion_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUSIONS))
    priority_venues: list[str] = field(default_factory=lambda: list(PRIORITY_VENUES))
    extra_venues: list[str] = field(default_factory=list)
    extra_areas: list[str] = field(default_factory=list)

    # --- gates ---
    min_keyword_matches: int = 1
    require_weekend: bool = False
    require_location: bool = False
    drop_fnb_excluded: bool = True
    drop_past_events: bool = True
    drop_over_budget: bool = False

    # --- scoring ---
    min_score: int = 8
    good_score: int = 12
    hot_score: int = 17
    max_booth_fee: float | None = 400.0

    # --- scraping behaviour ---
    posts_per_group: int = 25
    scroll_rounds: int = 5
    scroll_pause_seconds: float = 2.0
    headless: bool = True
    delay_between_groups_seconds: float = 30.0
    max_alerts_per_run: int = 8

    # --- housekeeping ---
    seen_post_retention_days: int = 60
    log_level: str = "INFO"

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


def _load_env_file(path: Path) -> None:
    """
    Read a .env file into os.environ without overwriting real env vars.

    Kept dependency-free so the bot still starts if python-dotenv was not
    installed; real env vars always win, which is what you want when running
    under launchd/systemd with the secrets injected.
    """
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_KNOWN_KEYS = {f.name for f in Config.__dataclass_fields__.values()}


def load_config(
    config_path: Path | None = None,
    env_path: Path | None = None,
) -> Config:
    """Build a Config from config.json + .env, validating what matters."""
    config_path = config_path or DEFAULT_CONFIG_PATH
    _load_env_file(env_path or DEFAULT_ENV_PATH)

    if not config_path.exists():
        raise ConfigError(
            f"No config file at {config_path}. Copy config.example.json to "
            "config.json and fill in your Facebook group URLs."
        )

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path} is not valid JSON: {exc}") from exc

    unknown = set(raw) - _KNOWN_KEYS
    if unknown:
        raise ConfigError(
            f"Unrecognised key(s) in {config_path.name}: {', '.join(sorted(unknown))}"
        )

    # config.json is committed to git; secrets must never live there.
    leaked = {"telegram_bot_token", "telegram_chat_id"} & set(raw)
    if leaked:
        raise ConfigError(
            f"{', '.join(sorted(leaked))} must go in .env, not {config_path.name} "
            "— config.json is tracked in git and would leak your bot token."
        )

    cfg = Config(**raw)
    cfg.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    cfg.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not cfg.facebook_groups:
        raise ConfigError(
            "config.json lists no facebook_groups. Add at least one group URL, "
            "e.g. https://www.facebook.com/groups/123456789"
        )

    bad_urls = [u for u in cfg.facebook_groups if "facebook.com/groups/" not in u]
    if bad_urls:
        raise ConfigError(
            "These entries do not look like Facebook group URLs: "
            + ", ".join(bad_urls)
        )

    if cfg.good_score < cfg.min_score or cfg.hot_score < cfg.good_score:
        raise ConfigError(
            "Score thresholds must satisfy min_score <= good_score <= hot_score "
            f"(got {cfg.min_score}, {cfg.good_score}, {cfg.hot_score})"
        )

    return cfg
