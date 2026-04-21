import json
import os
from datetime import datetime, timedelta


CACHE_DIR = os.path.join(os.path.dirname(__file__), "../../data")


def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, f"{name}.json")


def save(name: str, data) -> None:
    """Serialize data to data/<name>.json with a fetched_at timestamp."""
    payload = {
        "fetched_at": datetime.now().isoformat(),
        "data": data,
    }
    with open(_cache_path(name), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load(name: str, max_age_hours: int = 6):
    """Load cached data from data/<name>.json.

    Returns the data payload if the file exists and is younger than max_age_hours,
    otherwise returns None.
    """
    path = _cache_path(name)
    if not os.path.exists(path):
        return None

    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    fetched_at = datetime.fromisoformat(payload["fetched_at"])
    if datetime.now() - fetched_at > timedelta(hours=max_age_hours):
        return None

    return payload["data"]


def fetch_or_update(name: str, fetch_fn, max_age_hours: int = 6):
    """Return cached data if fresh, otherwise fetch, save, and return.

    If cache is missing or older than max_age_hours, calls fetch_fn(),
    saves the result to disk, and returns it.
    """
    cached = load(name, max_age_hours)
    if cached is not None:
        print(f"[cache] {name}: using cached data")
        return cached

    print(f"[cache] {name}: fetching from API...")
    data = fetch_fn()
    save(name, data)
    return data
