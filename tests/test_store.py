"""Announcement-lifecycle tests.

The rule under test: a match is announced once when found, then once more when
the show comes within ticket range, and never otherwise. The double-announce
case in test_new_find_already_imminent_does_not_repeat was a real bug -- shows
discovered already inside the window were announced on two consecutive days.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from gigs_store import GigsStore  # noqa: E402
from matcher import Match  # noqa: E402


def _match(artist: str = "Daniel Avery", days_out: int = 60, **kw) -> Match:
    fields = dict(
        artist=artist, likes=12, confidence="exact", event_id=f"e-{artist}-{days_out}",
        title="MOAB", date=(date.today() + timedelta(days=days_out)).isoformat(),
        venue="DURO", city="Milan", country="Italy", url="/events/1", source="ra",
    )
    fields.update(kw)
    return Match(**fields)


@pytest.fixture()
def store(tmp_path: Path) -> GigsStore:
    return GigsStore(tmp_path)


def test_new_match_is_announced_once(store: GigsStore) -> None:
    store.record([_match()])
    assert len(store.briefing_items()["new"]) == 1

    store.mark_announced(store.briefing_items())
    after = store.briefing_items()
    assert after["new"] == [] and after["imminent"] == []


def test_new_find_already_imminent_does_not_repeat(store: GigsStore) -> None:
    """A show found inside the ticket window burns both slots at once."""
    store.record([_match(days_out=5)])
    first = store.briefing_items(imminent_days=18)
    assert len(first["new"]) == 1 and first["imminent"] == []

    store.mark_announced(first, imminent_days=18)
    second = store.briefing_items(imminent_days=18)
    assert second["new"] == [], "already announced"
    assert second["imminent"] == [], "must not re-announce the very next run"


def test_far_show_resurfaces_once_when_close(store: GigsStore) -> None:
    store.record([_match(days_out=90)])
    store.mark_announced(store.briefing_items(), imminent_days=18)
    assert store.briefing_items()["imminent"] == []

    # the show approaches
    entry = next(iter(store._load()["matches"].values()))
    entry["date"] = (date.today() + timedelta(days=10)).isoformat()

    resurfaced = store.briefing_items(imminent_days=18)
    assert len(resurfaced["imminent"]) == 1

    store.mark_announced(resurfaced, imminent_days=18)
    assert store.briefing_items()["imminent"] == [], "only once"


def test_low_confidence_never_reaches_the_briefing(store: GigsStore) -> None:
    store.record([_match(confidence="title")])
    items = store.briefing_items()
    assert items["new"] == [] and items["imminent"] == []
    assert len(store.all_matches()) == 1, "but it is still listed by /gigs"


def test_past_shows_are_excluded_and_pruned(store: GigsStore) -> None:
    store.record([_match(days_out=-2), _match(artist="Four Tet", days_out=-40)])
    assert store.all_matches() == []
    assert store.briefing_items()["new"] == []
    assert store.prune(keep_days=30) == 1, "only the 40-day-old one is dropped"


def test_rescan_does_not_resurrect_announced_matches(store: GigsStore) -> None:
    """Re-recording the same match keeps its announcement state."""
    store.record([_match()])
    store.mark_announced(store.briefing_items())
    assert store.record([_match()]) == [], "not a new find"
    assert store.briefing_items()["new"] == []


def test_moved_event_details_refresh_without_reannouncing(store: GigsStore) -> None:
    store.record([_match()])
    store.mark_announced(store.briefing_items())
    store.record([_match(venue="Q35 WAREHOUSE")])
    row = store.all_matches()[0]
    assert row["venue"] == "Q35 WAREHOUSE"
    assert row["announced_new"] is True


def test_state_survives_a_reload(store: GigsStore, tmp_path: Path) -> None:
    store.record([_match()])
    store.mark_announced(store.briefing_items())
    store.save()
    assert GigsStore(tmp_path).briefing_items()["new"] == []
