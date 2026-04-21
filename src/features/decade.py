from collections import Counter


def decade_fingerprint(track_metas: list) -> dict:
    """Compute decade distribution from a list of TrackMetadata.

    Returns a small dict suitable for LLM prompt context.
    Tracks without a year are silently skipped.
    """
    years = [m.year for m in track_metas if m.year]
    if not years:
        return {}

    decade_counts: Counter = Counter()
    for year in years:
        decade_counts[(year // 10) * 10] += 1

    total = len(years)
    distribution = {
        f"{d}s": round(c / total, 2)
        for d, c in sorted(decade_counts.items())
    }
    dominant_decade_int = decade_counts.most_common(1)[0][0]
    dominant_decade = f"{dominant_decade_int}s"

    span_decades = max(decade_counts) - min(decade_counts)
    if span_decades >= 40:
        era_label = "eclectic"
    elif dominant_decade_int >= 2020:
        era_label = "contemporary"
    elif dominant_decade_int <= 1990:
        era_label = "catalog_digger"
    else:
        era_label = "modern_catalog"

    return {
        "dominant_decade": dominant_decade,
        "distribution": distribution,
        "earliest_year": min(years),
        "latest_year": max(years),
        "covered_decades": len(decade_counts),
        "era_label": era_label,
    }
