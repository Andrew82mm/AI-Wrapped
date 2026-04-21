# AI Wrapped

Spotify Wrapped, but with a narrative instead of numbers.

Collects listening history from Last.fm, enriches each track with metadata
from MusicBrainz + AcousticBrainz, extracts behavioral features, then uses
an LLM to generate a personal text — not "you listened to 47 rock tracks",
but "on Wednesday evening you switched from metal to Debussy".

## Status

In development. Data collection, metadata enrichment, and feature extraction
are complete. LLM narrative generation is next.

## Stack

- Python 3.12
- Last.fm API — listening history, top charts, track tags
- MusicBrainz — MBID, release year, canonical tags (no key required)
- AcousticBrainz — mood, danceability, BPM, genre classifiers (frozen in 2022)
- Genius API — release year fallback *(optional)*
- Claude (Anthropic SDK) — narrative generation *(planned)*

## Project structure

```
src/
  lastfm/
    client.py   — Last.fm API client: scrobbles, top charts, tags
    parser.py   — raw JSON → pandas DataFrames
    cache.py    — disk cache with TTL, fetch_or_update entry point
    sessions.py — session detector and listening pattern finder
  musicbrainz/
    client.py   — recording search + MBID resolution, 1 req/sec rate limit
  acousticbrainz/
    client.py   — high-level (mood/genre) and low-level (bpm) features
  genius/
    client.py   — song search, release year extraction (optional)
  metadata/
    provider.py — TrackMetadata dataclass + unified resolver with parallel
                  fetching and full fallback chain (MB → AB → LFM → Genius)
  features/
    decade.py       — decade distribution, dominant era label
    binge.py        — weeks with listening spikes vs median
    time_profile.py — peak hour, dominant time slot (night owl / early bird / …)
    artist_loyalty.py — veteran artists (4+ active weeks) and newcomers
    discovery.py    — new tracks per month, trend, explorer score
tests/
  test_parser.py
  test_sessions.py
  test_cache.py
  test_metadata.py
  test_features.py
data/               — cached API responses (not in git)
explore_lastfm.py   — Last.fm profile, sessions, patterns
explore_metadata.py — per-track metadata enrichment with coverage report
explore_features.py — compute all narrative features, print JSON context
```

## Quick start

**1. Clone and set up the environment**

```bash
git clone https://github.com/Andrew82mm/AI-Wrapped
cd AI-Wrapped
python3 -m venv venv
venv/bin/pip install requests python-dotenv pandas pytest pytest-mock
```

**2. Get a Last.fm API key**

Register at [last.fm/api](https://www.last.fm/api/account/create).
Callback URL and homepage can both be set to `http://localhost`.

MusicBrainz and AcousticBrainz require no key.
Genius is optional — get a token at [genius.com/api-clients](https://genius.com/api-clients) if you want better release year coverage.

**3. Create `.env`**

```bash
cp .env.example .env
# Required: LASTFM_API_KEY, LASTFM_USERNAME, MUSICBRAINZ_CONTACT
# Optional: GENIUS_ACCESS_TOKEN, ENRICH_TOP_N (default 50)
```

**4. Run**

```bash
venv/bin/python explore_lastfm.py    # profile, sessions, patterns
venv/bin/python explore_metadata.py  # enrich top-N tracks with MB+AB+Genius
venv/bin/python explore_features.py  # compute narrative features
```

Cache strategy: Last.fm responses — 6 hours; full scrobble history — 24 hours;
track metadata — 30 days (MBID and release year don't change).

MusicBrainz is rate-limited to 1 req/sec. Enrichment is capped at top N tracks
(default 50, override via `ENRICH_TOP_N`). Second run is instant from cache.

## Tests

```bash
venv/bin/pytest tests/ -v
```

82 tests. CI runs on every push and pull request to `main`.

## Planned

- LLM narrative generation (Claude, Anthropic SDK, prompt caching)
- Hallucination guard — verify all mentioned artists exist in input context
- CLI entry point `wrapped.py` — single command, formatted output
