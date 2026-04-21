"""
Quick exploration script — run this to see what Last.fm data looks like.
"""
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from src.lastfm.client import LastFMClient
from src.lastfm.parser import (
    parse_scrobbles,
    parse_top_artists,
    parse_top_tracks,
    parse_top_albums,
)

load_dotenv()

API_KEY = os.getenv("LASTFM_API_KEY")
USERNAME = os.getenv("LASTFM_USERNAME")

if not API_KEY or not USERNAME:
    raise SystemExit("Set LASTFM_API_KEY and LASTFM_USERNAME in .env")

client = LastFMClient(API_KEY)

# --- User info ---
print("=" * 50)
info = client.get_user_info(USERNAME)
registered = datetime.fromtimestamp(int(info["registered"]["unixtime"]))
print(f"User:        {info['name']}")
print(f"Country:     {info.get('country', '—')}")
print(f"Scrobbles:   {int(info['playcount']):,}")
print(f"Registered:  {registered.strftime('%Y-%m-%d')}")

# --- Top artists (last month) ---
print("\n" + "=" * 50)
print("TOP ARTISTS — last 3 months")
raw_artists = client.get_top_artists(USERNAME, period="3month", limit=10)
df_artists = parse_top_artists(raw_artists)
print(df_artists.to_string(index=False))

# --- Top tracks (last 3 months) ---
print("\n" + "=" * 50)
print("TOP TRACKS — last 3 months")
raw_tracks = client.get_top_tracks(USERNAME, period="3month", limit=10)
df_tracks = parse_top_tracks(raw_tracks)
print(df_tracks.to_string(index=False))

# --- Top albums (last 3 months) ---
print("\n" + "=" * 50)
print("TOP ALBUMS — last 3 months")
raw_albums = client.get_top_albums(USERNAME, period="3month", limit=10)
df_albums = parse_top_albums(raw_albums)
print(df_albums.to_string(index=False))

# --- Recent scrobbles (last 7 days) ---
print("\n" + "=" * 50)
print("RECENT SCROBBLES — last 90 days")
week_ago = int((datetime.now() - timedelta(days=90)).timestamp())
raw_recent = client.get_recent_tracks(USERNAME, from_ts=week_ago)
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

print("\nUnique artists this week:", df_scrobbles["artist"].nunique())
print("Unique tracks this week:", df_scrobbles["track"].nunique())

# --- Tags for top 5 artists ---
print("\n" + "=" * 50)
print("TAGS FOR TOP 5 ARTISTS")
for _, row in df_artists.head(5).iterrows():
    tags = client.get_artist_tags(row["artist"])
    print(f"  {row['artist']}: {', '.join(tags) if tags else '—'}")
