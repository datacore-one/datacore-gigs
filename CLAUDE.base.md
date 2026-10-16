# Gigs Module

Concert radar over the Spotify library: which artists the user has actually
liked are playing within reach of home.

## What it is

Region-first, not artist-first. One sweep of Resident Advisor's listings for
the configured areas (`areas` in `gigs.local.yaml`) returns every
event **with its lineup**; ~950 liked artists are then matched against ~600
events locally. Querying per artist would be ~950 requests for the same answer.

## Boundaries

**This module does not talk to Spotify.** A separate sync tool holds an OAuth
token with `user-library-read` and writes Liked Songs into SQLite
(`spotify_db_path`). This module reads that DB. A second integration would mean
a second consent flow and a second token cache drifting out of date, for data
already on disk. Refreshing the library is the sync tool's job.

**It writes no user data into itself.** Match history and the listings cache
live under `data_dir` (default `0-personal/.datacore/gigs/`), per DIP-0007 —
the module is publishable, a record of someone's music taste is not.

## Known coverage gap — state it, don't paper over it

RA covers club and festival bookings. It barely covers live-music venues:
many concert halls book acts that never appear in its listings. A first full
sweep can easily return all its matches from one country and none from the
home region, because the home region's listings are local residents, not
touring acts.

This is not a bug and must not be reported as one. It is the shape of the
source. The web-enrichment pass (see the `gigs` skill) exists to cover it. If
after some months the home region is still empty, the honest next step is
regional ticketing adapters, which were considered and deferred as too
maintenance-heavy for a personal module.

When the user asks "anything near home?" and the answer is nothing, **say
nothing is listed** — do not pad the answer with shows further away unless asked.

## Matching rules

Two tiers, deliberately unequal:

- **exact** — artist appears in an event's structured lineup. Briefing-eligible.
- **title** — artist name appears as whole words in the title, used only when an
  event has no lineup at all (~25% of listings). **Never briefing-eligible.**

Substring matching is banned and regression-tested. It was measured and is
worse than nothing: on the first sweep it produced five hits, all
five false — `Hyper` in "HYPERTRASH", `BoomBox` in "Badboombox", `S.N.E` in
"Neda Rimaitè". Names under 5 characters cannot title-match at all, because
`Air` would hit "OPEN AIR". Short acts like Âme are still found via lineup.

## Briefing discipline

A match is announced **once** when found, then **once** more when the show
comes within ~18 days (ticket time), then never. A show already inside that
window when discovered spends both slots at once — otherwise it appears two
mornings running, which is how a daily section stops being read.

On a morning with neither, `briefing` prints nothing and the section is
**omitted entirely**. Never render "no gigs".

`--mark` spends the announcements. Only pass it when the output actually
reaches the briefing.

## The like-count is the signal

`Artist Four (12x)` means twelve of their tracks are in the library — that is
the difference between a weekend trip and a shrug. Always carry it. Never sort
by date alone when the user is deciding whether to go.

## Failure posture

RA's GraphQL endpoint is undocumented and unversioned; treat it as something
that will break. On failure: fall back to cache, report the failure loudly in
`/gigs`, keep the briefing silent, and **never present cached listings as
current** — the scan line names its own source.

## Commands

| Command | Purpose |
|---------|---------|
| `/gigs` | Every upcoming match, grouped by event |
| `lib/gigs_scan.py scan` | Refresh listings, match, record |
| `lib/gigs_scan.py briefing --mark` | The /today section |
| `lib/gigs_scan.py ingest-web` | Fold agent-found events in (needs date + venue) |

## Tests

`pytest tests/` — 33 tests, no live calls. The false positives above and the
double-announcement bug are regression cases; if you change matching or
announcement logic, those are the tests that matter.
