"""
Klang Valley venue and area vocabulary.

Two tiers:

  PRIORITY_VENUES — high-footfall malls and recurring market sites worth an
      immediate look. These come from the shortlist in the original config,
      extended with the venues that run vendor-call bazaars most often.

  KNOWN_VENUES — everywhere else in KL/Selangor we recognise. A match here
      says "this is in your operating radius", which is worth points but is
      not the same signal as a priority venue.

Areas are matched separately so a post that only says "Shah Alam" still
registers as in-radius.

To operate outside the Klang Valley, add your venues to `extra_venues` /
`extra_areas` in config.json rather than editing this file — that keeps your
list intact across updates.
"""

from __future__ import annotations

import re

PRIORITY_VENUES: tuple[str, ...] = (
    "Sunway Pyramid",
    "Mid Valley",
    "The Gardens Mall",
    "Publika",
    "The Starling",
    "Empire City",
    "Pavilion KL",
    "Pavilion Bukit Jalil",
    "Suria KLCC",
    "1 Utama",
    "One Utama",
    "The Curve",
    "IPC Shopping Centre",
    "Sunway Velocity",
    "MyTown",
    "Nu Sentral",
    "KL Eco City",
    "Bangsar Shopping Centre",
    "Bangsar Village",
    "Mont Kiara",
    "Sunway Putra",
    "Setia City Mall",
    "Paradigm Mall",
    "Tropicana Gardens",
    "Central Market",
    "REXKL",
    "GMBB",
    "Sentul Depot",
    "Zepp KL",
)

KNOWN_VENUES: tuple[str, ...] = (
    "Berjaya Times Square",
    "Lalaport",
    "Quill City",
    "Sunway Pinnacle",
    "Sunway Geo",
    "Da Men Mall",
    "Subang Parade",
    "Empire Subang",
    "SS15 Courtyard",
    "Citta Mall",
    "Jaya One",
    "Jaya Shopping Centre",
    "Atria Shopping Gallery",
    "3 Damansara",
    "Sunway Nexis",
    "Encorp Strand",
    "Kepong Village Mall",
    "M3 Mall",
    "Wangsa Walk",
    "AEON Big",
    "AEON Mall",
    "Ampang Point",
    "Great Eastern Mall",
    "KLCC Park",
    "Taman Tugu",
    "Perdana Botanical",
    "Desa Park City",
    "The Waterfront",
    "Setia Alam",
    "Eco Ardence",
    "Elmina",
    "Gamuda Cove",
    "Twentyfive7",
    "Kota Kemuning",
    "Bukit Jalil",
    "Cyberjaya",
    "Putrajaya",
    "IOI City Mall",
    "Mines Shopping Fair",
    "South City Plaza",
    "Seri Kembangan",
    "Kajang",
    "Semenyih",
    "Rawang",
    "Klang Parade",
    "GM Klang",
    "Aeon Bukit Tinggi",
)

AREAS: tuple[str, ...] = (
    "Kuala Lumpur",
    "Selangor",
    "Klang Valley",
    "Petaling Jaya",
    "Subang Jaya",
    "Shah Alam",
    "Damansara",
    "Bangsar",
    "Cheras",
    "Ampang",
    "Setapak",
    "Wangsa Maju",
    "Sentul",
    "Kepong",
    "Puchong",
    "Seri Petaling",
    "Sri Petaling",
    "Old Klang Road",
    "Taman Desa",
    "Sri Hartamas",
    "Solaris",
    "TTDI",
    "Kota Damansara",
    "Ara Damansara",
    "Bukit Bintang",
    "Chow Kit",
    "Titiwangsa",
    "Serdang",
    "Sepang",
    "Klang",
    "Shah Alam",
)

# A few venues are commonly written more than one way.
ALIASES: dict[str, str] = {
    "1u": "1 Utama",
    "1 utama": "1 Utama",
    "one utama": "1 Utama",
    "klcc": "Suria KLCC",
    "mv": "Mid Valley",
    "mvm": "Mid Valley",
    "midvalley": "Mid Valley",
    "pj": "Petaling Jaya",
    "kl": "Kuala Lumpur",
    "bsc": "Bangsar Shopping Centre",
    "ttdi": "TTDI",
    "sunway pyramid mall": "Sunway Pyramid",
}

# Short aliases are only trusted when they stand alone as a word, otherwise
# "kl" fires inside "Klang" and "pj" inside "pjs".
_SHORT_ALIAS_MIN_LEN = 4


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    """Whole-phrase, whitespace-tolerant, case-insensitive matcher."""
    body = r"\s+".join(re.escape(p) for p in phrase.split())
    return re.compile(rf"\b{body}\b", re.IGNORECASE)


class VenueMatcher:
    """Finds venue and area mentions in post text."""

    def __init__(
        self,
        priority_venues: list[str] | None = None,
        extra_venues: list[str] | None = None,
        extra_areas: list[str] | None = None,
    ) -> None:
        self.priority = list(priority_venues if priority_venues is not None else PRIORITY_VENUES)
        self.known = list(KNOWN_VENUES) + list(extra_venues or [])
        self.areas = list(AREAS) + list(extra_areas or [])

        self._priority_patterns = [(v, _phrase_pattern(v)) for v in self.priority]
        self._known_patterns = [(v, _phrase_pattern(v)) for v in self.known]
        self._area_patterns = [(a, _phrase_pattern(a)) for a in self.areas]
        self._alias_patterns = [
            (alias, canonical, _phrase_pattern(alias))
            for alias, canonical in ALIASES.items()
        ]

    def match(self, text: str) -> dict[str, list[str]]:
        """Return {'priority': [...], 'known': [...], 'areas': [...]} of hits."""
        priority: list[str] = []
        known: list[str] = []
        areas: list[str] = []

        for name, pattern in self._priority_patterns:
            if pattern.search(text) and name not in priority:
                priority.append(name)

        for name, pattern in self._known_patterns:
            if pattern.search(text) and name not in known:
                known.append(name)

        for name, pattern in self._area_patterns:
            if pattern.search(text) and name not in areas:
                areas.append(name)

        for alias, canonical, pattern in self._alias_patterns:
            if len(alias) < _SHORT_ALIAS_MIN_LEN and not re.search(
                rf"(?:^|[\s,({{\[]){re.escape(alias)}(?:$|[\s,.){{\]!?])", text, re.IGNORECASE
            ):
                continue
            if not pattern.search(text):
                continue
            if canonical in self.priority and canonical not in priority:
                priority.append(canonical)
            elif canonical in self.areas and canonical not in areas:
                areas.append(canonical)
            elif canonical not in known and canonical in self.known:
                known.append(canonical)

        return {"priority": priority, "known": known, "areas": areas}
