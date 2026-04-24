"""OpenRouter-backed narrative generator.

We call OpenRouter's OpenAI-compatible chat completions endpoint directly
via `requests` — no extra SDK. Default model is a Claude Sonnet variant;
override via `OPENROUTER_MODEL` env or the `model` parameter.

Flow: build system + user prompt, POST, parse JSON body, validate names.
On validation failure the caller may re-invoke with `offender_hint` set —
we append it to the system prompt so the model knows what to fix.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass

import requests

from .context import build_allowed_names, build_context
from .prompt import system_prompt, user_prompt
from .verify import VerifyResult, verify_names


DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_CLAUDE_BIN = shutil.which("claude") or "/home/andrew/.vscode-oss/extensions/anthropic.claude-code-2.1.119-linux-x64/resources/native-binary/claude"


@dataclass
class Narrative:
    sections: list[dict]  # [{title, body}, ...]
    artists_mentioned: list[str]
    verify: VerifyResult
    raw: str  # the full model response string, for debugging

    def as_text(self) -> str:
        """Render sections as plain markdown for CLI display."""
        parts: list[str] = []
        for s in self.sections:
            parts.append(f"## {s.get('title', '').strip()}")
            parts.append(s.get("body", "").strip())
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"


class NarrativeError(RuntimeError):
    """Raised when the model response cannot be parsed or fails validation twice."""


def _extract_json(raw: str) -> dict:
    """Model sometimes wraps JSON in ```json fences even when told not to."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    return json.loads(s)


def _call_openrouter(
    system: str,
    user: str,
    *,
    api_key: str,
    model: str,
    temperature: float,
    timeout: int,
    rate_limit_retries: int = 4,
    rate_limit_backoff: float = 15.0,
) -> str:
    """POST to OpenRouter and return the assistant message content.

    Retries up to `rate_limit_retries` times on 429 with exponential backoff,
    since free-tier models are often temporarily rate-limited upstream.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    for attempt in range(rate_limit_retries + 1):
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 429 and attempt < rate_limit_retries:
            wait = rate_limit_backoff * (2 ** attempt)
            print(f"[narrative] rate-limited (429), retrying in {wait:.0f}s "
                  f"(attempt {attempt + 1}/{rate_limit_retries})...")
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            raise NarrativeError(
                f"OpenRouter {resp.status_code}: {resp.text[:500]}"
            )
        break
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise NarrativeError(f"Malformed OpenRouter response: {data!r}") from e


def _call_claude_cli(system: str, user: str, *, timeout: int) -> str:
    """Call the local claude CLI binary (Claude Code) in print mode.

    Used for local testing without an OpenRouter key. Passes system + user
    prompt concatenated, since the CLI doesn't have separate role args.
    """
    if not os.path.exists(_CLAUDE_BIN):
        raise NarrativeError(f"Claude CLI not found at {_CLAUDE_BIN!r}")
    prompt = f"{system}\n\n---\n\n{user}"
    try:
        result = subprocess.run(
            [_CLAUDE_BIN, "-p", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise NarrativeError(f"Claude CLI timed out after {timeout}s") from e
    if result.returncode != 0:
        raise NarrativeError(f"Claude CLI error: {result.stderr[:500]}")
    return result.stdout.strip()


def generate_narrative(
    payload: dict,
    *,
    voice: str = "a",
    lang: str = "ru",
    model: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.8,
    timeout: int = 300,
    max_retries: int = 1,
    backend: str = "openrouter",
) -> Narrative:
    """Generate a Wrapped narrative from the full `wrapped.py --json` payload.

    `max_retries=1` means: one initial attempt, plus up to one retry if the
    first output mentions artists outside the whitelist. After the retry the
    result is returned regardless — with `verify.ok=False` if still invalid.
    """
    if backend == "openrouter":
        api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise NarrativeError(
                "OPENROUTER_API_KEY is not set. Add it to .env or pass api_key=."
            )
    model = model or os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL

    context = build_context(payload)
    allowed = build_allowed_names(context.get("features", {}))

    system = system_prompt(voice, lang)
    user = user_prompt(context, lang)

    last_raw = ""
    last_result: VerifyResult | None = None
    last_parsed: dict = {}

    for attempt in range(max_retries + 1):
        retry_system = system
        if attempt > 0 and last_result is not None:
            retry_system = system + "\n\nRETRY NOTE: " + last_result.error_hint()

        if backend == "cli":
            last_raw = _call_claude_cli(retry_system, user, timeout=timeout)
        else:
            last_raw = _call_openrouter(
                retry_system, user,
                api_key=api_key, model=model,
                temperature=temperature, timeout=timeout,
            )
        try:
            last_parsed = _extract_json(last_raw)
        except json.JSONDecodeError as e:
            if attempt >= max_retries:
                raise NarrativeError(
                    f"Model returned non-JSON on final attempt: {e}. "
                    f"Raw: {last_raw[:500]}"
                ) from e
            continue

        mentioned = last_parsed.get("artists_mentioned", []) or []
        last_result = verify_names(mentioned, allowed)
        if last_result.ok:
            break

    return Narrative(
        sections=last_parsed.get("sections", []) or [],
        artists_mentioned=last_parsed.get("artists_mentioned", []) or [],
        verify=last_result or VerifyResult(ok=True, offenders=[]),
        raw=last_raw,
    )
