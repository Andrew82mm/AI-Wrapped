import time
import requests


BASE_URL = "https://ws.audioscrobbler.com/2.0/"


class LastFMClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()

    def _get(self, method: str, **params) -> dict:
        response = self.session.get(BASE_URL, params={
            "method": method,
            "api_key": self.api_key,
            "format": "json",
            **params,
        })
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise ValueError(f"Last.fm API error {data['error']}: {data['message']}")
        return data

    def get_recent_tracks(self, username: str, from_ts: int = None, to_ts: int = None, limit: int = 200) -> list[dict]:
        """Fetch all scrobbles in a time range, handles pagination automatically."""
        tracks = []
        page = 1

        while True:
            params = {"user": username, "limit": limit, "page": page}
            if from_ts:
                params["from"] = from_ts
            if to_ts:
                params["to"] = to_ts

            data = self._get("user.getRecentTracks", **params)
            page_tracks = data["recenttracks"]["track"]

            # Skip currently playing track (has no timestamp)
            page_tracks = [t for t in page_tracks if "date" in t]
            tracks.extend(page_tracks)

            attr = data["recenttracks"]["@attr"]
            if int(attr["page"]) >= int(attr["totalPages"]):
                break

            page += 1
            time.sleep(0.25)  # respect rate limit

        return tracks

    def get_top_artists(self, username: str, period: str = "overall", limit: int = 50) -> list[dict]:
        """period: overall | 7day | 1month | 3month | 6month | 12month"""
        data = self._get("user.getTopArtists", user=username, period=period, limit=limit)
        return data["topartists"]["artist"]

    def get_top_tracks(self, username: str, period: str = "overall", limit: int = 50) -> list[dict]:
        data = self._get("user.getTopTracks", user=username, period=period, limit=limit)
        return data["toptracks"]["track"]

    def get_top_albums(self, username: str, period: str = "overall", limit: int = 50) -> list[dict]:
        data = self._get("user.getTopAlbums", user=username, period=period, limit=limit)
        return data["topalbums"]["album"]

    def get_user_info(self, username: str) -> dict:
        data = self._get("user.getInfo", user=username)
        return data["user"]

    def get_weekly_chart_list(self, username: str) -> list[dict]:
        """Returns all available weekly chart periods for a user."""
        data = self._get("user.getWeeklyChartList", user=username)
        return data["weeklychartlist"]["chart"]

    def get_artist_tags(self, artist: str) -> list[str]:
        try:
            data = self._get("artist.getTopTags", artist=artist)
            tags = data["toptags"]["tag"]
            return [t["name"].lower() for t in tags[:5]]
        except Exception:
            return []
