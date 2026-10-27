#!/usr/bin/env python3
"""
Step 1 — Download the RSH register of social housing providers.

The Regulator of Social Housing publishes a snapshot of every registered
provider roughly mid-month. It gives the provider name, the RSH
registration number, and whether they are non-profit or profit-making.
It does NOT include addresses or contact details — those come later from
Companies House and the Charity Commission.

The RSH registration number is the key everything else joins on, so this
runs first.

Usage:
    python scripts/01_fetch_rsh.py
    python scripts/01_fetch_rsh.py --url https://.../specific-file.xlsx

Output:
    data/raw/<original filename>   the untouched download
    data/rp-register.csv           cleaned: rsh_number, org_name, designation, match_name
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import DATA, RAW, download, ensure_dirs, find_column, get, log, normalise_name  # noqa: E402

PUBLICATION_PAGE = (
    "https://www.gov.uk/government/publications/"
    "current-registered-providers-of-social-housing"
)

ASSET_RE = re.compile(
    r'https://assets\.publishing\.service\.gov\.uk/[^"\'\s<>]+\.(?:xlsx|xls|csv|ods)',
    re.IGNORECASE,
)


def discover_download_url() -> str:
    """
    Scrape the gov.uk publication page for the spreadsheet link.

    We parse rather than hardcode because RSH republishes under a new
    filename every month. If this ever breaks, open the page yourself,
    copy the spreadsheet link, and pass it with --url.
    """
    log(f"Looking up the current register on {PUBLICATION_PAGE}")
    html = get(PUBLICATION_PAGE).text
    urls = ASSET_RE.findall(html)
    if not urls:
        raise SystemExit(
            "Could not find a spreadsheet link on the RSH publication page.\n"
            "Open it in a browser, copy the link to the current register, "
            "and re-run with:\n"
            "    python scripts/01_fetch_rsh.py --url <paste link here>"
        )

    # Deduplicate, keep order.
    seen, ordered = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)

    # Prefer a file that looks like the register itself rather than the
    # separate registrations/de-registrations lists.
    def score(u: str) -> int:
        name = u.rsplit("/", 1)[-1].lower()
        s = 0
        if "regis" in name and "de-regis" not in name and "deregis" not in name:
            s += 2
        if "provider" in name:
            s += 2
        if "current" in name or "list" in name:
            s += 1
        if "de-regis" in name or "deregis" in name:
            s -= 5
        return s

    best = sorted(ordered, key=score, reverse=True)[0]
    log(f"  chose {best.rsplit('/', 1)[-1]}")
    if len(ordered) > 1:
        log(f"  ({len(ordered)} candidate files on the page; "
            "pass --url if this picked the wrong one)")
    return best


def read_register(path: Path) -> pd.DataFrame:
    """
    Read the downloaded file, finding the real header row.

    RSH spreadsheets usually carry a title and some notes above the table,
    so we hunt for the row that actually contains the column headings.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        raw = pd.read_csv(path, header=None, dtype=str,
                          keep_default_na=False, encoding_errors="replace")
    else:
        engine = "odf" if suffix == ".ods" else None
        raw = pd.read_excel(path, header=None, dtype=str, engine=engine)

    header_row = None
    for i in range(min(30, len(raw))):
        cells = " | ".join(str(c).lower() for c in raw.iloc[i].tolist())
        has_number = "registration number" in cells or "reg number" in cells or "rp code" in cells
        has_name = "name" in cells
        if has_number and has_name:
            header_row = i
            break

    if header_row is None:
        raise SystemExit(
            f"Could not find the header row in {path.name}.\n"
            "Open the file and check its layout — RSH may have changed the format."
        )

    log(f"  header found on row {header_row + 1}")
    df = raw.iloc[header_row + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[header_row].tolist()]
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", help="Spreadsheet URL to use instead of auto-discovery")
    args = ap.parse_args()

    ensure_dirs()

    url = args.url or discover_download_url()
    filename = url.rsplit("/", 1)[-1].split("?")[0]
    local = download(url, RAW / filename)

    log(f"Reading {local.name}")
    df = read_register(local)

    num_col = find_column(df.columns, "registration number", "reg number", "rp code", "number")
    name_col = find_column(df.columns, "organisation name", "provider name", "name")
    desig_col = find_column(df.columns, "designation", "profit", "type", "status")

    if not num_col or not name_col:
        raise SystemExit(
            f"Expected a number column and a name column, got: {list(df.columns)}"
        )

    out = pd.DataFrame({
        "rsh_number": df[num_col].astype(str).str.strip(),
        "org_name": df[name_col].astype(str).str.strip(),
        "designation": (df[desig_col].astype(str).str.strip()
                        if desig_col else ""),
    })

    # Drop blanks and footnote rows that trail the real table.
    out = out[out["org_name"].str.len() > 1]
    out = out[~out["org_name"].str.lower().str.startswith(("note", "source", "total"))]
    out = out[out["rsh_number"].str.strip().ne("")]
    out = out[out["rsh_number"].str.lower().ne("nan")]

    out["match_name"] = out["org_name"].map(normalise_name)
    out = out.drop_duplicates(subset=["rsh_number"]).reset_index(drop=True)

    dest = DATA / "rp-register.csv"
    out.to_csv(dest, index=False)

    log("")
    log(f"Wrote {dest} — {len(out)} registered providers")
    log("")
    log("Sample:")
    for _, row in out.head(5).iterrows():
        log(f"  {row['rsh_number']:>6}  {row['org_name'][:50]:<50}  -> {row['match_name']}")
    log("")
    log("Open data/rp-register.csv and check it looks sane before running step 2.")


if __name__ == "__main__":
    main()
