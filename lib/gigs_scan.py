#!/usr/bin/env python3
"""gigs -- which liked artists are playing within reach.

    python3 lib/gigs_scan.py scan       # refresh from RA, match, record
    python3 lib/gigs_scan.py list       # every upcoming match (/gigs)
    python3 lib/gigs_scan.py briefing   # the /today section, or nothing
    python3 lib/gigs_scan.py ingest-web # add agent-found events via stdin JSON

Add --json to any command for machine-readable output.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import ra_client  # noqa: E402
from artist_source import LibraryUnavailable, load_liked_artists  # noqa: E402
from gigs_store import GigsStore  # noqa: E402
from matcher import Match, match_events  # noqa: E402

FLAGS = {
    "Slovenia": "🇸🇮", "Austria": "🇦🇹", "Croatia": "🇭🇷",
    "Serbia": "🇷🇸", "Italy": "🇮🇹",
}


def _fmt(row: dict, show_flag: bool = True) -> str:
    where = " · ".join(p for p in [row.get("venue"), row.get("city")] if p)
    flag = (FLAGS.get(row.get("country") or "", "") + " ") if show_flag else ""
    likes = f" ({row.get('likes')}x)" if row.get("likes") else ""
    tail = "  (unconfirmed)" if row.get("confidence") != "exact" else ""
    return (
        f"  {row.get('date')}  {flag}{row.get('artist')}{likes}"
        f" — {where or row.get('title', '')}{tail}"
    )


def _group_by_event(rows: list[dict]) -> list[dict]:
    """Collapse several liked artists on one bill into a single line.

    A festival with four of your artists is one decision, not four.
    """
    grouped: dict[str, dict] = {}
    for row in rows:
        key = row.get("event_id") or f"{row.get('title')}:{row.get('date')}"
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {**row, "_artists": [(row.get("artist"), row.get("likes"))]}
        else:
            entry["_artists"].append((row.get("artist"), row.get("likes")))
            entry["likes"] = max(int(entry.get("likes") or 0), int(row.get("likes") or 0))
    out = []
    for entry in grouped.values():
        names = sorted(entry.pop("_artists"), key=lambda p: -int(p[1] or 0))
        entry["artist"] = ", ".join(f"{n} ({c}x)" for n, c in names)
        entry["likes"] = None  # already rendered inline per artist
        out.append(entry)
    out.sort(key=lambda r: (r.get("date") or ""))
    return out


def _areas(cfg: dict) -> dict[str, int]:
    configured = cfg.get("areas")
    if isinstance(configured, dict) and configured:
        return {str(k): int(v) for k, v in configured.items()}
    return ra_client.DEFAULT_AREAS


def _artists(cfg: dict):
    return load_liked_artists(
        cfg.get("spotify_db_path") or "~/Data/0-personal/2-code/plur-buzz/plur_buzz.db",
        min_likes=int(cfg.get("min_likes") or 1),
    )


def cmd_scan(args, cfg: dict) -> int:
    data_dir = config.data_dir(cfg)
    try:
        artists = _artists(cfg)
    except LibraryUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    cached, fetched_at = ra_client.load_cache(data_dir)
    max_age = int(cfg.get("cache_hours") or 12)
    problems: list[str] = []

    if args.no_refresh or (cached and ra_client.is_fresh(fetched_at, max_age)):
        events, source = cached, f"cache from {fetched_at}"
    else:
        events, problems = ra_client.sweep(
            areas=_areas(cfg), horizon_days=int(cfg.get("horizon_days") or 180)
        )
        if events:
            ra_client.save_cache(data_dir, events)
            source = "resident advisor (live)"
        else:
            events, source = cached, f"cache from {fetched_at} (live fetch failed)"

    matches = match_events(artists, events)
    store = GigsStore(data_dir)
    fresh = store.record(matches)
    store.prune(int(cfg.get("keep_past_days") or 30))
    store.save()

    if args.json:
        print(json.dumps({
            "artists": len(artists), "events": len(events), "source": source,
            "matches": len(matches), "new": len(fresh), "problems": problems,
        }, indent=1))
        return 0

    print(f"Scanned {len(events)} events ({source}) against {len(artists)} liked artists.")
    print(f"{len(matches)} matches, {len(fresh)} new.")
    for problem in problems:
        print(f"  ! {problem}", file=sys.stderr)
    for match in fresh[:20]:
        print(_fmt({
            "date": match.date, "artist": match.artist, "likes": match.likes,
            "venue": match.venue, "city": match.city, "country": match.country,
            "confidence": match.confidence, "title": match.title,
        }))
    return 0


def cmd_list(args, cfg: dict) -> int:
    store = GigsStore(config.data_dir(cfg))
    rows = store.all_matches()
    if not args.include_low:
        rows = [r for r in rows if r.get("confidence") == "exact"]
    if args.json:
        print(json.dumps(rows, indent=1, ensure_ascii=False))
        return 0
    if not rows:
        print("No upcoming matches. Run `scan` to refresh.")
        return 0
    events = _group_by_event(rows)
    artists = len({r.get("artist") for r in rows})
    print(f"{len(events)} upcoming shows featuring {artists} artists you've liked:")
    country = None
    for row in events:
        if row.get("country") != country:
            country = row.get("country")
            print(f"\n{FLAGS.get(country or '', '')} {country}")
        print(_fmt(row, show_flag=False))
        url = row.get("url") or ""
        if url:
            print(f"              {url if url.startswith('http') else 'https://ra.co' + url}")
    return 0


def cmd_briefing(args, cfg: dict) -> int:
    store = GigsStore(config.data_dir(cfg))
    items = store.briefing_items(int(cfg.get("imminent_days") or 18))
    cap = int(cfg.get("briefing_max") or 8)
    if args.json:
        print(json.dumps(items, indent=1, ensure_ascii=False))
    elif items["new"] or items["imminent"]:
        for heading, key in (
            ("**Newly announced**", "new"),
            ("**Coming up — time to get tickets**", "imminent"),
        ):
            rows = _group_by_event(items[key])
            if not rows:
                continue
            if key == "imminent" and items["new"]:
                print()
            print(heading)
            for row in rows[:cap]:
                print(_fmt(row))
            if len(rows) > cap:
                print(f"  …and {len(rows) - cap} more — run `/gigs` for the full list")
    # Silence is the correct output when there is nothing; the hook omits
    # the section entirely rather than printing "no gigs".
    if args.mark:
        store.mark_announced(items, int(cfg.get("imminent_days") or 18))
        store.save()
    return 0


def cmd_ingest_web(args, cfg: dict) -> int:
    """Take agent-found events on stdin and fold them into the same store.

    Expects a JSON list of events in RA shape. Only entries carrying both a
    date and a venue are accepted -- a rumour of a tour is not a gig.
    """
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"error: stdin is not valid JSON: {exc}", file=sys.stderr)
        return 2

    accepted, rejected = [], 0
    for event in payload if isinstance(payload, list) else []:
        venue = (event.get("venue") or {}).get("name")
        if not (event.get("date") and venue):
            rejected += 1
            continue
        event.setdefault("source", "web")
        event.setdefault("id", f"web-{abs(hash((event.get('title'), event.get('date'))))}")
        accepted.append(event)

    try:
        artists = _artists(cfg)
    except LibraryUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    matches = [
        Match(**{**m.__dict__, "source": "web"}) for m in match_events(artists, accepted)
    ]
    store = GigsStore(config.data_dir(cfg))
    fresh = store.record(matches)
    store.save()
    print(f"Ingested {len(accepted)} web events ({rejected} rejected for missing "
          f"date/venue): {len(matches)} matches, {len(fresh)} new.")
    return 0


def main(argv: list[str] | None = None) -> int:
    # --json is accepted on either side of the subcommand: `gigs --json list`
    # and `gigs list --json` both read naturally, so both work. SUPPRESS keeps
    # the subparser from clobbering a value already set by the main parser.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS,
        help="machine-readable output",
    )

    parser = argparse.ArgumentParser(prog="gigs", description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", parents=[common], help="refresh listings and match")
    scan.add_argument("--no-refresh", action="store_true", help="use cache only")
    listing = sub.add_parser("list", parents=[common], help="show upcoming matches")
    listing.add_argument(
        "--include-low", action="store_true", help="include unconfirmed title matches"
    )
    brief = sub.add_parser("briefing", parents=[common], help="the /today section")
    brief.add_argument("--mark", action="store_true", help="flag items as announced")
    sub.add_parser("ingest-web", parents=[common], help="add agent-found events from stdin JSON")

    args = parser.parse_args(argv)
    for attr, default in (("no_refresh", False), ("include_low", False), ("mark", False)):
        if not hasattr(args, attr):
            setattr(args, attr, default)

    cfg = config.load()
    handlers = {
        "scan": cmd_scan, "list": cmd_list,
        "briefing": cmd_briefing, "ingest-web": cmd_ingest_web,
    }
    return handlers[args.command](args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
