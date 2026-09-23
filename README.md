# gigs

Concert radar for your Spotify library. Finds artists you've actually liked
playing in Slovenia, Austria, Croatia, Serbia and Italy.

```
$ /gigs
15 upcoming shows featuring 17 artists you've liked:

🇮🇹 Italy
  2026-09-12  Artist One (4x), Artist Two (3x), Artist Three (1x) — Auditorium Parco della Musica · Rome
  2026-10-10  Artist Four (12x) — DURO · Milan
  2026-10-29  Artist Five (1x), Artist Six (1x) — Lingotto Fiere · Turin
```

## How it works

1. **Artists** come from the library `plur-buzz` already syncs — this module
   never touches Spotify itself.
2. **Events** come from one Resident Advisor sweep per region, returning full
   lineups, so ~950 artists match against ~600 events in a handful of requests.
3. **Matches** land in the morning briefing once when found, and once more when
   the show is close enough to buy tickets for.

## Setup

Nothing, if plur-buzz lives at its default path. Otherwise create
`gigs.local.yaml` (gitignored):

```yaml
spotify_db_path: /path/to/plur_buzz.db
```

To keep the library current, run plur-buzz's likes sync — this module reads,
it does not fetch.

## Coverage, honestly

Resident Advisor is excellent on clubs and festivals and thin on live-music
venues. On the first full sweep that meant 21 matches, **all in Italy, none
near home** — Vienna listed 143 events and matched none of them, because those
are local residents rather than touring acts.

The `/gigs` skill includes a web-enrichment pass over your most-liked artists
to catch Kino Šiška / Arena Wien / Tvornica bookings that RA never lists. If
the home region stays empty over a few months, the real fix is regional
ticketing adapters (Eventim.si, Entrio.hr, oeticket.at) — deliberately deferred
as too maintenance-heavy to build on speculation.

## Settings

See `module.yaml`. The ones worth knowing: `horizon_days` (180),
`imminent_days` (18, the ticket-time nudge), `briefing_max` (8),
`cache_hours` (12), `areas` (RA area IDs).

## Tests

```bash
pytest tests/     # 33 tests, no network
```

MIT.
