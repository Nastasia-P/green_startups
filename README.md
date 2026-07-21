# green_startups

Scripts to clean the raw PitchBook export, narrow the full company list down to
startups, and filter it down to "green" (EU-taxonomy aligned) startups.

## Requirements

- Python 3.9+
- pandas

```bash
pip install pandas
```

## Filter the full company list to startups

`filter_independent_startups.py` streams the full PitchBook export
(`Company_Europe.csv`, ~5.4 GB, read in chunks) and keeps only companies that
look like young, independent startups. A row is kept when **all** of the
following hold:

1. **Universe (allow-only)** — every comma-separated token in `Universe` is one
   of `{Pre-venture, Venture Capital, Private Equity, Debt Financed}`, with at
   least one token present. Rows carrying `M&A`, `Publicly Listed`, or
   `Other Private Companies` (or empty) are dropped.
2. **OwnershipStatus** in `{Privately Held (no backing), Privately Held (backing),
   In IPO Registration}`.
3. **CompanyFinancingStatus** in a strict allow-set of backed / formerly-backed /
   corporation statuses (pending/failed transactions and `Potential Target` are
   dropped).
4. **Alive** — `BusinessStatus` not in `{Out of Business, Bankruptcy: Liquidation,
   Bankruptcy: Admin/Reorg}` (empty kept).
5. **Young** — `YearFounded` present and `2026 - YearFounded <= 10`.

It adds an `age_years` column and prints a per-`CompanyFinancingStatus` breakdown
plus `BusinessStatus == "Startup"` coverage.

```bash
# Full company export -> independent_startups.csv
python filter_independent_startups.py
```

Input/output are constants at the top of the script:

- `INPUT_PATH`  = `Company_Europe.csv`
- `OUTPUT_PATH` = `independent_startups.csv`

## Filter green startups

`filter_green_startups.py` scans each company's `Keywords` and `Description`
columns for EU-taxonomy `pitchbook_keywords` (whole-word, case-insensitive) and
writes the matches to `green_startups.csv`, adding a `matched_keywords` column
that records which terms triggered each match.

It reads `startups_cleaned.csv` by default, so run the cleaning step first if you
only have the raw export:

```bash
# 1. Clean the raw export -> startups_cleaned.csv (skip if already cleaned)
python clean_csv.py

# 2. Filter to green startups -> green_startups.csv
python filter_green_startups.py
```

### Input / output paths

Paths are defined as constants at the top of `filter_green_startups.py`:

- `INPUT_PATH`  = `startups_cleaned.csv`
- `OUTPUT_PATH` = `green_startups.csv`
- `SEARCH_COLUMNS` = `["Keywords", "Description"]`

Edit these constants to point at a different input file, change the output
location, or restrict matching to fewer columns.
