"""Generate a self-contained HTML report from the wrapped.py JSON output.

Usage:
    python frontend/render.py features.json report.html
    python frontend/render.py features.json report.html --narrative narrative.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


_PALETTE = [
    {"bg": "#fff0f2", "color": "#e60023"},
    {"bg": "#fdf6ec", "color": "#c46b00"},
    {"bg": "#f3f0ff", "color": "#6845ab"},
    {"bg": "#f0fff4", "color": "#1a7f3c"},
    {"bg": "#f0f4ff", "color": "#3b5bdb"},
]

_DECADE_COLORS = {
    "2020s": "#e60023",
    "2010s": "#e60023",
    "2000s": "#c0001d",
    "1990s": "#6845ab",
    "1980s": "#4a2d8a",
    "1970s": "#2d4a8a",
    "1960s": "#1a3566",
}


def _period_meta(period_str: str) -> dict:
    if period_str == "lifetime":
        return {"label": "All time", "days": None}
    m = re.match(r"last:(\d+)", period_str)
    if m:
        days = int(m.group(1))
        labels = {7: "7 days", 30: "30 days", 90: "90 days",
                  180: "6 months", 365: "1 year"}
        return {"label": labels.get(days, f"{days} days"), "days": days}
    if re.match(r"\d{4}$", period_str):
        return {"label": period_str, "days": 365}
    return {"label": period_str, "days": None}


def _format_duration(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _format_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%b %-d")
    except Exception:
        return iso


def _first_week_to_date(iso_week: str) -> str:
    try:
        year, w = iso_week.split("-W")
        d = datetime.strptime(f"{year}-W{w}-1", "%G-W%V-%u")
        return d.strftime("%b %-d")
    except Exception:
        return iso_week


def compute_archetype(features: dict) -> dict:
    ts   = features.get("time_signature", {})
    ls   = features.get("listening_style", {})
    dr   = features.get("discovery_rate", {})
    bw   = features.get("binge_weeks", {})
    df   = features.get("decade_fingerprint", {})
    al   = features.get("artist_loyalty", {})

    slot             = ts.get("dominant_slot", "evening") or "evening"
    style            = ls.get("label", "balanced") or "balanced"
    explorer_score   = dr.get("explorer_score", 0) or 0
    trend            = dr.get("trend", "stable") or "stable"
    binge_count      = bw.get("binge_count", 0) or 0
    dominant_decade  = df.get("dominant_decade", "") or ""
    veterans         = al.get("veterans") or []
    repeat_intensity = ls.get("repeat_intensity", 0) or 0

    if slot == "night" and style == "obsessive":
        return {"nickname": "Полночный одержимый", "tagline": "Ночь — единственное время, когда треки слышны правильно", "emoji": "🌙"}
    if explorer_score > 0.5 and trend == "growing":
        return {"nickname": "Неутомимый исследователь", "tagline": "Ни один плейлист нельзя слушать дважды", "emoji": "🔭"}
    if binge_count >= 4:
        return {"nickname": "Машина для биндж-прослушивания", "tagline": "Либо всё, либо ничего. Чаще всего — всё", "emoji": "⚡"}
    if len(veterans) >= 4 and explorer_score < 0.35:
        return {"nickname": "Верный хранитель", "tagline": "Любимые артисты — как старые друзья. Зачем новые?", "emoji": "🔒"}
    if dominant_decade and dominant_decade <= "2000s":
        return {"nickname": "Меломан не своего времени", "tagline": "Лучшая музыка уже была написана", "emoji": "📼"}
    if style == "collector":
        return {"nickname": "Коллекционер звука", "tagline": "Чем больше треков, тем лучше. Всегда", "emoji": "📀"}
    if slot in ("night", "late_night") and repeat_intensity >= 10:
        return {"nickname": "Ночной гурман", "tagline": "После 22:00 начинается настоящая музыка", "emoji": "🍷"}
    if slot in ("night", "late_night"):
        return {"nickname": "Полночный слушатель", "tagline": "Тишина дня — только фон для ночных треков", "emoji": "🦉"}
    if slot == "morning":
        return {"nickname": "Утренний настройщик", "tagline": "Музыка раньше кофе", "emoji": "☀️"}
    if explorer_score > 0.4:
        return {"nickname": "Активный исследователь", "tagline": "Плейлист всегда можно обновить", "emoji": "🗺️"}
    if style == "obsessive":
        return {"nickname": "Музыкальный одержимый", "tagline": "Один трек. Снова. Снова. Снова", "emoji": "🔁"}
    return {"nickname": "Сбалансированный меломан", "tagline": "Всему своё время и своя музыка", "emoji": "🎵"}


def build_wrapped_data(payload: dict, narrative_sections: list | None = None) -> dict:
    features = payload.get("features", {})
    username = payload.get("user", "")
    period_str = payload.get("period", "lifetime")
    period = _period_meta(period_str)

    scrobbles = payload.get("scrobbles_total", 0)
    per_day = round(scrobbles / period["days"]) if period.get("days") and scrobbles else 0

    # ── time signature ────────────────────────────────────────────────────────
    ts = features.get("time_signature", {})
    hour_dist_raw = ts.get("hour_distribution", [0] * 24)
    peak_hour = ts.get("peak_hour", 0)
    h12 = peak_hour % 12 or 12
    peak_label = f"{h12}:00 {'AM' if peak_hour < 12 else 'PM'}"
    label_map = {
        "insomniac":        "Insomniac",
        "early bird":       "Early Bird",
        "daytime listener": "Daytime Listener",
        "evening listener": "Evening Listener",
        "night owl":        "Night Owl",
    }
    ts_label = label_map.get(ts.get("label", ""), ts.get("label", "Night Owl"))

    slot = ts.get("dominant_slot", "")
    if slot in ("night", "insomniac"):
        slot_pill = "🌙 Mostly after midnight"
    elif slot == "late_night":
        slot_pill = "🌙 Night owl — active after 10 PM"
    elif slot == "morning":
        slot_pill = "☀️ Morning sessions dominate"
    elif slot == "afternoon":
        slot_pill = "☀️ Afternoon listener"
    else:
        slot_pill = "🌆 Evening listener"

    # ── decade fingerprint ────────────────────────────────────────────────────
    df_feat = features.get("decade_fingerprint", {})
    dist = df_feat.get("distribution", {})
    decades = [
        {
            "label": dec,
            "pct": round(frac * 100),
            "color": _DECADE_COLORS.get(dec, "#6845ab"),
        }
        for dec, frac in sorted(dist.items(), key=lambda x: -x[1])
    ]

    # ── binge weeks ───────────────────────────────────────────────────────────
    bw = features.get("binge_weeks", {})
    weekly_raw = bw.get("weekly_data", [])
    binge_weeks_js = [
        {
            "label": w["label"],
            "val":   w["tracks"],
            "spike": w["is_binge"],
            "artist": f"{w['top_artist']} week" if w.get("top_artist") else None,
            "sc":    w["tracks"] if w["is_binge"] else None,
        }
        for w in weekly_raw[-16:]
    ]

    # ── artist loyalty ────────────────────────────────────────────────────────
    al = features.get("artist_loyalty", {})
    veterans = [
        {"name": v["artist"], "badge": f"{v['active_weeks']} weeks active"}
        for v in (al.get("veterans") or [])[:5]
    ]
    newcomers = [
        {"name": n["artist"], "badge": f"first heard {_first_week_to_date(n['first_week'])}"}
        for n in (al.get("newcomers") or [])[:5]
    ]

    # ── guilty pleasures ──────────────────────────────────────────────────────
    gp = features.get("guilty_pleasures", {})
    guilty = [
        {
            "name":   g["artist"],
            "tag":    f"{round(g['late_fraction'] * 100)}% late-night plays",
            "letter": g["artist"][0].upper(),
            **_PALETTE[i % len(_PALETTE)],
        }
        for i, g in enumerate((gp.get("guilty_pleasures") or [])[:3])
    ]

    # ── recommendations ───────────────────────────────────────────────────────
    mr = features.get("musical_roommates", {})
    recs = [
        {
            "name": r["artist"],
            "via":  r.get("suggested_by", [])[:3],
            "desc": "",
        }
        for r in (mr.get("recommendations") or [])[:3]
    ]

    # ── artifacts ─────────────────────────────────────────────────────────────
    art = features.get("artifacts", {})
    artifact_cards = []

    ls = art.get("longest_session")
    if ls:
        top = ls.get("top_artists", [])
        artist_str = f" with {top[0]}" if top else ""
        artifact_cards.append({
            "icon":  "⟳",
            "value": _format_duration(ls["duration_min"]),
            "label": f"Longest session\n{_format_date(ls['start'])}{artist_str}",
        })

    streak = art.get("longest_streak")
    if streak:
        artifact_cards.append({
            "icon":  "◈",
            "value": f"{streak['days']} days",
            "label": f"Longest listening streak\n{_format_date(streak['start'])} – {_format_date(streak['end'])}",
        })

    pd_ = art.get("peak_day")
    if pd_:
        artifact_cards.append({
            "icon":  "▲",
            "value": str(pd_["tracks"]),
            "label": f"Most scrobbles in a day\n{_format_date(pd_['date'])}",
        })

    dead = art.get("dead_periods") or []
    if dead:
        worst = dead[0]
        artifact_cards.append({
            "icon":  "◷",
            "value": f"{worst['gap_days']}d silence",
            "label": f"Longest break\n{_format_date(worst['after'])} – {_format_date(worst['before'])}",
        })

    return {
        "user":      username,
        "period":    period,
        "archetype": compute_archetype(features),
        "scrobbles": scrobbles,
        "per_day": per_day,
        "time_signature": {
            "hour_distribution": hour_dist_raw,
            "peak_hour":  peak_hour,
            "peak_label": peak_label,
            "label":      ts_label,
            "pill":       slot_pill,
        },
        "decade_fingerprint": {
            "decades":   decades,
            "dominant":  df_feat.get("dominant_decade", ""),
            "earliest":  df_feat.get("earliest_year"),
            "latest":    df_feat.get("latest_year"),
        },
        "binge_weeks": {
            "weeks":       binge_weeks_js,
            "median":      bw.get("median_weekly_tracks", 0),
            "binge_count": bw.get("binge_count", 0),
        },
        "artist_loyalty": {
            "veterans":  veterans,
            "newcomers": newcomers,
        },
        "guilty_pleasures": guilty,
        "recommendations":  recs,
        "artifacts":        artifact_cards,
        "narrative":        {"sections": narrative_sections or []},
    }


def render(payload: dict, narrative_sections: list | None, out_path: str) -> None:
    data = build_wrapped_data(payload, narrative_sections)
    data_json = json.dumps(data, ensure_ascii=False, indent=2, default=str)

    template_path = Path(__file__).parent / "template.html"
    html = template_path.read_text(encoding="utf-8")
    html = html.replace("__WRAPPED_DATA_JSON__", data_json)

    Path(out_path).write_text(html, encoding="utf-8")
    size_kb = os.path.getsize(out_path) // 1024
    print(f"[html] wrote {out_path} ({size_kb} KB)")


def _parse_narrative_md(path: str) -> list[dict]:
    """Parse '## Title\\nbody…' markdown into [{title, body}] list."""
    text = Path(path).read_text(encoding="utf-8")
    sections: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                sections.append(current)
            current = {"title": line[3:].strip(), "body": ""}
        elif current is not None:
            current["body"] = (current["body"] + "\n" + line).strip()
    if current:
        sections.append(current)
    return sections


def main() -> None:
    parser = argparse.ArgumentParser(description="Render AI-Wrapped HTML report")
    parser.add_argument("features_json", help="features JSON from wrapped.py --json")
    parser.add_argument("output_html",   help="output HTML file path")
    parser.add_argument("--narrative",   default=None,
                        help="narrative markdown from wrapped.py --narrative-out")
    args = parser.parse_args()

    payload = json.loads(Path(args.features_json).read_text(encoding="utf-8"))
    narrative_sections = _parse_narrative_md(args.narrative) if args.narrative else None
    render(payload, narrative_sections, args.output_html)


if __name__ == "__main__":
    main()
