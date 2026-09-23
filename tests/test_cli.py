"""CLI surface tests.

`--json` on the wrong side of the subcommand silently produced human output
and broke a caller parsing it. Both orders are supported and pinned here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))

import config  # noqa: E402
import gigs_scan  # noqa: E402


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Point the module at an empty data dir and a library that isn't there."""
    monkeypatch.setattr(config, "data_dir", lambda cfg=None: tmp_path)
    monkeypatch.setattr(gigs_scan.config, "data_dir", lambda cfg=None: tmp_path)
    monkeypatch.setattr(gigs_scan.config, "load", lambda: {"imminent_days": 18})
    return tmp_path


@pytest.mark.parametrize("argv", [["briefing", "--json"], ["--json", "briefing"]])
def test_json_flag_works_on_either_side(sandbox, capsys, argv) -> None:
    assert gigs_scan.main(argv) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"new": [], "imminent": []}


def test_briefing_is_silent_when_nothing_qualifies(sandbox, capsys) -> None:
    """The /today hook keys off empty output to omit the section entirely."""
    assert gigs_scan.main(["briefing"]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_missing_library_exits_nonzero_with_guidance(sandbox, capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        gigs_scan.config, "load", lambda: {"spotify_db_path": "/nowhere/plur_buzz.db"}
    )
    assert gigs_scan.main(["scan"]) == 2
    err = capsys.readouterr().err
    assert "not found" in err and "plur-buzz" in err, "error must say how to fix it"


def test_ingest_web_rejects_entries_without_date_or_venue(sandbox, capsys, monkeypatch) -> None:
    from matcher import LikedArtist

    monkeypatch.setattr(gigs_scan, "_artists", lambda cfg: [LikedArtist("Moderat", 14)])
    monkeypatch.setattr(
        sys, "stdin",
        type("S", (), {"read": staticmethod(lambda: json.dumps([
            {"title": "Rumoured tour", "artists": [{"id": "w", "name": "Moderat"}]},
            {"title": "Moderat live", "date": "2026-11-14",
             "venue": {"name": "Kino Šiška",
                       "area": {"name": "Ljubljana", "country": {"name": "Slovenia"}}},
             "artists": [{"id": "w2", "name": "Moderat"}]},
        ]))})(),
    )
    assert gigs_scan.main(["ingest-web"]) == 0
    out = capsys.readouterr().out
    assert "1 rejected" in out and "1 new" in out


def test_ingest_web_rejects_malformed_stdin(sandbox, capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": staticmethod(lambda: "not json")})())
    assert gigs_scan.main(["ingest-web"]) == 2
