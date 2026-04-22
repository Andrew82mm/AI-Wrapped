"""Hallucination guard for generated narratives.

MVP: the model is required to self-report every artist/track it mentioned
via the `artists_mentioned` field. We validate that each reported name
appears in the whitelist collected from the input features. A name counts
as valid if it matches (case-insensitively, stripped) any allowed artist
*or* track — tracks are allowed because models sometimes quote song titles
verbatim, and a track title overlapping an allowed artist name shouldn't
fail the check.

This does not catch the adversarial case where the model mentions an artist
in body text but omits it from `artists_mentioned`. That's an upgrade path
(scan body against a proper-noun extractor) left to a future iteration.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VerifyResult:
    ok: bool
    offenders: list[str]  # names reported by the model that aren't in the whitelist

    def error_hint(self) -> str:
        """A hint string suitable for inclusion in a retry prompt."""
        joined = ", ".join(repr(n) for n in self.offenders)
        return (
            f"The following names were mentioned but do not exist in the "
            f"input data: {joined}. Remove them or replace with names that "
            f"actually appear in `features`."
        )


def _normalize(s: str) -> str:
    return s.strip().casefold()


def verify_names(
    artists_mentioned: list[str],
    allowed: dict[str, set[str]],
) -> VerifyResult:
    """Check every self-reported name against the whitelist."""
    allowed_norm = {_normalize(n) for n in allowed.get("artists", set())}
    allowed_norm |= {_normalize(n) for n in allowed.get("tracks", set())}

    offenders: list[str] = []
    for name in artists_mentioned or []:
        if _normalize(name) not in allowed_norm:
            offenders.append(name)

    return VerifyResult(ok=not offenders, offenders=offenders)
