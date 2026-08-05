"""
Facebook group scraping via Playwright.

Reality check on this layer: Facebook's markup is obfuscated and changes
without notice, so treat everything here as best-effort and expect to adjust
the selectors occasionally. The design accounts for that:

  * Several selector strategies are tried in order, not just one.
  * A run that finds zero posts is reported as an error rather than being
    mistaken for "no new posts" — that distinction is the difference between
    a quiet bot and a broken one.
  * Permalinks are extracted when present so dedup keys are real IDs.

The session cookie comes from `save_session.py`, which you run once by hand.
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Tried in order; the first that yields posts wins.
POST_SELECTORS = (
    "div[role='feed'] > div",
    "[role='article']",
    "div[data-pagelet^='GroupsFeed']",
)

_PERMALINK_PATTERNS = (
    re.compile(r"/groups/[^/]+/(?:posts|permalink)/(\d+)"),
    re.compile(r"story_fbid=(\d+)"),
    re.compile(r"/posts/(\d+)"),
)

# Text Facebook injects around the actual post body.
_CHROME_LINES = re.compile(
    r"^(?:like|comment|share|reply|see more|lihat lagi|suka|komen|kongsi|"
    r"all reactions?|top comments?|view \d+ (?:more )?comments?|"
    r"\d+[smhdw]|\d+ (?:min|hr|hour|day|week)s? ago)$",
    re.IGNORECASE,
)

MIN_POST_LENGTH = 60


class ScrapeError(RuntimeError):
    pass


@dataclass
class Post:
    text: str
    url: str
    group_url: str
    permalink: str | None = None


def _clean_post_text(raw: str) -> str:
    """Drop Facebook's UI chrome lines and collapse whitespace."""
    kept = [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and not _CHROME_LINES.match(line.strip())
    ]
    return "\n".join(kept).strip()


def _extract_permalink(element) -> str | None:
    """Find the post's own permalink among its links, if Facebook rendered one."""
    try:
        anchors = element.query_selector_all("a[href*='/groups/']")
    except Exception:  # noqa: BLE001 - element may have detached mid-scroll
        return None

    for anchor in anchors:
        href = anchor.get_attribute("href") or ""
        for pattern in _PERMALINK_PATTERNS:
            if pattern.search(href):
                if href.startswith("/"):
                    href = "https://www.facebook.com" + href
                return href.split("?")[0]
    return None


class FacebookScraper:
    """
    Opens a saved logged-in session and reads recent posts from a group.

    Use as a context manager so the browser always gets closed:

        with FacebookScraper(session_path, cfg) as scraper:
            posts = scraper.fetch_group("https://facebook.com/groups/...")
    """

    def __init__(self, session_path: Path, config) -> None:
        self.session_path = session_path
        self.cfg = config
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "FacebookScraper":
        if not self.session_path.exists():
            raise ScrapeError(
                f"No saved Facebook session at {self.session_path}.\n"
                "Run:  python -m bot.save_session\n"
                "A browser window opens — log in to Facebook, then press Enter."
            )

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.cfg.headless)
        self._context = self._browser.new_context(
            storage_state=str(self.session_path),
            viewport={"width": 1440, "height": 900},
            locale="en-GB",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        return self

    def __exit__(self, *exc_info) -> None:
        # Persist any refreshed cookies so the session lasts longer.
        try:
            if self._context is not None:
                self._context.storage_state(path=str(self.session_path))
        except Exception as exc:  # noqa: BLE001 - never mask the original error
            log.warning("Could not refresh saved session: %s", exc)

        for closeable in (self._context, self._browser):
            try:
                if closeable is not None:
                    closeable.close()
            except Exception:  # noqa: BLE001
                pass
        if self._playwright is not None:
            self._playwright.stop()

    # -- internals -------------------------------------------------------

    def _check_logged_in(self, page) -> None:
        url = page.url.lower()
        if "login" in url or "checkpoint" in url:
            raise ScrapeError(
                "Facebook redirected to login/checkpoint — the saved session has "
                "expired or been flagged. Re-run: python -m bot.save_session"
            )

    def _scroll(self, page) -> None:
        """Scroll in human-ish increments to trigger lazy loading."""
        for _ in range(self.cfg.scroll_rounds):
            page.mouse.wheel(0, random.randint(1400, 2200))
            time.sleep(self.cfg.scroll_pause_seconds + random.uniform(0, 0.8))

    def _collect_elements(self, page) -> list:
        for selector in POST_SELECTORS:
            try:
                elements = page.query_selector_all(selector)
            except Exception as exc:  # noqa: BLE001
                log.debug("Selector %s errored: %s", selector, exc)
                continue
            if len(elements) >= 3:
                log.debug("Using selector %s (%d elements)", selector, len(elements))
                return elements
        return []

    def group_name(self, page) -> str:
        for selector in ("h1", "[role='main'] h1", "title"):
            try:
                element = page.query_selector(selector)
                if element:
                    name = (element.inner_text() or "").strip()
                    if name:
                        return name.split("|")[0].strip()[:80]
            except Exception:  # noqa: BLE001
                continue
        return "Facebook group"

    # -- public ----------------------------------------------------------

    def fetch_group(self, group_url: str) -> tuple[list[Post], str]:
        """Return (posts, group_name) for one group's recent feed."""
        if self._context is None:
            raise ScrapeError("Scraper used outside its context manager")

        page = self._context.new_page()
        try:
            page.goto(group_url, wait_until="domcontentloaded", timeout=60_000)
            self._check_logged_in(page)

            # networkidle rarely settles on Facebook; a fixed settle beats waiting.
            time.sleep(3)
            self._scroll(page)

            name = self.group_name(page)
            elements = self._collect_elements(page)

            if not elements:
                raise ScrapeError(
                    f"No post elements found in {group_url}. Facebook's markup has "
                    "likely changed — update POST_SELECTORS in bot/facebook.py."
                )

            posts: list[Post] = []
            seen_text: set[str] = set()

            for element in elements[: self.cfg.posts_per_group]:
                try:
                    raw = element.inner_text()
                except Exception:  # noqa: BLE001 - detached node during scroll
                    continue

                text = _clean_post_text(raw or "")
                # Short fragments are sidebar widgets and composer boxes.
                if len(text) < MIN_POST_LENGTH or text in seen_text:
                    continue
                seen_text.add(text)

                permalink = _extract_permalink(element)
                posts.append(
                    Post(
                        text=text,
                        url=permalink or group_url,
                        group_url=group_url,
                        permalink=permalink,
                    )
                )

            log.info("Fetched %d usable posts from %s", len(posts), name)
            return posts, name
        finally:
            page.close()
