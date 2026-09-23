---
name: gigs
description: Show upcoming shows by artists from your Spotify library, playing within reach
user-invocable: true
---

# Gigs

Artists you've actually liked, playing in Slovenia, Austria, Croatia, Serbia or Italy.

## Current matches

!`cd ~/Data/.datacore/modules/gigs && python3 lib/gigs_scan.py scan 2>&1 | head -3 && echo && python3 lib/gigs_scan.py list 2>&1 | head -60`

## Instructions

### How to read it

- `(12x)` is how many tracks by that artist are in your library — the strongest
  signal that a show is worth the trip.
- `(unconfirmed)` appears only with `--include-low`: the artist's name was found
  in an event title but not in a structured lineup. Verify before booking.

### Follow-ups

Offer these; don't run them unprompted.

| Ask | Do |
|-----|-----|
| "show unconfirmed too" | `python3 lib/gigs_scan.py list --include-low` |
| "refresh" | `python3 lib/gigs_scan.py scan` (cache is 12h; this forces a look) |
| "anything near home?" | Filter to Slovenia/Austria/Croatia/Serbia and say plainly if it's empty |
| "check the big names" | Run the web-enrichment pass below |

### Web enrichment

Resident Advisor covers club and festival bookings well and misses live-music
venues almost entirely — Kino Šiška, Arena Wien, Tvornica, Dom Omladine book
acts that never appear in RA listings. Roughly monthly, or when the user asks
about a specific artist:

1. Take the top artists by like-count that have no upcoming RA match:
   `python3 lib/gigs_scan.py list --json` for what's already known, and
   `python3 -c "import sys;sys.path.insert(0,'lib');import config,artist_source;
   [print(a.name,a.likes) for a in artist_source.top_artists(artist_source.load_liked_artists(config.load()['spotify_db_path']),40)]"`
2. Search each for 2026/2027 tour dates in the five countries, using the exa or
   perplexity MCP tools.
3. Feed confirmed findings back in — **only** entries with both a real date and
   a named venue; a tour rumour is not a gig:

```bash
echo '[{"title":"Artist at Venue","date":"2026-11-14","contentUrl":"https://...",
  "venue":{"name":"Kino Šiška","area":{"name":"Ljubljana","country":{"name":"Slovenia"}}},
  "artists":[{"id":"w1","name":"Artist Name"}]}]' \
  | python3 lib/gigs_scan.py ingest-web
```

Web-sourced matches merge into the same store and reach the briefing on the
same terms as RA ones.

### Honesty rule

If a scan fails, say so — never present cached listings as current. The scan
line reports its own source (`resident advisor (live)` vs `cache from ...`);
pass that through rather than hiding it.
