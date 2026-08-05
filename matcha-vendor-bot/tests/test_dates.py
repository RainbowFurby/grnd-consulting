"""Date extraction, using the formats these posts actually use."""

import unittest
from datetime import date

from bot.dates import extract_dates

TODAY = date(2026, 8, 5)  # a Wednesday


class TestWeekendDetection(unittest.TestCase):
    def test_explicit_english_weekend(self):
        self.assertTrue(extract_dates("Join us this weekend!", TODAY).is_weekend)

    def test_explicit_malay_weekend(self):
        self.assertTrue(extract_dates("Bazaar hujung minggu ini", TODAY).is_weekend)

    def test_weekday_names(self):
        self.assertTrue(extract_dates("Sabtu & Ahad, 10am-10pm", TODAY).is_weekend)
        self.assertTrue(extract_dates("Sat/Sun only", TODAY).is_weekend)

    def test_weekday_event_is_not_weekend(self):
        info = extract_dates("Bazaar on Wednesday 12 Aug", TODAY)
        self.assertFalse(info.is_weekend)

    def test_date_that_falls_on_saturday(self):
        # 8 Aug 2026 is a Saturday.
        self.assertTrue(extract_dates("Event on 8 Ogos", TODAY).is_weekend)

    def test_minggu_alone_is_not_a_weekend_claim(self):
        # "minggu depan" = next week, not Sunday.
        info = extract_dates("Kami buka minggu depan", TODAY)
        self.assertFalse(info.mentions_weekend)


class TestDateParsing(unittest.TestCase):
    def test_day_month_english(self):
        self.assertIn(date(2026, 8, 8), extract_dates("8 August", TODAY).dates)

    def test_day_month_malay(self):
        self.assertIn(date(2026, 8, 8), extract_dates("8 Ogos 2026", TODAY).dates)

    def test_malay_haribulan(self):
        self.assertIn(date(2026, 8, 15), extract_dates("15hb Ogos", TODAY).dates)

    def test_month_day_order(self):
        self.assertIn(date(2026, 8, 22), extract_dates("August 22, 2026", TODAY).dates)

    def test_numeric_slash(self):
        self.assertIn(date(2026, 8, 8), extract_dates("8/8", TODAY).dates)

    def test_numeric_full(self):
        self.assertIn(date(2026, 12, 25), extract_dates("25-12-2026", TODAY).dates)

    def test_range_captures_both_ends(self):
        dates = extract_dates("8-9 Aug 2026", TODAY).dates
        self.assertIn(date(2026, 8, 8), dates)
        self.assertIn(date(2026, 8, 9), dates)

    def test_range_with_ampersand(self):
        dates = extract_dates("22 & 23 Ogos", TODAY).dates
        self.assertIn(date(2026, 8, 22), dates)
        self.assertIn(date(2026, 8, 23), dates)

    def test_range_fills_intermediate_days(self):
        dates = extract_dates("7-9 August", TODAY).dates
        self.assertIn(date(2026, 8, 8), dates)

    def test_bare_past_date_rolls_to_next_year(self):
        # Seen in August, "20 Jan" means next January.
        self.assertIn(date(2027, 1, 20), extract_dates("20 Jan", TODAY).dates)

    def test_recent_past_date_stays_in_this_year(self):
        # Within the grace window — last weekend's post, not next year's.
        self.assertIn(date(2026, 7, 25), extract_dates("25 July", TODAY).dates)


class TestFalsePositives(unittest.TestCase):
    def test_opening_hours_are_not_dates(self):
        self.assertEqual(extract_dates("Open 10-6pm daily", TODAY).dates, [])

    def test_time_with_dot_is_not_a_date(self):
        self.assertEqual(extract_dates("Starts at 11.30 am", TODAY).dates, [])

    def test_price_range_is_not_a_date(self):
        self.assertEqual(extract_dates("Booth RM10-15 per day", TODAY).dates, [])

    def test_may_as_a_verb_is_not_a_date(self):
        self.assertEqual(extract_dates("You may 8pm onwards", TODAY).dates, [])


class TestPastEvents(unittest.TestCase):
    def test_past_only(self):
        info = extract_dates("Thanks to everyone who came on 1/8/2026!", TODAY)
        self.assertTrue(info.has_only_past_dates)
        self.assertFalse(info.has_future_date)

    def test_future_present(self):
        info = extract_dates("See you 22 Ogos 2026", TODAY)
        self.assertTrue(info.has_future_date)
        self.assertFalse(info.has_only_past_dates)


class TestDescribe(unittest.TestCase):
    def test_single_date(self):
        self.assertEqual(extract_dates("8 Aug 2026", TODAY).describe(), "8 Aug (Sat)")

    def test_range(self):
        self.assertEqual(extract_dates("8 & 9 Aug 2026", TODAY).describe(), "8-9 Aug (Sat-Sun)")

    def test_weekend_without_date(self):
        self.assertEqual(extract_dates("this weekend!", TODAY).describe(), "weekend (date unclear)")

    def test_nothing(self):
        self.assertEqual(extract_dates("Booth available, DM us", TODAY).describe(), "")


if __name__ == "__main__":
    unittest.main()
