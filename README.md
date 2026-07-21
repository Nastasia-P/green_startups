# green_startups

Scripts to clean the raw PitchBook export and filter it down to "green"
(EU-taxonomy aligned) startups.

## Requirements

- Python 3.9+
- pandas

```bash
pip install pandas
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
