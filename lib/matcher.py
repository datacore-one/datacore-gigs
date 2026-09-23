"""Match liked artists against event lineups.

Two tiers, deliberately unequal:

- ``exact``  — the artist appears in an event's structured lineup. Trustworthy.
- ``title``  — the artist name appears as whole words in the event title, used
  only when an event has no structured lineup at all.

The title tier exists because ~25% of RA listings carry no structured lineup
(measured 2026-09-09: 155 of 614 events across the target region). It is
token-gated rather than substring-based because substring matching was measured
and is unusable: on the same sweep it produced 5 near-home hits, all 5 false --
"Hyper" inside "HYPERTRASH", "BoomBox" inside "Badboombox", "S.N.E" inside
"Neda Rimaite". Those three are regression tests in tests/test_matcher.py.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Suffixes promoters append to a booking; they are not part of the artist name.
_BILLING = re.compile(
    r"\s*[\(\[]?\b(live|dj set|dj-set|djset|b2b|hybrid set|all night long|"
    r"live av|a/v|av set|extended set|closing set|opening set)\b[\)\]]?\s*",
    re.IGNORECASE,
)

# Minimum length for a title-tier match. Short names collide constantly with
# ordinary words; the exact tier has no such limit because it needs none.
MIN_TITLE_LEN = 5


def fold(value: str) -> str:
    """Strip accents and case so 'El Búho' and 'El Buho' compare equal."""
    folded = unicodedata.normalize("NFKD", value or "")
    folded = folded.encode("ascii", "ignore").decode()
    return folded.lower()


def canonical(name: str) -> str:
    """Reduce an artist name to a comparison key.

    Accents dropped, '&' spelled out so 'Klik & Frik' meets 'Klik and Frik',
    billing suffixes removed, everything non-alphanumeric discarded.
    """
    name = _BILLING.sub(" ", fold(name))
    name = name.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", name)


def tokens(value: str) -> list[str]:
    """Word tokens of a string, accent-folded. Used for title matching."""
    return re.findall(r"[a-z0-9]+", fold(value).replace("&", " and "))


def title_contains(title: str, artist: str) -> bool:
    """True when *artist* appears in *title* as a whole run of words.

    Word-boundary anchored on both ends, so 'Hyper' does not match
    'HYPERTRASH' and 'BoomBox' does not match 'Badboombox'.
    """
    a_tokens = tokens(artist)
    if not a_tokens:
        return False
    if len(canonical(artist)) < MIN_TITLE_LEN:
        return False
    t_tokens = tokens(title)
    n = len(a_tokens)
    return any(t_tokens[i : i + n] == a_tokens for i in range(len(t_tokens) - n + 1))


@dataclass(frozen=True)
class LikedArtist:
    """An artist from the library, with how often they were liked."""

    name: str
    likes: int
    key: str = field(default="")

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", self.key or canonical(self.name))


@dataclass(frozen=True)
class Match:
    artist: str
    likes: int
    confidence: str  # "exact" | "title"
    event_id: str
    title: str
    date: str
    venue: str | None
    city: str | None
    country: str | None
    url: str | None
    source: str = "ra"

    @property
    def is_briefable(self) -> bool:
        """Only exact matches are allowed near the morning briefing."""
        return self.confidence == "exact"


def index_artists(artists: list[LikedArtist]) -> dict[str, LikedArtist]:
    """Key artists for lookup, keeping the higher like-count on collision."""
    out: dict[str, LikedArtist] = {}
    for a in artists:
        if not a.key:
            continue
        prev = out.get(a.key)
        if prev is None or a.likes > prev.likes:
            out[a.key] = a
    return out


def match_events(artists: list[LikedArtist], events: list[dict]) -> list[Match]:
    """Find liked artists playing in *events*.

    An event contributes at most one match per artist. The title tier is only
    consulted for events that carry no structured lineup -- when a lineup
    exists and the artist is absent from it, they are genuinely not playing.
    """
    index = index_artists(artists)
    matches: list[Match] = []

    for event in events:
        lineup = event.get("artists") or []
        seen: set[str] = set()

        for entry in lineup:
            key = canonical(entry.get("name", ""))
            liked = index.get(key)
            if liked and key not in seen:
                seen.add(key)
                matches.append(_build(liked, event, "exact"))

        if not lineup:
            title = event.get("title", "")
            for key, liked in index.items():
                if key not in seen and title_contains(title, liked.name):
                    seen.add(key)
                    matches.append(_build(liked, event, "title"))

    matches.sort(key=lambda m: (m.date, -m.likes, m.artist))
    return matches


def _build(liked: LikedArtist, event: dict, confidence: str) -> Match:
    venue = event.get("venue") or {}
    area = venue.get("area") or {}
    country = area.get("country") or {}
    return Match(
        artist=liked.name,
        likes=liked.likes,
        confidence=confidence,
        event_id=str(event.get("id", "")),
        title=event.get("title", ""),
        date=(event.get("date") or "")[:10],
        venue=venue.get("name"),
        city=area.get("name"),
        country=country.get("name"),
        url=event.get("contentUrl"),
        source=event.get("source", "ra"),
    )
