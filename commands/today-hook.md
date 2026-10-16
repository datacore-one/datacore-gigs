---
name: today-hook
description: today-hook command
recall:
  scopes:
    - command:today-hook
  tags:
    - today-hook
    - gigs
---

# Gigs Hook: /today Integration

Adds a short "Gigs" section to the morning briefing — **only when there is
something to say**. Called by `/today` when the gigs module is installed.

## Workflow

### Step 1: Produce the section

```bash
cd ~/Data/.datacore/modules/gigs && python3 lib/gigs_scan.py scan --no-refresh >/dev/null 2>&1
python3 lib/gigs_scan.py briefing --mark
```

`--no-refresh` keeps the briefing off the network: it must never block on an
undocumented third-party endpoint. Listings are refreshed by `/gigs` (12-hour
cache) or a scheduled `scan`.

### Step 2: Decide whether the section exists

`briefing` prints nothing when nothing qualifies. **That is the expected case on
most mornings** — 21 matches over six months is about one every nine days.

| Output | What to do |
|--------|-----------|
| Empty | **Omit the section entirely** |
| Content | Render under `### Gigs`, unchanged in substance |

### Step 3: Render

One line per show: artist, like-count, venue, city. Two subsections at most —
**Newly announced** (found since the last briefing) and **Coming up** (now
within ~18 days, the ticket-buying prompt).

```markdown
### Gigs

**Newly announced**
  2026-10-10  🇮🇹 Artist Four (12x) — Example Club · Milan

**Coming up — time to get tickets**
  2026-09-22  🇮🇹 Artist Seven (2x) — Example Hall · Milan
```

## Your Boundaries

- **Never render an empty section.** No "no gigs today", no placeholder, no
  "nothing near you this morning". Silence means the section does not exist.
- **Never pass `--mark` unless the output actually reaches the briefing.** It
  spends the announcement; if /today aborts afterwards, those shows are
  silently consumed and never mentioned again.
- **Never surface unconfirmed (title-tier) matches.** They are filtered out
  upstream; do not reach around the tool to add them.
- **Never editorialise about whether to go.** The like-count carries the
  judgement. `Artist Four (12x)` in Milan speaks for itself.
- **Never pad.** One match is one line, not a paragraph.
- **Never present cached listings as current.** If asked how fresh this is, the
  scan output names its own source.
- **Do not report the empty home region as a fault.** RA covers clubs, not
  live-music venues; that gap is documented and expected.

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| Scan exits non-zero | Produce **no section**. Do not surface the error in the briefing. |
| Spotify library missing | No section. It surfaces when the user runs `/gigs`. |
| RA unreachable | No section. `--no-refresh` means the briefing was reading cache anyway. |
| Cache empty and no matches | No section. |
| `briefing` prints but /today then fails | The announcement is already spent — note it, don't re-run with `--mark`. |

A missing library or an upstream outage is not briefing material. The briefing
reports gigs; `/gigs` reports the health of the thing that finds them.
