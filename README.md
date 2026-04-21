# AI Wrapped

Spotify Wrapped, but with a narrative instead of numbers.

Collects listening history from Last.fm, analyzes sessions and behavioral patterns, then uses an LLM to generate a personal text breakdown — not "you listened to 47 rock tracks", but "on Wednesday evening you switched from metal to Debussy".

## Status

In development. Data layer (Last.fm) and session detector are implemented.

## Stack

- Python 3.12
- Last.fm API — listening history
- Spotify API — track audio features *(planned)*
- MusicBrainz / Tavily — artist info and new releases *(planned)*
- LLM  — narrative generation *(planned)*

## Project structure

```
src/
  lastfm/
    client.py   — Last.fm API HTTP client
    parser.py   — parse raw API responses into DataFrames
    cache.py    — cache API responses to disk
    sessions.py — session detector and pattern finder
tests/
  test_parser.py
  test_sessions.py
  test_cache.py
data/           — cached API responses (not in git)
explore_lastfm.py — data exploration script
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

**3. Create `.env`**

```bash
cp .env.example .env
# fill in LASTFM_API_KEY and LASTFM_USERNAME
```

**4. Run**

```bash
venv/bin/python explore_lastfm.py
```

The script prints a user profile, top artists/tracks/albums for the last 3 months,
scrobble stats by hour and weekday, and detected session patterns.
Data is cached in `data/` and refreshed every 6 hours.

## Tests

```bash
venv/bin/pytest tests/ -v
```

CI runs automatically on every push and pull request to `main`.

## Planned features

- Spotify audio features (energy, valence, BPM) for an emotional listening profile
- Nostalgia score — share of tracks from the user's formative years (ages 13–23)
- Seasonal trends — compare current period against the same period last year
- Web search grounding for up-to-date artist and release information
- LLM narrative and recommendations
