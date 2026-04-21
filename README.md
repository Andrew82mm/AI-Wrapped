# AI Wrapped

Spotify Wrapped, but with a narrative instead of numbers.

Collects listening history from Last.fm, analyzes sessions and behavioral patterns, then uses an LLM to generate a personal text breakdown — not "you listened to 47 rock tracks", but "on Wednesday evening you switched from metal to Debussy".

## Status

In development. Data layer (Last.fm), session detector, and track-metadata
enrichment (MusicBrainz + AcousticBrainz) are implemented.

## Stack

- Python 3.12
- Last.fm API — listening history and tag fallback
- MusicBrainz — MBID, release year, canonical tags
- AcousticBrainz — mood, danceability, BPM, genre classifiers (frozen in 2022)
- Genius API — free-text song/artist context for LLM narrative *(optional)*
- LLM — narrative generation *(planned)*

## Project structure

```
src/
  lastfm/
    client.py   — Last.fm API HTTP client
    parser.py   — parse raw API responses into DataFrames
    cache.py    — cache API responses to disk
    sessions.py — session detector and pattern finder
  musicbrainz/
    client.py   — MusicBrainz recording search + MBID resolution
  acousticbrainz/
    client.py   — AcousticBrainz high/low-level feature fetch
  genius/
    client.py   — Genius song search (optional narrative context)
  metadata/
    provider.py — TrackMetadata dataclass + unified resolver with cache
tests/
  test_parser.py
  test_sessions.py
  test_cache.py
  test_metadata.py
data/           — cached API responses (not in git)
explore_lastfm.py   — Last.fm data exploration
explore_metadata.py — per-track metadata enrichment
```

## Quick start

**1. Clone and set up the environment**

```bash
git clone https://github.com/Andrew82mm/AI-Wrapped
cd AI-Wrapped
python3 -m venv venv
venv/bin/pip install requests python-dotenv pandas pytest pytest-mock
```

**2. Get an API key**

Register an application at [last.fm/api](https://www.last.fm/api/account/create).
Callback URL and homepage can both be set to `http://localhost`.

MusicBrainz requires no key, only a contact (email or URL) in the
User-Agent — set `MUSICBRAINZ_CONTACT` in `.env`. AcousticBrainz is
fully open.

**3. Create `.env`**

```bash
cp .env.example .env
# fill in LASTFM_API_KEY, LASTFM_USERNAME, MUSICBRAINZ_CONTACT
```

**4. Run**

```bash
venv/bin/python explore_lastfm.py       # Last.fm profile, sessions, patterns
venv/bin/python explore_metadata.py     # per-track metadata enrichment
```

Data is cached in `data/` — Last.fm responses refresh every 6 hours,
track metadata every 30 days (MBID and release year don't change).

MusicBrainz is rate-limited to 1 request/second, so enrichment is
capped at the top N tracks (default 50; override via `ENRICH_TOP_N`).

## Tests

```bash
venv/bin/pytest tests/ -v
```

CI runs automatically on every push and pull request to `main`.

## Planned features

- Nostalgia score — share of tracks from the user's formative years (ages 13–23)
- Mood transitions within sessions (e.g. aggressive → ambient inside one evening)
- Seasonal trends — compare current period against the same period last year
- LLM narrative and recommendations
