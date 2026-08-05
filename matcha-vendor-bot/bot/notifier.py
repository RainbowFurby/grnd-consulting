"""
Telegram delivery.

Push-only: the bot posts into your group chat and never listens for
commands, so there is no long-running process to keep alive. Config changes
happen in config.json.
"""

from __future__ import annotations

import html
import logging
import time

import requests

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_LENGTH = 4096
BODY_EXCERPT_CHARS = 700


class TelegramError(RuntimeError):
    pass


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, dry_run: bool = False) -> None:
        self.token = token
        self.chat_id = chat_id
        self.dry_run = dry_run

    # -- low level -------------------------------------------------------

    def _call(self, method: str, payload: dict, retries: int = 3) -> dict:
        url = API_BASE.format(token=self.token, method=method)
        delay = 2.0

        for attempt in range(1, retries + 1):
            try:
                resp = requests.post(url, data=payload, timeout=20)
            except requests.RequestException as exc:
                if attempt == retries:
                    raise TelegramError(f"network error calling {method}: {exc}") from exc
                log.warning("Telegram %s failed (%s), retrying in %.0fs", method, exc, delay)
                time.sleep(delay)
                delay *= 2
                continue

            # 429 carries a server-specified cooldown; respect it exactly.
            if resp.status_code == 429:
                wait = float(resp.json().get("parameters", {}).get("retry_after", delay))
                log.warning("Telegram rate limited, waiting %.0fs", wait)
                time.sleep(wait + 1)
                continue

            if resp.ok:
                return resp.json()

            if 500 <= resp.status_code < 600 and attempt < retries:
                log.warning("Telegram %s returned %s, retrying", method, resp.status_code)
                time.sleep(delay)
                delay *= 2
                continue

            raise TelegramError(
                f"{method} failed with HTTP {resp.status_code}: {resp.text[:300]}"
            )

        raise TelegramError(f"{method} failed after {retries} attempts")

    # -- public ----------------------------------------------------------

    def verify(self) -> str:
        """Confirm the token works. Returns the bot's @username."""
        data = self._call("getMe", {})
        return data.get("result", {}).get("username", "unknown")

    def send(self, text: str) -> None:
        if self.dry_run:
            print("\n--- DRY RUN: would send to Telegram ---")
            print(text)
            print("--- end ---\n")
            return

        self._call(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": text[:MAX_MESSAGE_LENGTH],
                "parse_mode": "HTML",
                "disable_web_page_preview": "false",
            },
        )


def _esc(value: str) -> str:
    return html.escape(value, quote=False)


def format_alert(post, result, group_name: str) -> str:
    """
    Build the Telegram message for one matching post.

    Structure is deliberate: tier and date first (decide in one glance),
    then the facts you would otherwise have to read the post for, then the
    post excerpt, then the link.
    """
    lines: list[str] = [f"<b>{_esc(result.tier_label)}</b> · 🍵 vendor call"]

    facts: list[str] = []

    date_label = result.date_info.describe()
    if date_label:
        prefix = "📅" if result.date_info.is_weekend else "🗓"
        facts.append(f"{prefix} {_esc(date_label)}")

    venue = (
        result.priority_venues
        or result.known_venues
        or result.areas
    )
    if venue:
        star = "⭐️" if result.priority_venues else "📍"
        facts.append(f"{star} {_esc(', '.join(venue[:2]))}")

    if result.booth_fee_is_free:
        facts.append("💰 Free booth")
    elif result.booth_fee is not None:
        facts.append(f"💰 from RM{result.booth_fee:.0f}")

    if result.fnb_ok:
        facts.append("🥤 F&amp;B welcome")

    if facts:
        lines.append(" · ".join(facts))

    lines.append("")
    excerpt = post.text.strip()
    if len(excerpt) > BODY_EXCERPT_CHARS:
        excerpt = excerpt[:BODY_EXCERPT_CHARS].rsplit(" ", 1)[0] + "…"
    lines.append(f"<blockquote>{_esc(excerpt)}</blockquote>")
    lines.append("")

    lines.append(f"<i>from {_esc(group_name)}</i>")
    lines.append(f'<a href="{_esc(post.url)}">Open post →</a>')
    lines.append(f"<code>score {result.score}</code>")

    return "\n".join(lines)


def format_run_summary(checked: int, matched: int, groups: int, errors: list[str]) -> str:
    lines = [
        "🍵 <b>Vendor bot run</b>",
        f"Checked {checked} posts across {groups} group(s) · {matched} new match(es)",
    ]
    if errors:
        lines.append("")
        lines.append("<b>Problems:</b>")
        for err in errors[:5]:
            lines.append(f"• {_esc(err)}")
    return "\n".join(lines)
