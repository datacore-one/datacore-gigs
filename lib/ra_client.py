"""Resident Advisor event listings for the target region.

Region-first, not artist-first. One paged query per area returns every event
with its lineup, so ~950 liked artists are matched against ~600 events with a
handful of requests instead of ~950 lookups.

This is RA's own GraphQL endpoint, which is undocumented and unversioned. It
is treated throughout as something that will break: failures surface loudly and
fall back to cache, and cached data is never presented as fresh. The HTML site
sits behind Cloudflare (403); the GraphQL endpoint does not.

Area IDs come from the installation's settings (``areas``). Country-level
"All" areas were measured to cover their cities, so city areas need not be
queried separately.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ENDPOINT = "https://ra.co/graphql"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# label -> RA area id
# No built-in region: set ``areas`` in gigs.local.yaml.
DEFAULT_AREAS: dict[str, int] = {}

_QUERY = """
query($filters: FilterInputDtoInput, $pageSize: Int, $page: Int) {
  eventListings(filters: $filters, pageSize: $pageSize, page: $page,
                sort: {listingDate: {order: ASCENDING}}) {
    totalResults
    data {
      event {
        id title date contentUrl
        venue { name area { name country { name } } }
        artists { id name }
      }
    }
  }
}
"""

PAGE_SIZE = 100
MAX_PAGES = 20  # 2000 events per area; the region runs ~600 in six months


class RegionUnavailable(RuntimeError):
    """RA could not be reached or answered in a shape we understand."""


def _post(payload: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Referer": "https://ra.co/events",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RegionUnavailable(
            f"RA returned HTTP {exc.code}. The endpoint is undocumented and may "
            "have changed or started blocking. Cached results are used instead."
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RegionUnavailable(f"RA request failed: {exc}") from exc


def fetch_area(area_id: int, gte: str, lte: str, timeout: int = 45) -> list[dict]:
    """Every listed event in one area between two ISO dates."""
    events: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        payload = {
            "query": _QUERY,
            "variables": {
                "filters": {
                    "areas": {"eq": int(area_id)},
                    "listingDate": {"gte": gte, "lte": lte},
                },
                "pageSize": PAGE_SIZE,
                "page": page,
            },
        }
        body = _post(payload, timeout)
        if body.get("errors"):
            raise RegionUnavailable(
                "RA rejected the query -- its schema has likely changed: "
                f"{json.dumps(body['errors'])[:300]}"
            )
        listings = (body.get("data") or {}).get("eventListings") or {}
        rows = listings.get("data") or []
        events.extend(row["event"] for row in rows if row.get("event"))
        if not rows or page * PAGE_SIZE >= int(listings.get("totalResults") or 0):
            break
        time.sleep(0.4)  # courtesy to an endpoint that owes us nothing
    return events


def sweep(
    areas: dict[str, int] | None = None,
    horizon_days: int = 180,
    today: date | None = None,
) -> tuple[list[dict], list[str]]:
    """Fetch every area. Returns (deduped events, per-area failure notes).

    A single area failing does not abort the sweep -- partial coverage beats
    none -- but every failure is returned so the caller can say so out loud.
    """
    areas = areas or DEFAULT_AREAS
    today = today or datetime.now(timezone.utc).date()
    gte = today.isoformat()
    lte = (today + timedelta(days=horizon_days)).isoformat()

    by_id: dict[str, dict] = {}
    problems: list[str] = []
    for label, area_id in areas.items():
        try:
            for event in fetch_area(area_id, gte, lte):
                by_id[str(event["id"])] = event
        except RegionUnavailable as exc:
            problems.append(f"{label}: {exc}")
    return list(by_id.values()), problems


# --- cache ------------------------------------------------------------------

def cache_path(data_dir: Path) -> Path:
    return Path(data_dir) / "events_cache.json"


def save_cache(data_dir: Path, events: list[dict]) -> None:
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "events": events,
    }
    cache_path(data_dir).write_text(json.dumps(payload))


def load_cache(data_dir: Path) -> tuple[list[dict], str | None]:
    """Cached events and when they were fetched (None when there is no cache)."""
    path = cache_path(data_dir)
    if not path.exists():
        return [], None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return [], None
    return payload.get("events") or [], payload.get("fetched_at")


def is_fresh(fetched_at: str | None, max_age_hours: int) -> bool:
    if not fetched_at:
        return False
    try:
        stamp = datetime.fromisoformat(fetched_at)
    except ValueError:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - stamp
    return age < timedelta(hours=max_age_hours)
