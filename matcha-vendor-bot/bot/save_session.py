"""
One-time Facebook login.

Opens a real browser window so you log in yourself — the bot never sees or
stores your password. What gets saved is the resulting session cookie, in
fb_session.json, which the scraper reuses on later runs.

    python -m bot.save_session

Re-run this whenever the bot reports that the session expired (typically
every few weeks, or immediately after you change your Facebook password).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SESSION_PATH = PROJECT_ROOT / "fb_session.json"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is not installed. Run:\n"
            "  pip install -r requirements.txt\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        return 1

    print("Opening a browser window…")
    print("1. Log in to Facebook as normal (including any 2FA).")
    print("2. Make sure you can see your News Feed.")
    print("3. Come back here and press Enter.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="en-GB",
        )
        page = context.new_page()
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")

        input("Press Enter once you are logged in… ")

        current = page.url.lower()
        if "login" in current or "checkpoint" in current:
            print(
                "\nStill on a login/checkpoint page — the session was not saved.\n"
                "Finish logging in, then run this again.",
                file=sys.stderr,
            )
            browser.close()
            return 1

        context.storage_state(path=str(SESSION_PATH))
        browser.close()

    # The cookie is a live credential; keep it off other accounts on the box.
    try:
        SESSION_PATH.chmod(0o600)
    except OSError:
        pass

    print(f"\n✅ Session saved to {SESSION_PATH}")
    print("This file is a live login credential — it is gitignored, keep it that way.")
    print("\nNext:  python -m bot.run --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
