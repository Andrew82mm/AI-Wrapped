"""Synthetic report for demos and README screenshots.

Served at /api/demo and opened in the UI with http://localhost:8000/?demo —
no Last.fm account, API keys or LLM needed. The numbers are made up; the
payload goes through the real `build_wrapped_data`, so it exercises the same
rendering path as a genuine report.
"""
from __future__ import annotations

from frontend.render import build_wrapped_data

_WEEKLY = [
    ("Jul 13", 96, None), ("Jul 20", 118, None), ("Jul 27", 104, None),
    ("Aug 3", 131, None), ("Aug 10", 87, None), ("Aug 17", 342, "Daft Punk"),
    ("Aug 24", 122, None), ("Aug 31", 109, None), ("Sep 7", 98, None),
    ("Sep 14", 55, None), ("Sep 21", 126, None), ("Sep 28", 381, "Radiohead"),
    ("Oct 5", 140, None), ("Oct 12", 113, None),
]

DEMO_PAYLOAD = {
    "user": "demo_listener",
    "period": "last_90d",
    "scrobbles_total": 2437,
    "features": {
        "time_signature": {
            "peak_hour": 23,
            "dominant_slot": "late_night",
            "label": "night owl",
            "hour_distribution": [
                84, 52, 30, 12, 6, 8, 20, 34, 48, 60, 72, 80,
                92, 88, 96, 104, 112, 126, 150, 176, 210, 248, 290, 322,
            ],
        },
        "decade_fingerprint": {
            "distribution": {"2010s": 0.38, "2000s": 0.27, "1990s": 0.2,
                             "2020s": 0.1, "1980s": 0.05},
            "dominant_decade": "2010s",
            "earliest_year": 1983,
            "latest_year": 2026,
        },
        "binge_weeks": {
            "median_weekly_tracks": 112,
            "binge_count": 2,
            "weekly_data": [
                {"label": label, "tracks": n, "is_binge": artist is not None,
                 "top_artist": artist}
                for label, n, artist in _WEEKLY
            ],
        },
        "artist_loyalty": {
            "veterans": [
                {"artist": "Radiohead", "active_weeks": 13},
                {"artist": "Daft Punk", "active_weeks": 12},
                {"artist": "Massive Attack", "active_weeks": 10},
            ],
            "newcomers": [
                {"artist": "Khruangbin", "first_week": "2026-W35"},
                {"artist": "Caroline Polachek", "first_week": "2026-W38"},
            ],
        },
        "guilty_pleasures": {
            "guilty_pleasures": [
                {"artist": "Calvin Harris", "plays": 41, "late_fraction": 0.93},
                {"artist": "ABBA", "plays": 27, "late_fraction": 0.88},
                {"artist": "Rick Astley", "plays": 19, "late_fraction": 0.84},
            ],
        },
        "musical_roommates": {
            "recommendations": [
                {"artist": "Thom Yorke", "suggested_by": ["Radiohead", "Massive Attack"]},
                {"artist": "Four Tet", "suggested_by": ["Daft Punk", "Khruangbin"]},
                {"artist": "Portishead", "suggested_by": ["Massive Attack"]},
            ],
        },
        "artifacts": {
            "longest_session": {
                "duration_min": 372,
                "start": "2026-09-27T21:10:00",
                "top_artists": ["Radiohead"],
            },
            "longest_streak": {
                "days": 41,
                "start": "2026-07-20T00:00:00",
                "end": "2026-08-29T00:00:00",
            },
            "peak_day": {"date": "2026-09-27T00:00:00", "tracks": 119},
            "dead_periods": [
                {"gap_days": 6, "after": "2026-09-08", "before": "2026-09-14"},
            ],
        },
    },
}

DEMO_NARRATIVE = [
    {
        "title": "Ночной слушатель",
        "body": "Твой день заканчивается там, где у других начинается тишина: пик "
                "прослушиваний приходится на 23:00, а после полуночи в плеере всё "
                "ещё играет больше, чем в семь утра. Музыка для тебя — не фон, а "
                "способ закрыть день.",
    },
    {
        "title": "Две недели в одном альбоме",
        "body": "Дважды за квартал счётчик взлетал втрое: в августе — неделя Daft "
                "Punk, в конце сентября — Radiohead, и 27 сентября ты просидел за "
                "ними больше шести часов подряд. Остальное время ты слушаешь ровно, "
                "примерно по сотне треков в неделю.",
    },
    {
        "title": "Тайные слабости",
        "body": "Днём у тебя Massive Attack и Radiohead, а к ночи — Calvin Harris и "
                "ABBA. Девять из десяти прослушиваний этих артистов случаются после "
                "десяти вечера. Мы никому не скажем.",
    },
    {
        "title": "Что послушать дальше",
        "body": "Если Radiohead и Massive Attack твои постоянные спутники, Thom "
                "Yorke уже должен быть в твоей библиотеке. А Khruangbin, открытый "
                "в конце лета, ведёт прямо к Four Tet.",
    },
]


def build_demo_report() -> dict:
    return build_wrapped_data(DEMO_PAYLOAD, DEMO_NARRATIVE)
