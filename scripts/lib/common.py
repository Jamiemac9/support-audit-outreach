"""Shared helpers for the Support Audit outreach scripts."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import requests

# Repo root = two levels up from scripts/lib/
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"

USER_AGENT = (
    "support-audit-outreach/0.1 "
    "(internal research tool; contact@supportaudit.co.uk)"
)

# Legal-form suffixes and filler words stripped before matching org names.
_SUFFIXES = [
    "limited", "ltd", "llp", "plc", "cic", "cio", "c i c",
    "community interest company",
    "charitable incorporated organisation",
    "registered society", "industrial and provident society",
    "housing association", "housing assoc", "housing society",
    "housing trust", "housing group", "housing",
    "association", "trust", "group", "company", "co",
    "the", "and", "&",
]

_PUNCT = re.compile(r"[^a-z0-9\s]")
_SPACE = re.compile(r"\s+")


def ensure_dirs() -> None:
    """Create the data directories if they are not there yet."""
    RAW.mkdir(parents=True, exist_ok=True)


def session() -> requests.Session:
    """A requests session with a polite User-Agent and sane timeouts."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def get(url: str, *, tries: int = 3, timeout: int = 60, **kwargs):
    """GET with a few retries. Raises on the final failure."""
    s = kwargs.pop("session", None) or session()
    last = None
    for attempt in range(1, tries + 1):
        try:
            r = s.get(url, timeout=timeout, **kwargs)
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001 - we re-raise below
            last = exc
            if attempt < tries:
                wait = 2**attempt
                log(f"  request failed ({exc}); retrying in {wait}s")
                time.sleep(wait)
    raise RuntimeError(f"GET failed after {tries} tries: {url}") from last


def download(url: str, dest: Path, *, session_=None) -> Path:
    """Stream a URL to a file on disk. Returns the path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    s = session_ or session()
    log(f"  downloading {url}")
    with s.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)
    size_mb = dest.stat().st_size / (1024 * 1024)
    log(f"  saved {dest.name} ({size_mb:.1f} MB)")
    return dest


def normalise_name(name: str) -> str:
    """
    Reduce an organisation name to a comparable key.

    'The Riverside Group Limited' -> 'riverside'
    'Riverside Housing Association Ltd.' -> 'riverside'

    This is deliberately aggressive. It is used for *candidate* matching
    only; anything below the auto-accept threshold goes to a review file
    for you to eyeball, never straight into the matched set.
    """
    if not name:
        return ""
    s = str(name).lower().strip()
    s = s.replace("’", "'").replace("&", " and ")
    s = _PUNCT.sub(" ", s)
    s = _SPACE.sub(" ", s).strip()

    words = s.split()
    # Strip suffix words from the end, repeatedly.
    changed = True
    while changed and words:
        changed = False
        for suffix in sorted(_SUFFIXES, key=lambda x: -len(x.split())):
            parts = suffix.split()
            n = len(parts)
            if len(words) > n and words[-n:] == parts:
                words = words[:-n]
                changed = True
                break

    # Drop remaining filler words anywhere in the string.
    filler = {"the", "and"}
    words = [w for w in words if w not in filler]

    return " ".join(words).strip()


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def find_column(columns, *candidates) -> str | None:
    """
    Find the first column whose lowercased name contains any candidate
    substring. Lets the scripts cope with slightly different headings.
    """
    lowered = {str(c).lower().strip(): c for c in columns}
    for cand in candidates:
        for low, original in lowered.items():
            if cand in low:
                return original
    return None
