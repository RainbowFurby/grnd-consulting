"""
Scoring engine: decides whether a Facebook post is a vendor call worth
waking your group chat for.

The shape of the decision:

  1. GATES — hard pass/fail. A post must read as a vendor call, must not be
     someone else *looking* for a booth, must not have already happened, and
     must not explicitly exclude F&B vendors. Any gate failure drops it,
     regardless of how good the rest looks.

  2. SIGNALS — everything else adds or subtracts points: weekend dates, a
     venue you care about, a booth fee inside your budget, explicit F&B or
     drinks welcome, an organiser-sounding call to action.

  3. TIER — the final score maps to 🔥 / ✅ / 👀 so the alert tells you how
     hard to look, rather than every match arriving at the same volume.

Every score carries `reasons`, so when the bot pushes something odd you can
see exactly which rule fired.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .dates import DateInfo, extract_dates
from .venues import VenueMatcher

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

# Words that make a post look like a bazaar/booth opportunity at all.
DEFAULT_VENDOR_KEYWORDS: tuple[str, ...] = (
    "vendor", "bazaar", "bazar", "pop up", "pop-up", "popup", "booth",
    "lapak", "penjaja", "gerai", "stall", "market", "pasar",
    "flea", "carnival", "karnival", "festival", "fair", "expo",
)

# Phrases that say an organiser is actively recruiting. This is the single
# strongest signal that a post is a call and not just event chatter.
DEFAULT_ORGANISER_SIGNALS: tuple[str, ...] = (
    "call for vendor", "calling all vendor", "calling vendors",
    "open for vendor", "open to vendor", "vendor wanted", "wanted vendor",
    "looking for vendor", "seeking vendor", "vendor registration",
    "vendor form", "registration form", "google form", "borang",
    "pendaftaran", "daftar sekarang", "sign up", "signup",
    "slot available", "slots available", "available slot", "limited slot",
    "slot terhad", "slot kosong", "booth available", "booking",
    "dm for details", "pm for details", "wasap", "whatsapp us",
    "jom join", "join us as vendor", "rent a booth", "sewa gerai",
    "sewa lapak", "menjemput", "jemputan", "peniaga dijemput",
)

# Someone hunting for a booth, not offering one. These invert the meaning of
# the vendor keywords, so they are a hard drop.
DEFAULT_EXCLUSIONS: tuple[str, ...] = (
    "looking for bazaar", "looking for a booth", "looking for booth",
    "cari bazaar", "cari lapak", "cari gerai", "cari booth",
    "any bazaar recommend", "recommend any bazaar", "mana ada bazaar",
    "any bazaar happening", "nak join bazaar", "want to join bazaar",
    "wts", "want to sell", "for sale", "used booth", "second hand",
    "hiring", "job vacancy", "jawatan kosong", "part time staff",
    "promoter wanted", "crew wanted",
)

# F&B acceptance. Matcha is a drinks booth, so an event that bans F&B is
# useless no matter how good the venue is.
FNB_POSITIVE: tuple[str, ...] = (
    "f&b", "f & b", "fnb", "food", "beverage", "drinks", "drink",
    "makanan", "minuman", "dessert", "snack", "cafe", "kopi", "coffee",
    "boba", "matcha", "tea", "juice", "bakery", "kuih",
)

FNB_NEGATIVE: tuple[str, ...] = (
    "no f&b", "no fnb", "without f&b", "f&b not allowed", "no food",
    "food not allowed", "tiada makanan", "tanpa makanan", "no drinks",
    "dry goods only", "non-food", "non food", "fashion only",
    "preloved only", "no beverage", "handmade only",
)

# --------------------------------------------------------------------------
# Booth fee
# --------------------------------------------------------------------------

_FEE = re.compile(
    r"(?:rm|myr)\s*(?P<amount>\d{1,3}(?:[,\s]?\d{3})*(?:\.\d{1,2})?)\s*"
    r"(?P<suffix>k\b)?",
    re.IGNORECASE,
)

_FREE_BOOTH = re.compile(
    r"\b(?:foc|free\s+(?:booth|slot|stall|entry|participation)|"
    r"percuma|tiada\s+bayaran|no\s+(?:booth\s+)?fee)\b",
    re.IGNORECASE,
)

# Money that isn't a booth fee — prize pools, sales targets, deposits.
_FEE_FALSE_CONTEXT = re.compile(
    r"\b(?:prize|hadiah|worth|bernilai|sales|jualan|revenue|voucher|"
    r"giveaway|cashback|hamper)\b",
    re.IGNORECASE,
)


def extract_booth_fee(text: str) -> tuple[float | None, bool]:
    """
    Best-effort booth fee in RM.

    Returns (amount, is_free). Amount is the *lowest* plausible RM figure in
    the post, since organisers usually quote the cheapest booth first and the
    rest are upgrades. Returns (None, False) when nothing usable is found.
    """
    if _FREE_BOOTH.search(text):
        return (0.0, True)

    amounts: list[float] = []
    for m in _FEE.finditer(text):
        window = text[max(0, m.start() - 40):m.end() + 40]
        if _FEE_FALSE_CONTEXT.search(window):
            continue
        raw = m.group("amount").replace(",", "").replace(" ", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        if m.group("suffix"):
            value *= 1000
        # Sub-RM10 figures are almost always per-item pricing, not booth rent.
        if value >= 10:
            amounts.append(value)

    return (min(amounts), False) if amounts else (None, False)


# --------------------------------------------------------------------------
# Result
# --------------------------------------------------------------------------

TIER_HOT = "hot"
TIER_GOOD = "good"
TIER_MAYBE = "maybe"

TIER_LABELS = {
    TIER_HOT: "🔥 Strong match",
    TIER_GOOD: "✅ Good match",
    TIER_MAYBE: "👀 Worth a look",
}


@dataclass
class MatchResult:
    passes: bool
    score: int = 0
    tier: str = TIER_MAYBE
    reasons: list[str] = field(default_factory=list)
    rejected_because: str | None = None

    keyword_hits: list[str] = field(default_factory=list)
    organiser_hits: list[str] = field(default_factory=list)
    priority_venues: list[str] = field(default_factory=list)
    known_venues: list[str] = field(default_factory=list)
    areas: list[str] = field(default_factory=list)
    booth_fee: float | None = None
    booth_fee_is_free: bool = False
    fnb_ok: bool | None = None
    date_info: DateInfo = field(default_factory=DateInfo)

    @property
    def tier_label(self) -> str:
        return TIER_LABELS.get(self.tier, TIER_LABELS[TIER_MAYBE])


def _hits(text: str, vocabulary) -> list[str]:
    lowered = text.lower()
    return [term for term in vocabulary if term.lower() in lowered]


class PostMatcher:
    """Applies the configured gates and signals to post text."""

    def __init__(self, config) -> None:
        self.cfg = config
        self.venues = VenueMatcher(
            priority_venues=config.priority_venues,
            extra_venues=config.extra_venues,
            extra_areas=config.extra_areas,
        )

    def evaluate(self, text: str, today: date | None = None) -> MatchResult:
        cfg = self.cfg
        lowered = text.lower()
        result = MatchResult(passes=False)

        result.keyword_hits = _hits(text, cfg.vendor_keywords)
        result.organiser_hits = _hits(text, cfg.organiser_signals)
        venue_hits = self.venues.match(text)
        result.priority_venues = venue_hits["priority"]
        result.known_venues = venue_hits["known"]
        result.areas = venue_hits["areas"]
        result.booth_fee, result.booth_fee_is_free = extract_booth_fee(text)
        result.date_info = extract_dates(text, today=today)

        fnb_negative = _hits(text, FNB_NEGATIVE)
        fnb_positive = _hits(text, FNB_POSITIVE)
        if fnb_negative:
            result.fnb_ok = False
        elif fnb_positive:
            result.fnb_ok = True

        # ---- Gates ----------------------------------------------------
        if len(result.keyword_hits) < cfg.min_keyword_matches:
            result.rejected_because = "no vendor/bazaar keywords"
            return result

        exclusion_hit = _hits(text, cfg.exclusion_keywords)
        if exclusion_hit and not result.organiser_hits:
            result.rejected_because = f"excluded by phrase: {exclusion_hit[0]}"
            return result

        if cfg.drop_fnb_excluded and result.fnb_ok is False:
            result.rejected_because = f"F&B excluded: {fnb_negative[0]}"
            return result

        if cfg.drop_past_events and result.date_info.has_only_past_dates:
            result.rejected_because = "all dates already passed"
            return result

        if cfg.require_weekend and not result.date_info.is_weekend:
            result.rejected_because = "no weekend date found"
            return result

        if cfg.require_location and not (result.priority_venues or result.known_venues or result.areas):
            result.rejected_because = "outside target area"
            return result

        if (
            cfg.max_booth_fee is not None
            and result.booth_fee is not None
            and result.booth_fee > cfg.max_booth_fee
            and cfg.drop_over_budget
        ):
            result.rejected_because = f"booth fee RM{result.booth_fee:.0f} over budget"
            return result

        # ---- Signals --------------------------------------------------
        score = 0

        keyword_points = min(len(result.keyword_hits), 3) * 2
        score += keyword_points
        result.reasons.append(f"+{keyword_points} vendor keywords ({len(result.keyword_hits)})")

        if result.organiser_hits:
            score += 5
            result.reasons.append(f"+5 organiser call ('{result.organiser_hits[0]}')")

        if result.date_info.is_weekend:
            score += 4
            result.reasons.append("+4 weekend date")
        elif result.date_info.has_future_date:
            score += 1
            result.reasons.append("+1 dated, weekday")

        if result.priority_venues:
            score += 5
            result.reasons.append(f"+5 priority venue ({result.priority_venues[0]})")
        elif result.known_venues:
            score += 3
            result.reasons.append(f"+3 known venue ({result.known_venues[0]})")
        elif result.areas:
            score += 2
            result.reasons.append(f"+2 in target area ({result.areas[0]})")

        if result.fnb_ok:
            score += 3
            result.reasons.append("+3 F&B / drinks welcome")

        if result.booth_fee_is_free:
            score += 3
            result.reasons.append("+3 free booth")
        elif result.booth_fee is not None:
            if cfg.max_booth_fee is None or result.booth_fee <= cfg.max_booth_fee:
                score += 2
                result.reasons.append(f"+2 booth fee RM{result.booth_fee:.0f} within budget")
            else:
                score -= 3
                result.reasons.append(f"-3 booth fee RM{result.booth_fee:.0f} over budget")

        if any(term in lowered for term in ("matcha", "japanese", "dessert", "drinks")):
            score += 1
            result.reasons.append("+1 mentions drinks/dessert")

        result.score = score
        result.passes = score >= cfg.min_score

        if score >= cfg.hot_score:
            result.tier = TIER_HOT
        elif score >= cfg.good_score:
            result.tier = TIER_GOOD
        else:
            result.tier = TIER_MAYBE

        if not result.passes:
            result.rejected_because = f"score {score} below threshold {cfg.min_score}"

        return result
