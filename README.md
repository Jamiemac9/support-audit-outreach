# Support Audit — Outreach

Builds and maintains the prospect list for Support Audit (supportaudit.co.uk),
from free public data. No paid enrichment tools.

Everything runs as numbered scripts. Each one writes a CSV you can open and
check before moving to the next. If step 1's output looks wrong, fix step 1 —
don't build step 2 on top of it.

---

## One-time setup

You need Python 3.10 or newer.

```bash
git clone https://github.com/Jamiemac9/support-audit-outreach
cd support-audit-outreach

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env               # Windows: copy .env.example .env
```

Then open `.env` and paste in your API keys. `.env` is gitignored, so your
keys never get committed.

| Key | Where to get it | Needed for |
|---|---|---|
| `COMPANIES_HOUSE_API_KEY` | [developer.company-information.service.gov.uk](https://developer.company-information.service.gov.uk/) | Step 4 (directors) |
| `CHARITY_COMMISSION_API_KEY` | [api-portal.charitycommission.gov.uk](https://api-portal.charitycommission.gov.uk/) | Optional — step 3 uses the bulk download, which needs no key |

Both are free and take about five minutes each.

---

## The steps

### Step 1 — Get the register of providers

```bash
python scripts/01_fetch_rsh.py
```

Downloads the Regulator of Social Housing's current list of registered
providers and cleans it into `data/rp-register.csv`.

That file has four columns: `rsh_number`, `org_name`, `designation`,
`match_name`. **`rsh_number` is the key everything else joins on** — never
match organisations on name alone, because half the sector shares words like
"Housing Association Limited".

`match_name` is the name stripped down for comparison: *The Riverside Group
Limited* becomes `riverside`.

If the script can't find the download link (RSH republishes under a new
filename monthly), open the page it names, copy the spreadsheet link, and run:

```bash
python scripts/01_fetch_rsh.py --url <paste the link>
```

**Check before moving on:** open `data/rp-register.csv`. You should see
roughly 1,300–1,500 rows and recognise the big names.

---

### Step 2 — Match your existing list

Export your current contact list to CSV and save it as `data/my-list.csv`.
It can have any columns you like — the script works out which one holds the
organisation name.

```bash
python scripts/02_match_list.py
```

Three files come out:

| File | What it is |
|---|---|
| `data/matched.csv` | Your rows, stamped with their RSH number |
| `data/review.csv` | Near-misses — **your judgement needed**, not auto-matched |
| `data/gaps.csv` | Providers on the register you don't have yet |

`gaps.csv` is the answer to "who am I missing". It feeds steps 3 and 4.

Work through `review.csv` by hand. If something in there is a real match, fix
the spelling in `my-list.csv` and re-run. Don't lower the threshold to make
the number go up — that puts wrong matches into `matched.csv`, and a wrong
match means messaging the wrong person about the wrong organisation.

Options:

```bash
python scripts/02_match_list.py --name-column "Company"   # if auto-detect picks wrong
python scripts/02_match_list.py --threshold 92            # stricter
```

---

### Steps 3 and 4 — not written yet

- **Step 3** — Charity Commission bulk download, for trustees and board members
  (your chairs and governance contacts).
- **Step 4** — Companies House API, for directors of the non-charity providers
  and the Birmingham managing agents.

---

## Notes

- `data/raw/` holds untouched downloads and is gitignored — it's re-fetchable.
- `data/my-list.csv` is gitignored by default. If the repo is private and you'd
  rather version it, remove that line from `.gitignore`.
- Nothing here touches LinkedIn. Sales Navigator data is pulled across by hand —
  automated scraping risks the account, and the account is the business.
