"""Config loading, validation, and alert formatting."""

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from bot.config import Config, ConfigError, load_config
from bot.facebook import Post, _clean_post_text
from bot.matching import PostMatcher
from bot.notifier import format_alert

VALID = {"facebook_groups": ["https://www.facebook.com/groups/123456"]}


class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.env_path = self.dir / ".env"
        for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            os.environ.pop(key, None)

    def tearDown(self):
        self._tmp.cleanup()
        for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            os.environ.pop(key, None)

    def write(self, data: dict) -> Path:
        path = self.dir / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_valid_config(self):
        cfg = load_config(self.write(VALID), self.env_path)
        self.assertEqual(cfg.facebook_groups, VALID["facebook_groups"])
        self.assertFalse(cfg.telegram_configured)

    def test_missing_file(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config(self.dir / "nope.json", self.env_path)
        self.assertIn("No config file", str(ctx.exception))

    def test_malformed_json(self):
        path = self.dir / "config.json"
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_config(path, self.env_path)

    def test_unknown_key_is_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config(self.write({**VALID, "weekend_only": True}), self.env_path)
        self.assertIn("weekend_only", str(ctx.exception))

    def test_secrets_in_config_are_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config(self.write({**VALID, "telegram_bot_token": "123:abc"}), self.env_path)
        self.assertIn(".env", str(ctx.exception))

    def test_empty_group_list(self):
        with self.assertRaises(ConfigError):
            load_config(self.write({"facebook_groups": []}), self.env_path)

    def test_non_group_url_rejected(self):
        bad = {"facebook_groups": ["https://www.facebook.com/marketplace/kl"]}
        with self.assertRaises(ConfigError) as ctx:
            load_config(self.write(bad), self.env_path)
        self.assertIn("do not look like Facebook group URLs", str(ctx.exception))

    def test_incoherent_thresholds_rejected(self):
        bad = {**VALID, "min_score": 20, "good_score": 10, "hot_score": 5}
        with self.assertRaises(ConfigError):
            load_config(self.write(bad), self.env_path)

    def test_env_file_supplies_secrets(self):
        self.env_path.write_text(
            "TELEGRAM_BOT_TOKEN=123:abc\nTELEGRAM_CHAT_ID=-1009876\n", encoding="utf-8"
        )
        cfg = load_config(self.write(VALID), self.env_path)
        self.assertTrue(cfg.telegram_configured)
        self.assertEqual(cfg.telegram_chat_id, "-1009876")

    def test_real_env_var_beats_env_file(self):
        os.environ["TELEGRAM_CHAT_ID"] = "-1001111"
        self.env_path.write_text("TELEGRAM_CHAT_ID=-1002222\n", encoding="utf-8")
        cfg = load_config(self.write(VALID), self.env_path)
        self.assertEqual(cfg.telegram_chat_id, "-1001111")

    def test_shipped_config_is_valid(self):
        # The committed config.json must always load cleanly.
        shipped = Path(__file__).resolve().parent.parent / "config.json"
        cfg = load_config(shipped, self.env_path)
        self.assertTrue(cfg.facebook_groups)


class TestPostCleaning(unittest.TestCase):
    def test_chrome_lines_removed(self):
        raw = "CALL FOR VENDORS\nBazaar at Publika\nLike\nComment\nShare\n3h\nSee more"
        self.assertEqual(_clean_post_text(raw), "CALL FOR VENDORS\nBazaar at Publika")

    def test_body_preserved(self):
        raw = "Vendor call\n\nBooth RM120\nDM us"
        self.assertEqual(_clean_post_text(raw), "Vendor call\nBooth RM120\nDM us")


class TestAlertFormatting(unittest.TestCase):
    def setUp(self):
        self.matcher = PostMatcher(Config(facebook_groups=["x"]))

    def test_alert_contains_the_essentials(self):
        text = (
            "CALL FOR VENDORS! Weekend bazaar at Sunway Pyramid, 8 & 9 Ogos 2026. "
            "Booth fee RM250. F&B welcome. DM for details."
        )
        post = Post(text=text, url="https://facebook.com/groups/1/posts/2", group_url="g")
        message = format_alert(post, self.matcher.evaluate(text, date(2026, 8, 5)), "KL Bazaar Group")

        self.assertIn("Sunway Pyramid", message)
        self.assertIn("RM250", message)
        self.assertIn("8-9 Aug", message)
        self.assertIn("KL Bazaar Group", message)
        self.assertIn("https://facebook.com/groups/1/posts/2", message)

    def test_html_in_post_is_escaped(self):
        text = "Call for vendors <b>bazaar</b> & booth at Publika RM100, F&B ok"
        post = Post(text=text, url="https://x/1", group_url="g")
        message = format_alert(post, self.matcher.evaluate(text, date(2026, 8, 5)), "Group & Co")

        self.assertIn("&lt;b&gt;bazaar&lt;/b&gt;", message)
        self.assertIn("Group &amp; Co", message)

    def test_long_post_is_truncated(self):
        text = "Call for vendors at Publika. " + ("padding words here. " * 200)
        post = Post(text=text, url="https://x/1", group_url="g")
        message = format_alert(post, self.matcher.evaluate(text, date(2026, 8, 5)), "G")
        self.assertLess(len(message), 4096)
        self.assertIn("…", message)


if __name__ == "__main__":
    unittest.main()
