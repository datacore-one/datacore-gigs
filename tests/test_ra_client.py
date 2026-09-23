"""RA client tests — fixture-driven, never live.

RA's GraphQL endpoint is undocumented and unversioned. These tests pin the
behaviour that matters when it changes underneath us: failures must be loud,
partial sweeps must still return what they got, and cache must never be
mistaken for fresh data.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import ra_client  # noqa: E402

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "ra_page.json").read_text())


@pytest.fixture()
def one_page(monkeypatch):
    """Endpoint returns a single page of results."""
    monkeypatch.setattr(ra_client, "_post", lambda payload, timeout: FIXTURE)


def test_fetch_area_parses_events(one_page) -> None:
    events = ra_client.fetch_area(142, "2026-09-10", "2027-03-09")
    assert [e["id"] for e in events] == ["1001", "1002"]
    assert events[0]["artists"][0]["name"] == "Example Artist"
    assert events[1]["artists"] == [], "lineup-less events still come through"


def test_graphql_errors_raise_rather_than_returning_empty(monkeypatch) -> None:
    """A schema change must not look like 'no events on'."""
    monkeypatch.setattr(
        ra_client, "_post",
        lambda payload, timeout: {"errors": [{"message": 'Cannot query field "urlName"'}]},
    )
    with pytest.raises(ra_client.RegionUnavailable, match="schema"):
        ra_client.fetch_area(142, "2026-09-10", "2027-03-09")


def test_sweep_dedupes_events_across_areas(one_page) -> None:
    events, problems = ra_client.sweep(areas={"A": 1, "B": 2}, horizon_days=30)
    assert len(events) == 2, "same events in two areas collapse to one set"
    assert problems == []


def test_sweep_survives_one_area_failing(monkeypatch) -> None:
    """Partial coverage beats none — but the failure is reported, not swallowed."""
    calls = {"n": 0}

    def flaky(payload, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ra_client.RegionUnavailable("HTTP 403")
        return FIXTURE

    monkeypatch.setattr(ra_client, "_post", flaky)
    events, problems = ra_client.sweep(areas={"Broken": 1, "Fine": 2}, horizon_days=30)
    assert len(events) == 2, "the working area still returned data"
    assert len(problems) == 1 and "Broken" in problems[0]


def test_sweep_requests_the_configured_horizon(monkeypatch) -> None:
    captured = {}

    def capture(payload, timeout):
        captured.update(payload["variables"]["filters"]["listingDate"])
        return FIXTURE

    monkeypatch.setattr(ra_client, "_post", capture)
    ra_client.sweep(areas={"A": 1}, horizon_days=90, today=datetime(2026, 9, 10).date())
    assert captured == {"gte": "2026-09-10", "lte": "2026-12-09"}


# --- cache ------------------------------------------------------------------

def test_cache_roundtrip(tmp_path: Path) -> None:
    ra_client.save_cache(tmp_path, [{"id": "1"}])
    events, fetched_at = ra_client.load_cache(tmp_path)
    assert events == [{"id": "1"}] and fetched_at


def test_missing_cache_is_not_an_error(tmp_path: Path) -> None:
    assert ra_client.load_cache(tmp_path) == ([], None)


def test_corrupt_cache_is_not_an_error(tmp_path: Path) -> None:
    ra_client.cache_path(tmp_path).write_text("{not json")
    assert ra_client.load_cache(tmp_path) == ([], None)


@pytest.mark.parametrize(
    "age_hours,max_age,expected",
    [(1, 12, True), (11.9, 12, True), (13, 12, False), (240, 12, False)],
)
def test_freshness_window(age_hours: float, max_age: int, expected: bool) -> None:
    stamp = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    assert ra_client.is_fresh(stamp, max_age) is expected


def test_absent_or_unparseable_timestamp_is_never_fresh() -> None:
    """Unknown age must fail closed, or cache gets presented as current."""
    assert ra_client.is_fresh(None, 12) is False
    assert ra_client.is_fresh("not-a-date", 12) is False
