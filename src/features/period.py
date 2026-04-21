from dataclasses import dataclass
from datetime import datetime
import pandas as pd


@dataclass(frozen=True)
class Period:
    """Inclusive date range used to scope feature computation.

    `name` is an opaque label (e.g. "2025", "may_2025", "renovation")
    surfaced in the final narrative; pick something readable.
    """
    name: str
    start: datetime
    end: datetime

    def contains(self, ts: datetime) -> bool:
        return self.start <= ts <= self.end


def filter_df(df: pd.DataFrame, period: Period | None) -> pd.DataFrame:
    """Return rows of df whose `timestamp` falls inside `period`.

    A None period is a no-op, so callers can pass period-or-None uniformly.
    """
    if period is None or df.empty:
        return df
    mask = (df["timestamp"] >= period.start) & (df["timestamp"] <= period.end)
    return df[mask].reset_index(drop=True)


def year_period(year: int) -> Period:
    return Period(
        name=str(year),
        start=datetime(year, 1, 1),
        end=datetime(year, 12, 31, 23, 59, 59),
    )


def last_n_days(df: pd.DataFrame, n: int) -> Period | None:
    """Build a period covering the last `n` days of df's timestamp range.

    Returns None if df is empty so downstream code can short-circuit.
    """
    if df.empty:
        return None
    end = df["timestamp"].max()
    start = end - pd.Timedelta(days=n)
    return Period(name=f"last_{n}d", start=start, end=end)
