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

Filters `Company_Europe.csv` down to young, independent startups and writes
`independent_startups.csv`:

```bash
python filter_independent_startups.py
```

## Filter startups stage by stage

`filter_startups_stages.py` filters `Company_Europe.csv` through four sequential
stages and writes survivors to `startups_stages_filtered.csv`. A row must pass
each stage to reach the next:

1. **Young** - `YearFounded` present and `2026 - YearFounded <= 10` (missing year dropped).
2. **Ownership** - `OwnershipStatus` is privately held or in IPO registration
   (`Out of Business` is dropped at this stage).
3. **Universe** - every comma-separated `Universe` token is allowed
   (`Pre-venture`, `Venture Capital`, `Private Equity`, `Debt Financed`) and at
   least one is present.
4. **Alive** - `BusinessStatus` is not bankrupt/defunct (empty is kept as unknown).

Each stage prints why companies were filtered out (kept/dropped counts plus a
breakdown of the failing values).

```bash
python filter_startups_stages.py
```

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
