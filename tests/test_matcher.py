"""Matcher tests.

The false-positive cases are not hypothetical: each one was produced by a
naive substring matcher during the 2026-09-09 feasibility sweep of the target
region. They are here so that matching can never regress to that behaviour.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from matcher import (  # noqa: E402
    LikedArtist,
    canonical,
    match_events,
    title_contains,
)


# --- canonicalisation -------------------------------------------------------

@pytest.mark.parametrize(
    "a,b",
    [
        ("El Búho", "El Buho"),          # diacritics
        ("Âme", "Ame"),
        ("Tuğçe", "Tugce"),
        ("Klik & Frik", "Klik and Frik"),  # ampersand spelled out
        ("Floating Points", "floating points"),
        ("Daniel Avery (live)", "Daniel Avery"),      # billing suffix
        ("Jeff Mills [DJ set]", "Jeff Mills"),
        ("Yu Su b2b Prins Thomas", "Yu Su Prins Thomas"),
    ],
)
def test_canonical_equates(a: str, b: str) -> None:
    assert canonical(a) == canonical(b)


def test_canonical_separates_distinct_artists() -> None:
    assert canonical("Kode9") != canonical("Kode 10")
    assert canonical("Hyper") != canonical("Hypertrash")


# --- title matching: the measured false positives ---------------------------

@pytest.mark.parametrize(
    "title,artist",
    [
        ("HYPERTRASH - LOUD, QUEER & ANNOYING", "Hyper"),
        ("Piknik with Badboombox Zagreb / Kali / Gigi", "BoomBox"),
        ("Matthew Ryals, Neda Rimaitè", "S.N.E"),
        ("SOTTOSUONO OPEN AIR: Carl Craig", "Air"),   # whole word, still junk
        ("Deep House All Night", "Deep"),          # too short, and a common word
        ("Sunset Sessions", "Sun"),
    ],
)
def test_title_rejects_substring_collisions(title: str, artist: str) -> None:
    assert not title_contains(title, artist)


@pytest.mark.parametrize(
    "title,artist",
    [
        ("MOAB // Daniel Avery", "Daniel Avery"),
        ("SOTTOSUONO x DURO: Carl Craig", "Carl Craig"),
        ("Special guest: floating points live", "Floating Points"),
    ],
)
def test_title_accepts_whole_word_runs(title: str, artist: str) -> None:
    assert title_contains(title, artist)


def test_short_names_are_deliberately_unreachable_by_title() -> None:
    """Names under MIN_TITLE_LEN never title-match, and that is the right call.

    'Âme' is a real liked artist, but a 3-character name matches ordinary words
    in event titles -- 'Air' would hit "SOTTOSUONO OPEN AIR". Short acts are
    still found the normal way, through a structured lineup, which is how Âme
    was in fact found during the feasibility sweep.
    """
    assert not title_contains("Âme DJ + Auggië", "Ame")

    lineup_event = _event("e1", "Âme DJ + Auggië", ["Âme"])
    (m,) = match_events([LikedArtist("Âme", 1)], [lineup_event])
    assert m.confidence == "exact"


# --- event matching ---------------------------------------------------------

def _event(eid: str, title: str, lineup: list[str] | None, date: str = "2026-10-10") -> dict:
    return {
        "id": eid,
        "title": title,
        "date": f"{date}T22:00:00.000",
        "contentUrl": f"/events/{eid}",
        "venue": {"name": "DURO", "area": {"name": "Milan", "country": {"name": "Italy"}}},
        "artists": [{"id": "1", "name": n} for n in (lineup or [])],
    }


def test_exact_lineup_match_wins() -> None:
    artists = [LikedArtist("Daniel Avery", 12)]
    events = [_event("e1", "MOAB", ["Daniel Avery", "Someone Else"])]
    (m,) = match_events(artists, events)
    assert m.artist == "Daniel Avery"
    assert m.confidence == "exact"
    assert m.likes == 12
    assert m.is_briefable


def test_lineup_present_but_artist_absent_is_not_a_match() -> None:
    """A listed lineup is authoritative -- don't fall back to the title."""
    artists = [LikedArtist("Daniel Avery", 12)]
    events = [_event("e1", "Daniel Avery tribute night", ["A DJ", "Another DJ"])]
    assert match_events(artists, events) == []


def test_title_tier_only_when_lineup_missing() -> None:
    artists = [LikedArtist("Carl Craig", 1)]
    events = [_event("e1", "SOTTOSUONO x DURO: Carl Craig", None)]
    (m,) = match_events(artists, events)
    assert m.confidence == "title"
    assert not m.is_briefable, "low-confidence matches must stay out of the briefing"


def test_no_duplicate_match_per_artist_per_event() -> None:
    artists = [LikedArtist("Yu Su", 3)]
    events = [_event("e1", "Festival", ["Yu Su", "Yu Su (live)"])]
    assert len(match_events(artists, events)) == 1


def test_results_sorted_by_date_then_likes() -> None:
    artists = [LikedArtist("Daniel Avery", 12), LikedArtist("Kode9", 1)]
    events = [
        _event("e1", "Later", ["Kode9"], date="2026-12-01"),
        _event("e2", "Sooner", ["Daniel Avery"], date="2026-10-01"),
    ]
    dates = [m.date for m in match_events(artists, events)]
    assert dates == ["2026-10-01", "2026-12-01"]


def test_multi_artist_string_splitting_is_caller_side() -> None:
    """Two acts liked separately both match the same event."""
    artists = [LikedArtist("El Búho", 2), LikedArtist("Klik & Frik", 1)]
    events = [_event("e1", "Organic night", ["El Buho", "Klik and Frik"])]
    assert {m.artist for m in match_events(artists, events)} == {"El Búho", "Klik & Frik"}
