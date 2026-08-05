"""
Scoring behaviour, exercised against posts written the way real vendor
calls in Malaysian bazaar groups are written.
"""

import unittest
from datetime import date

from bot.config import Config
from bot.matching import PostMatcher, extract_booth_fee

TODAY = date(2026, 8, 5)

STRONG_CALL = """
📢 CALL FOR VENDORS 📢
Weekend Bazaar @ Sunway Pyramid
Date: 8 & 9 Ogos 2026 (Sabtu & Ahad)
Time: 10am - 10pm
Booth fee: RM250 for 2 days (includes table + 2 chairs)
F&B vendors welcome! Limited slots available.
DM for details or fill in the Google Form below.
"""

MID_CALL = """
Vendor registration open for our community pasar malam in Cheras.
Every Tuesday and Thursday. Booth RM60 per night.
WhatsApp us to book your lapak.
"""

NO_FNB = """
Calling all vendors! Preloved Fashion Bazaar at Publika, 22-23 August 2026.
Booth fee RM180. Fashion and preloved only, no F&B allowed.
"""

VENDOR_HUNTING = """
Hi all, any bazaar happening this weekend around KL? Looking for a booth
for my drinks business. Thanks!
"""

PAST_EVENT = """
Thank you to all our vendors who joined the bazaar at Mid Valley on
1 & 2 August 2026! See you next time.
"""

CHITCHAT = """
Selling my second hand booth tent, used twice only. RM150 nego. WTS.
"""


def make_config(**overrides) -> Config:
    cfg = Config(facebook_groups=["https://www.facebook.com/groups/1"])
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


class TestBoothFee(unittest.TestCase):
    def test_plain_amount(self):
        self.assertEqual(extract_booth_fee("Booth fee RM250")[0], 250.0)

    def test_with_space_and_decimals(self):
        self.assertEqual(extract_booth_fee("Fee: RM 199.50 per day")[0], 199.5)

    def test_thousands_separator(self):
        self.assertEqual(extract_booth_fee("Premium booth RM1,200")[0], 1200.0)

    def test_lowest_amount_wins(self):
        # Organisers quote the cheapest tier first; upgrades follow.
        self.assertEqual(extract_booth_fee("RM150 small / RM300 large")[0], 150.0)

    def test_free_booth(self):
        amount, is_free = extract_booth_fee("FOC booth for the first 10 vendors")
        self.assertTrue(is_free)
        self.assertEqual(amount, 0.0)

    def test_malay_free(self):
        self.assertTrue(extract_booth_fee("Penyertaan percuma!")[1])

    def test_prize_money_is_not_a_fee(self):
        self.assertIsNone(extract_booth_fee("Win prizes worth RM5,000!")[0])

    def test_no_amount(self):
        self.assertIsNone(extract_booth_fee("DM for booth pricing")[0])


class TestGates(unittest.TestCase):
    def setUp(self):
        self.matcher = PostMatcher(make_config())

    def test_strong_call_passes(self):
        result = self.matcher.evaluate(STRONG_CALL, TODAY)
        self.assertTrue(result.passes)
        self.assertEqual(result.tier, "hot")

    def test_vendor_hunting_is_dropped(self):
        result = self.matcher.evaluate(VENDOR_HUNTING, TODAY)
        self.assertFalse(result.passes)
        self.assertIn("excluded by phrase", result.rejected_because)

    def test_fnb_excluded_is_dropped(self):
        result = self.matcher.evaluate(NO_FNB, TODAY)
        self.assertFalse(result.passes)
        self.assertIn("F&B excluded", result.rejected_because)

    def test_past_event_is_dropped(self):
        result = self.matcher.evaluate(PAST_EVENT, TODAY)
        self.assertFalse(result.passes)
        self.assertEqual(result.rejected_because, "all dates already passed")

    def test_unrelated_post_is_dropped(self):
        result = self.matcher.evaluate(CHITCHAT, TODAY)
        self.assertFalse(result.passes)

    def test_no_keywords_at_all(self):
        result = self.matcher.evaluate("Good morning everyone, have a nice day!", TODAY)
        self.assertEqual(result.rejected_because, "no vendor/bazaar keywords")


class TestOptionalGates(unittest.TestCase):
    def test_require_weekend_drops_weekday_event(self):
        matcher = PostMatcher(make_config(require_weekend=True))
        result = matcher.evaluate(MID_CALL, TODAY)
        self.assertFalse(result.passes)
        self.assertEqual(result.rejected_because, "no weekend date found")

    def test_weekday_event_passes_when_weekend_not_required(self):
        result = PostMatcher(make_config()).evaluate(MID_CALL, TODAY)
        self.assertTrue(result.passes)

    def test_require_location_drops_unplaced_post(self):
        matcher = PostMatcher(make_config(require_location=True))
        text = "Call for vendors! Weekend bazaar, booth RM100. DM for details."
        self.assertFalse(matcher.evaluate(text, TODAY).passes)

    def test_over_budget_dropped_when_configured(self):
        matcher = PostMatcher(make_config(max_booth_fee=100, drop_over_budget=True))
        result = matcher.evaluate(STRONG_CALL, TODAY)
        self.assertFalse(result.passes)
        self.assertIn("over budget", result.rejected_because)

    def test_over_budget_only_penalised_by_default(self):
        matcher = PostMatcher(make_config(max_booth_fee=100))
        result = matcher.evaluate(STRONG_CALL, TODAY)
        self.assertTrue(result.passes)
        self.assertTrue(any("over budget" in r for r in result.reasons))


class TestSignals(unittest.TestCase):
    def setUp(self):
        self.matcher = PostMatcher(make_config())

    def test_priority_venue_detected(self):
        result = self.matcher.evaluate(STRONG_CALL, TODAY)
        self.assertIn("Sunway Pyramid", result.priority_venues)

    def test_area_detected_without_venue(self):
        result = self.matcher.evaluate(MID_CALL, TODAY)
        self.assertIn("Cheras", result.areas)

    def test_fnb_positive(self):
        self.assertTrue(self.matcher.evaluate(STRONG_CALL, TODAY).fnb_ok)

    def test_organiser_signal_detected(self):
        self.assertTrue(self.matcher.evaluate(STRONG_CALL, TODAY).organiser_hits)

    def test_priority_venue_outscores_plain_area(self):
        strong = self.matcher.evaluate(STRONG_CALL, TODAY).score
        mid = self.matcher.evaluate(MID_CALL, TODAY).score
        self.assertGreater(strong, mid)

    def test_reasons_are_populated(self):
        result = self.matcher.evaluate(STRONG_CALL, TODAY)
        self.assertTrue(result.reasons)
        self.assertTrue(any("priority venue" in r for r in result.reasons))

    def test_tier_thresholds(self):
        weak = "Bazaar booth available soon, stay tuned for more info from us."
        self.assertEqual(self.matcher.evaluate(weak, TODAY).tier, "maybe")


if __name__ == "__main__":
    unittest.main()
