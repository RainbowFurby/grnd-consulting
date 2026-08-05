"""
Entry point. Run once, alert on new matches, exit.

    python -m bot.run                 # normal run
    python -m bot.run --dry-run       # scrape + score, print instead of sending
    python -m bot.run --test-telegram # verify token/chat id, send a test message
    python -m bot.run --score "text"  # score one post from the command line
    python -m bot.run --stats         # what the database knows so far

Exits non-zero when something went wrong, so a scheduler can surface it.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .config import ConfigError, load_config
from .facebook import FacebookScraper, ScrapeError
from .matching import PostMatcher
from .notifier import TelegramError, TelegramNotifier, format_alert, format_run_summary
from .store import SeenStore, fingerprint

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SESSION_PATH = PROJECT_ROOT / "fb_session.json"
DB_PATH = PROJECT_ROOT / "data" / "seen_posts.db"
LOG_PATH = PROJECT_ROOT / "data" / "bot.log"

log = logging.getLogger("vendorbot")


def setup_logging(level: str, verbose: bool) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if verbose else getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )


# --------------------------------------------------------------------------
# Sub-commands
# --------------------------------------------------------------------------

def cmd_test_telegram(cfg) -> int:
    if not cfg.telegram_configured:
        print(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set.\n"
            "Copy .env.example to .env and fill them in (see README step 3).",
            file=sys.stderr,
        )
        return 1

    notifier = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id)
    try:
        username = notifier.verify()
        print(f"✅ Token valid — bot is @{username}")
        notifier.send(
            "🍵 <b>The Everyday Matcha vendor bot</b>\n"
            "Connected. You'll get an alert here whenever a matching "
            "vendor call shows up."
        )
        print(f"✅ Test message sent to chat {cfg.telegram_chat_id}")
        return 0
    except TelegramError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        if "chat not found" in str(exc).lower():
            print(
                "\nThe token works but the chat id is wrong. Add the bot to your "
                "group, send any message there, then visit:\n"
                f"  https://api.telegram.org/bot{cfg.telegram_bot_token}/getUpdates\n"
                "and copy the numeric id from result[].message.chat.id "
                "(group ids start with -).",
                file=sys.stderr,
            )
        return 1


def cmd_score(cfg, text: str) -> int:
    result = PostMatcher(cfg).evaluate(text)
    verdict = "MATCH" if result.passes else "no match"
    print(f"\n{verdict} — score {result.score} ({result.tier})")
    if result.rejected_because:
        print(f"reason: {result.rejected_because}")
    for reason in result.reasons:
        print(f"  {reason}")
    print(f"\nkeywords : {', '.join(result.keyword_hits) or '-'}")
    print(f"organiser: {', '.join(result.organiser_hits) or '-'}")
    print(f"venues   : {', '.join(result.priority_venues + result.known_venues) or '-'}")
    print(f"areas    : {', '.join(result.areas) or '-'}")
    print(f"dates    : {result.date_info.describe() or '-'}")
    fee = "free" if result.booth_fee_is_free else (
        f"RM{result.booth_fee:.0f}" if result.booth_fee is not None else "-"
    )
    print(f"fee      : {fee}")
    print(f"F&B      : {result.fnb_ok if result.fnb_ok is not None else 'unstated'}")
    return 0


def cmd_stats(store: SeenStore) -> int:
    stats = store.stats()
    print(f"Posts seen    : {stats['total_seen']}")
    print(f"Alerts pushed : {stats['total_alerted']}")
    print(f"Database      : {DB_PATH}")
    return 0


# --------------------------------------------------------------------------
# Main run
# --------------------------------------------------------------------------

def run_once(cfg, dry_run: bool = False) -> int:
    store = SeenStore(DB_PATH)
    matcher = PostMatcher(cfg)
    notifier = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id, dry_run=dry_run)

    if not dry_run and not cfg.telegram_configured:
        log.error("Telegram is not configured — run with --dry-run or fill in .env")
        return 1

    checked = 0
    alerted = 0
    errors: list[str] = []

    with FacebookScraper(SESSION_PATH, cfg) as scraper:
        for index, group_url in enumerate(cfg.facebook_groups):
            if index > 0:
                # Spacing requests out is the main thing keeping the account
                # from looking automated.
                time.sleep(cfg.delay_between_groups_seconds)

            try:
                posts, group_name = scraper.fetch_group(group_url)
            except ScrapeError as exc:
                log.error("%s", exc)
                errors.append(str(exc))
                continue

            for post in posts:
                checked += 1
                key = fingerprint(post.text, post.permalink)
                if store.has_seen(key):
                    continue

                result = matcher.evaluate(post.text)

                if result.passes and alerted >= cfg.max_alerts_per_run:
                    log.warning(
                        "Hit max_alerts_per_run (%d) — remaining matches deferred "
                        "to the next run", cfg.max_alerts_per_run
                    )
                    break

                if result.passes:
                    try:
                        notifier.send(format_alert(post, result, group_name))
                        alerted += 1
                        log.info("Alerted: score=%d tier=%s %s",
                                 result.score, result.tier, post.text[:70].replace("\n", " "))
                        time.sleep(1.5)  # stay under Telegram's per-chat rate limit
                    except TelegramError as exc:
                        log.error("Failed to send alert: %s", exc)
                        errors.append(f"telegram: {exc}")
                        # Not recorded as seen, so the next run retries it.
                        continue
                else:
                    log.debug("Skipped (%s): %s",
                              result.rejected_because, post.text[:60].replace("\n", " "))

                store.record(
                    key,
                    group_url,
                    alerted=result.passes,
                    score=result.score,
                    tier=result.tier,
                    snippet=post.text[:200],
                )

    removed = store.prune(cfg.seen_post_retention_days)
    if removed:
        log.debug("Pruned %d expired records", removed)

    log.info("Run complete: %d posts checked, %d alerts, %d error(s)",
             checked, alerted, len(errors))

    # A run that scraped nothing at all is a failure, not a quiet day.
    if checked == 0 and errors:
        if cfg.telegram_configured and not dry_run:
            try:
                notifier.send(format_run_summary(checked, alerted, len(cfg.facebook_groups), errors))
            except TelegramError:
                pass
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bot.run",
        description="Watch Facebook groups for bazaar vendor calls and alert Telegram.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="scrape and score, print alerts instead of sending")
    parser.add_argument("--test-telegram", action="store_true",
                        help="verify Telegram credentials and send a test message")
    parser.add_argument("--score", metavar="TEXT",
                        help="score a single post's text and exit (no scraping)")
    parser.add_argument("--score-file", metavar="PATH", type=Path,
                        help="score the contents of a file and exit")
    parser.add_argument("--stats", action="store_true", help="show database stats and exit")
    parser.add_argument("--config", type=Path, help="path to config.json")
    parser.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"❌ Config error: {exc}", file=sys.stderr)
        return 2

    setup_logging(cfg.log_level, args.verbose)

    if args.test_telegram:
        return cmd_test_telegram(cfg)
    if args.score:
        return cmd_score(cfg, args.score)
    if args.score_file:
        return cmd_score(cfg, args.score_file.read_text(encoding="utf-8"))
    if args.stats:
        return cmd_stats(SeenStore(DB_PATH))

    try:
        return run_once(cfg, dry_run=args.dry_run)
    except ScrapeError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.warning("Interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
