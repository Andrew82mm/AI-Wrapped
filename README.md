# AI-Wrapped

Spotify Wrapped, but with a narrative instead of numbers.

Pulls your Last.fm listening history, enriches tracks with metadata from
MusicBrainz + AcousticBrainz, computes behavioral features, then sends
the whole picture to an LLM that writes a personal editorial — not
"you listened to 47 rock tracks", but "on Wednesday evenings you drift
from metal into Debussy, every time".

---

## Quick start — web interface

```bash
git clone https://github.com/Andrew82mm/AI-Wrapped
cd AI-Wrapped
python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env   # fill in the required keys (see below)

venv/bin/python frontend/server.py
# → open http://localhost:8000
```

On the welcome screen you enter a Last.fm username, pick a time window
(7 days → all time), and choose the narrative backend (Claude CLI or
OpenRouter). The report generates in the background and streams progress
to the browser.

---

## Quick start — CLI

```bash
venv/bin/python wrapped.py --user yourname --period last:90 --backend cli
```

Useful flags:

| Flag | Default | Description |
|---|---|---|
| `--user` | prompt | Last.fm username |
| `--period` | lifetime | `last:N` / `YYYY` / `YYYY-MM-DD:YYYY-MM-DD` |
| `--backend` | openrouter | `cli` (local Claude Code binary) or `openrouter` |
| `--lang` | ru | narrative language: `ru` or `en` |
| `--voice` | a | `a` = observational friend, `b` = music critic |
| `--json out.json` | — | dump features JSON |
| `--html report.html` | — | render self-contained HTML report |
| `--stages` | all | `profile`, `metadata`, `features`, `narrative` |
| `--top-n` | 50 | tracks to enrich with MusicBrainz/AcousticBrainz |

---

## Environment variables (`.env`)

```dotenv
# Required
LASTFM_API_KEY=...          # last.fm/api/account/create
MUSICBRAINZ_CONTACT=...     # your email — required by MusicBrainz ToS

# Narrative backends (one is enough)
OPENROUTER_API_KEY=...      # openrouter.ai — for --backend openrouter
# Claude CLI backend uses the local `claude` binary — no extra key needed

# Optional
GENIUS_ACCESS_TOKEN=...     # better release-year coverage
ENRICH_TOP_N=50             # how many top tracks to enrich
OPENROUTER_MODEL=...        # override default model
LASTFM_USERNAME=...         # skip the username prompt in CLI mode
```

---

## How it works

```
Last.fm API
  ↓ scrobble history, top artists/tracks/albums
MusicBrainz + AcousticBrainz
  ↓ MBID, release year, mood, BPM, genre
Feature extraction
  ↓ 9 behavioral signals (see below)
LLM (Claude CLI or OpenRouter)
  ↓ editorial narrative, verified against artist whitelist
HTML report
```

### Features computed

| Feature | What it captures |
|---|---|
| `time_signature` | Peak hour, dominant time slot (night owl / early bird / …) |
| `decade_fingerprint` | Decade distribution of listened tracks, dominant era |
| `binge_weeks` | Weeks with listening spikes vs personal median |
| `artist_loyalty` | Veterans (4+ active weeks) and new arrivals |
| `discovery_rate` | New tracks per month, explorer score, trend |
| `listening_style` | Obsessive vs collector vs explorer, top obsession track |
| `guilty_pleasures` | Artists listened to almost exclusively late at night |
| `musical_roommates` | Artist recommendations via Last.fm similarity graph |
| `artifacts` | Longest session, streak, peak day, longest silence |

---

## Project structure

```
src/
  lastfm/       — API client, parser, disk cache, session detector
  musicbrainz/  — recording search, MBID resolution (1 req/sec)
  acousticbrainz/ — mood, genre, BPM classifiers
  genius/       — release year fallback (optional)
  metadata/     — unified TrackMetadata resolver with full fallback chain
  features/     — all 9 feature modules
  narrative/    — prompt builder, LLM caller, hallucination verifier

frontend/
  server.py     — FastAPI server: /api/generate, /api/status, /api/result
  index.html    — React web app (CDN Babel, no build step)
  template.html — static self-contained HTML report (via --html flag)
  render.py     — transforms feature JSON → frontend data format

tests/          — 224 unit tests, no network calls
data/           — per-user cache (not in git): data/<username>/
wrapped.py      — CLI entry point
```

---

## Narrative backends

**Claude CLI** (`--backend cli`)  
Uses the local `claude` binary from Claude Code. No API key needed beyond
what Claude Code already has. Timeout: 5 minutes. Good for local use.

**OpenRouter** (`--backend openrouter`)  
Calls any model via the OpenRouter API. Default: `nvidia/nemotron-3-super-120b-a12b:free`.
Override via `OPENROUTER_MODEL`. Retries on 429 with exponential backoff (up to 4×).

---

## Per-user cache

Each user's data lives in `data/<username>/`. Multiple users can be
processed without collision. Cache TTL:

- Scrobble history: 24 hours
- Top charts: 6 hours  
- Track metadata (MB/AB): 30 days

---

## Tests

```bash
venv/bin/pytest tests/ -q
# 224 tests, ~9s, no network calls
```

Integration tests (real API calls) are in `test_metadata_integration.py`
and are excluded from the default run.
