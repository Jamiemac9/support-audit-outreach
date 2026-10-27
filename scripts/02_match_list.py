#!/usr/bin/env python3
"""
Step 2 — Match your existing contact list against the RSH register.

Answers the question: which registered providers do I already have, and
which am I missing?

Input:
    data/my-list.csv       your own list. Any columns; the script finds
                           the organisation name column itself, or use
                           --name-column to say which one.
    data/rp-register.csv   produced by step 1.

Output:
    data/matched.csv   your rows, stamped with the RSH number
    data/review.csv    near-misses for you to eyeball — NOT auto-matched
    data/gaps.csv      providers on the register that you do not have

Usage:
    python scripts/02_match_list.py
    python scripts/02_match_list.py --name-column "Company"
    python scripts/02_match_list.py --threshold 92
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import DATA, find_column, log, normalise_name  # noqa: E402

AUTO_ACCEPT = 90   # at or above this, treat as the same organisation
REVIEW_FLOOR = 75  # between floor and accept, send to review.csv


def load_my_list(path: Path, name_column: str | None) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        raise SystemExit(
            f"{path} not found.\n\n"
            "Export your existing list to CSV and save it there. It can have\n"
            "any columns you like — the script only needs one holding the\n"
            "organisation name."
        )

    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding_errors="replace")
    if df.empty:
        raise SystemExit(f"{path} has no rows.")

    col = name_column or find_column(
        df.columns,
        "organisation", "organization", "company", "provider",
        "client", "account", "org", "name",
    )
    if not col:
        raise SystemExit(
            f"Could not work out which column holds the organisation name.\n"
            f"Columns found: {list(df.columns)}\n"
            f"Re-run with --name-column \"<the right one>\""
        )
    if col not in df.columns:
        raise SystemExit(f"Column {col!r} is not in {path.name}: {list(df.columns)}")

    log(f"Using {col!r} as the organisation name column")
    return df, col


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name-column", help="Column in my-list.csv holding the org name")
    ap.add_argument("--threshold", type=int, default=AUTO_ACCEPT,
                    help=f"Auto-accept score, 0-100 (default {AUTO_ACCEPT})")
    args = ap.parse_args()

    register_path = DATA / "rp-register.csv"
    if not register_path.exists():
        raise SystemExit("data/rp-register.csv not found — run step 1 first.")

    register = pd.read_csv(register_path, dtype=str, keep_default_na=False)
    mine, name_col = load_my_list(DATA / "my-list.csv", args.name_column)

    mine = mine.copy()
    mine["match_name"] = mine[name_col].map(normalise_name)

    # Lookup from normalised name -> register row index.
    choices = register["match_name"].tolist()

    matched_rows, review_rows = [], []
    matched_rsh_numbers = set()

    for _, row in mine.iterrows():
        key = row["match_name"]
        if not key:
            review_rows.append({
                **row.to_dict(),
                "rsh_number": "",
                "register_name": "",
                "score": 0,
                "reason": "blank or unparseable name",
            })
            continue

        hit = process.extractOne(key, choices, scorer=fuzz.token_sort_ratio)
        if hit is None:
            review_rows.append({**row.to_dict(), "rsh_number": "",
                                "register_name": "", "score": 0,
                                "reason": "no candidate"})
            continue

        best_name, score, idx = hit
        reg_row = register.iloc[idx]

        if score >= args.threshold:
            matched_rows.append({
                **row.to_dict(),
                "rsh_number": reg_row["rsh_number"],
                "register_name": reg_row["org_name"],
                "designation": reg_row.get("designation", ""),
                "score": round(score),
            })
            matched_rsh_numbers.add(reg_row["rsh_number"])
        elif score >= REVIEW_FLOOR:
            review_rows.append({
                **row.to_dict(),
                "rsh_number": reg_row["rsh_number"],
                "register_name": reg_row["org_name"],
                "score": round(score),
                "reason": "below auto-accept — confirm or reject by hand",
            })
        else:
            review_rows.append({
                **row.to_dict(),
                "rsh_number": "",
                "register_name": reg_row["org_name"],
                "score": round(score),
                "reason": "not a registered provider, or named very differently",
            })

    matched = pd.DataFrame(matched_rows)
    review = pd.DataFrame(review_rows)
    gaps = register[~register["rsh_number"].isin(matched_rsh_numbers)].copy()

    for name, frame in (("matched", matched), ("review", review), ("gaps", gaps)):
        dest = DATA / f"{name}.csv"
        frame.to_csv(dest, index=False)

    log("")
    log("=" * 60)
    log(f"  Your list:            {len(mine):>5} rows")
    log(f"  Matched to register:  {len(matched):>5}  -> data/matched.csv")
    log(f"  Need your eyes on:    {len(review):>5}  -> data/review.csv")
    log(f"  Register gaps:        {len(gaps):>5}  -> data/gaps.csv")
    log("=" * 60)
    log("")
    log("Open data/review.csv first. Anything in there that IS a genuine match,")
    log("fix the name in my-list.csv and re-run — that is cheaper than")
    log("loosening the threshold and polluting matched.csv.")


if __name__ == "__main__":
    main()
