"""Dedup fingerprinting and the seen-post database."""

import tempfile
import unittest
from pathlib import Path

from bot.store import SeenStore, fingerprint
from bot.venues import VenueMatcher

POST = "CALL FOR VENDORS! Bazaar at Publika this weekend. Booth RM200."


class TestFingerprint(unittest.TestCase):
    def test_same_text_same_key(self):
        self.assertEqual(fingerprint(POST), fingerprint(POST))

    def test_different_text_different_key(self):
        self.assertNotEqual(fingerprint(POST), fingerprint(POST + " Extra info here."))

    def test_reaction_counts_do_not_change_the_key(self):
        # The same post re-read an hour later carries different chrome.
        first = fingerprint(POST + "\n12 likes 3 comments\n2h")
        later = fingerprint(POST + "\n48 likes 9 comments\n5h")
        self.assertEqual(first, later)

    def test_see_more_does_not_change_the_key(self):
        self.assertEqual(fingerprint(POST), fingerprint(POST + " See more"))

    def test_permalink_wins_over_text(self):
        url = "https://www.facebook.com/groups/123/posts/456/"
        self.assertEqual(fingerprint(POST, url), fingerprint("totally different", url))

    def test_permalink_query_string_ignored(self):
        base = "https://www.facebook.com/groups/123/posts/456"
        self.assertEqual(fingerprint("", base), fingerprint("", base + "?ref=share"))


class TestSeenStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = SeenStore(Path(self._tmp.name) / "seen.db")

    def tearDown(self):
        self._tmp.cleanup()

    def test_unseen_then_seen(self):
        key = fingerprint(POST)
        self.assertFalse(self.store.has_seen(key))
        self.store.record(key, "https://facebook.com/groups/1", alerted=True, score=20)
        self.assertTrue(self.store.has_seen(key))

    def test_recording_twice_is_harmless(self):
        key = fingerprint(POST)
        self.store.record(key, "g", alerted=True, score=20)
        self.store.record(key, "g", alerted=False, score=1)
        self.assertEqual(self.store.stats()["total_seen"], 1)
        # The first outcome is kept — a post is not "un-alerted" by a re-read.
        self.assertEqual(self.store.stats()["total_alerted"], 1)

    def test_stats_count_alerts_separately(self):
        self.store.record("a", "g", alerted=True, score=20)
        self.store.record("b", "g", alerted=False, score=2)
        self.assertEqual(self.store.stats(), {"total_seen": 2, "total_alerted": 1})

    def test_prune_keeps_recent_records(self):
        self.store.record("a", "g", alerted=True)
        self.assertEqual(self.store.prune(retention_days=60), 0)
        self.assertTrue(self.store.has_seen("a"))

    def test_survives_reopen(self):
        # Retention is the whole point: the set-slicing approach in the
        # reference script forgot posts arbitrarily and re-alerted them.
        self.store.record("a", "g", alerted=True)
        reopened = SeenStore(self.store.db_path)
        self.assertTrue(reopened.has_seen("a"))


class TestVenueMatcher(unittest.TestCase):
    def setUp(self):
        self.matcher = VenueMatcher()

    def test_priority_venue(self):
        hits = self.matcher.match("Bazaar at Sunway Pyramid this weekend")
        self.assertIn("Sunway Pyramid", hits["priority"])

    def test_case_and_spacing_tolerant(self):
        hits = self.matcher.match("held at  mid   valley  megamall")
        self.assertIn("Mid Valley", hits["priority"])

    def test_area_only(self):
        hits = self.matcher.match("Pop up market in Shah Alam")
        self.assertIn("Shah Alam", hits["areas"])

    def test_alias_resolves_to_canonical_name(self):
        hits = self.matcher.match("Vendor call at 1U next month")
        self.assertIn("1 Utama", hits["priority"])

    def test_short_alias_not_matched_inside_word(self):
        # "kl" must not fire on "Klang"; "Klang" is its own area entry.
        hits = self.matcher.match("Bazaar in Klang town centre")
        self.assertNotIn("Kuala Lumpur", hits["areas"])

    def test_extra_venues_are_honoured(self):
        matcher = VenueMatcher(extra_venues=["Gurney Plaza"])
        self.assertIn("Gurney Plaza", matcher.match("Booth at Gurney Plaza")["known"])

    def test_no_match(self):
        hits = self.matcher.match("Online bazaar, no physical booth")
        self.assertEqual(hits, {"priority": [], "known": [], "areas": []})


if __name__ == "__main__":
    unittest.main()
