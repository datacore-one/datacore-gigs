"""What has been found, and what has already been said about it.

The briefing rule this implements: announce a match once when it is first
discovered, then stay quiet about it until the show is close enough to buy
tickets for, announce it once more, then never again. Without this state a
daily briefing section degenerates into the same lines every morning until
it stops being read.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from matcher import Match, canonical

STORE_NAME = "matches.json"


def _key(match: Match) -> str:
    return f"{match.event_id}:{canonical(match.artist)}"


def _today() -> date:
    return datetime.now(timezone.utc).date()


class GigsStore:
    """JSON-backed record of matches and what has been announced."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / STORE_NAME
        self._data: dict[str, Any] | None = None

    # --- persistence --------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if self._data is not None:
            return self._data
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except json.JSONDecodeError:
                self._data = {"matches": {}}
        else:
            self._data = {"matches": {}}
        self._data.setdefault("matches", {})
        return self._data

    def save(self) -> None:
        data = self._load()
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.path.write_text(json.dumps(data, indent=1, ensure_ascii=False))

    # --- ingest -------------------------------------------------------------

    def record(self, matches: Iterable[Match]) -> list[Match]:
        """Merge matches in. Returns those seen for the first time.

        Existing entries keep their first_seen and announcement flags; their
        event details are refreshed, because dates and venues do move.
        """
        data = self._load()
        store = data["matches"]
        today = _today().isoformat()
        fresh: list[Match] = []

        for match in matches:
            key = _key(match)
            entry = store.get(key)
            payload = {
                "artist": match.artist,
                "likes": match.likes,
                "confidence": match.confidence,
                "event_id": match.event_id,
                "title": match.title,
                "date": match.date,
                "venue": match.venue,
                "city": match.city,
                "country": match.country,
                "url": match.url,
                "source": match.source,
            }
            if entry is None:
                payload.update(
                    first_seen=today, announced_new=False, announced_imminent=False
                )
                store[key] = payload
                fresh.append(match)
            else:
                entry.update(payload)
        return fresh

    # --- selection ----------------------------------------------------------

    def all_matches(self, include_past: bool = False) -> list[dict]:
        today = _today().isoformat()
        rows = list(self._load()["matches"].values())
        if not include_past:
            rows = [r for r in rows if (r.get("date") or "") >= today]
        rows.sort(key=lambda r: (r.get("date") or "", -int(r.get("likes") or 0)))
        return rows

    def briefing_items(self, imminent_days: int = 18) -> dict[str, list[dict]]:
        """The two things worth interrupting a morning for.

        Only exact-confidence matches qualify; title-tier guesses stay in
        /gigs where a wrong one costs nothing.
        """
        today = _today()
        horizon = (today + timedelta(days=imminent_days)).isoformat()
        today_iso = today.isoformat()

        new_finds, imminent = [], []
        for row in self._load()["matches"].values():
            if row.get("confidence") != "exact":
                continue
            when = row.get("date") or ""
            if when < today_iso:
                continue
            if not row.get("announced_new"):
                new_finds.append(row)
            elif not row.get("announced_imminent") and when <= horizon:
                imminent.append(row)

        key = lambda r: (r.get("date") or "", -int(r.get("likes") or 0))
        return {"new": sorted(new_finds, key=key), "imminent": sorted(imminent, key=key)}

    def mark_announced(self, items: dict[str, list[dict]], imminent_days: int = 18) -> None:
        """Flag what the briefing just showed, so it is not shown again.

        A find that is already inside the ticket window when discovered has its
        imminent slot burned at the same time. Otherwise it would qualify as
        "coming up" the very next morning and be announced twice running --
        which is the exact repetition this state exists to prevent.
        """
        store = self._load()["matches"]
        horizon = (_today() + timedelta(days=imminent_days)).isoformat()
        for row in items.get("new", []):
            entry = store.get(f"{row['event_id']}:{canonical(row['artist'])}")
            if entry:
                entry["announced_new"] = True
                if (entry.get("date") or "") <= horizon:
                    entry["announced_imminent"] = True
        for row in items.get("imminent", []):
            entry = store.get(f"{row['event_id']}:{canonical(row['artist'])}")
            if entry:
                entry["announced_imminent"] = True

    def prune(self, keep_days: int = 30) -> int:
        """Drop events that finished more than *keep_days* ago."""
        cutoff = (_today() - timedelta(days=keep_days)).isoformat()
        store = self._load()["matches"]
        stale = [k for k, v in store.items() if (v.get("date") or "") < cutoff]
        for k in stale:
            del store[k]
        return len(stale)
