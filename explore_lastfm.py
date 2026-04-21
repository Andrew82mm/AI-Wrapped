"""
Quick exploration script — run this to see what Last.fm data looks like.
Данные кэшируются в data/ и обновляются раз в 6 часов.
"""
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from src.lastfm.client import LastFMClient
from src.lastfm.cache import fetch_or_update
from src.lastfm.parser import (
    parse_scrobbles,
    parse_top_artists,
    parse_top_tracks,
    parse_top_albums,
)
from src.lastfm.sessions import detect_sessions, sessions_to_df, find_patterns

load_dotenv()

API_KEY = os.getenv("LASTFM_API_KEY")
USERNAME = os.getenv("LASTFM_USERNAME")

if not API_KEY or not USERNAME:
    raise SystemExit("Set LASTFM_API_KEY and LASTFM_USERNAME in .env")

client = LastFMClient(API_KEY)

# --- User info ---
print("=" * 50)
info = fetch_or_update(
    f"{USERNAME}_info",
    lambda: client.get_user_info(USERNAME),
    max_age_hours=24,
)
registered = datetime.fromtimestamp(int(info["registered"]["unixtime"]))
print(f"User:        {info['name']}")
print(f"Country:     {info.get('country', '—')}")
print(f"Scrobbles:   {int(info['playcount']):,}")
print(f"Registered:  {registered.strftime('%Y-%m-%d')}")

# --- Top artists (last 3 months) ---
print("\n" + "=" * 50)
print("TOP ARTISTS — last 3 months")
raw_artists = fetch_or_update(
    f"{USERNAME}_top_artists_3month",
    lambda: client.get_top_artists(USERNAME, period="3month", limit=10),
)
df_artists = parse_top_artists(raw_artists)
print(df_artists.to_string(index=False))

# --- Top tracks (last 3 months) ---
print("\n" + "=" * 50)
print("TOP TRACKS — last 3 months")
raw_tracks = fetch_or_update(
    f"{USERNAME}_top_tracks_3month",
    lambda: client.get_top_tracks(USERNAME, period="3month", limit=10),
)
df_tracks = parse_top_tracks(raw_tracks)
print(df_tracks.to_string(index=False))

# --- Top albums (last 3 months) ---
print("\n" + "=" * 50)
print("TOP ALBUMS — last 3 months")
raw_albums = fetch_or_update(
    f"{USERNAME}_top_albums_3month",
    lambda: client.get_top_albums(USERNAME, period="3month", limit=10),
)
df_albums = parse_top_albums(raw_albums)
print(df_albums.to_string(index=False))

# --- Scrobbles (last 90 days) ---
print("\n" + "=" * 50)
print("RECENT SCROBBLES — last 90 days")
days_ago_90 = int((datetime.now() - timedelta(days=90)).timestamp())
raw_recent = fetch_or_update(
    f"{USERNAME}_scrobbles_90d",
    lambda: client.get_recent_tracks(USERNAME, from_ts=days_ago_90),
)
df_scrobbles = parse_scrobbles(raw_recent)
print(f"Total scrobbles: {len(df_scrobbles)}")
print(f"\nFirst scrobble:\n{df_scrobbles.iloc[0]}")
print(f"\nLast scrobble:\n{df_scrobbles.iloc[-1]}")

# --- Simple stats from scrobbles ---
print("\n" + "=" * 50)
print("STATS FROM SCROBBLES")

df_scrobbles["hour"] = df_scrobbles["timestamp"].dt.hour
df_scrobbles["weekday"] = df_scrobbles["timestamp"].dt.day_name()

print("\nScrobbles by hour of day:")
print(df_scrobbles.groupby("hour").size().sort_index().to_string())

print("\nScrobbles by weekday:")
order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
by_day = df_scrobbles.groupby("weekday").size().reindex(order).fillna(0).astype(int)
print(by_day.to_string())

print("\nUnique artists:", df_scrobbles["artist"].nunique())
print("Unique tracks:", df_scrobbles["track"].nunique())

# --- Sessions ---
print("\n" + "=" * 50)
print("SESSIONS")
sessions = detect_sessions(df_scrobbles)
df_sessions = sessions_to_df(sessions)
print(f"Total sessions: {len(sessions)}")
print(f"Avg duration:   {df_sessions['duration_min'].mean():.0f} min")
print(f"Avg tracks:     {df_sessions['track_count'].mean():.1f}")
print(f"\nLongest sessions:")
print(df_sessions.nlargest(5, "duration_min")[["start", "duration_min", "track_count", "top_artists"]].to_string(index=False))

print("\n" + "=" * 50)
print("RECURRING PATTERNS")
patterns = find_patterns(sessions)
for p in patterns:
    artists = ", ".join(p["top_artists"]) or "—"
    print(
        f"  [{p['day_type']} {p['time_slot']}]"
        f"  ~{p['avg_hour']:.0f}:00"
        f"  {p['avg_duration_min']} min"
        f"  x{p['occurrences']} times"
        f"  | {artists}"
    )

# --- Tags for top 5 artists ---
print("\n" + "=" * 50)
print("TAGS FOR TOP 5 ARTISTS")
for _, row in df_artists.head(5).iterrows():
    tags = fetch_or_update(
        f"tags_{row['artist'].replace(' ', '_')}",
        lambda a=row["artist"]: client.get_artist_tags(a),
        max_age_hours=72,
    )
    print(f"  {row['artist']}: {', '.join(tags) if tags else '—'}")
