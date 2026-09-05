# Step 9 - Keyword-Recovery Robustness Diagnostic

A compact, **read-only** robustness check. It applies the thesis's own
environmental vocabulary (standalone tokens + multi-word phrases) independently to
the `Keywords` and `Description` text of all 116,005 firms, then measures how many
of the **6,636 Stage-1 firms** - those flagged green *only* via PitchBook's
CleanTech / Climate Tech verticals - are independently recovered by the text
vocabulary alone.

It adds nothing to any other step and modifies no existing classification: it only
reads prior outputs and writes its own new files.

## What it does

- Loads the canonical baseline [`data/outputs/clean_tables/population_key.parquet`](../../data/outputs/clean_tables/population_key.parquet)
  (116,005 firms; `green` = 8,306; `green_stage` vertical/token/phrase/none =
  6,636/834/836/107,699). This file is never written.
- Joins `Keywords`, `Description`, `Verticals` from
  [`startups_stages_filtered.csv`](../../startups_stages_filtered.csv).
- Applies the **token** and **phrase** matching rules imported unchanged from
  [`classify_startups_green_strong_terms.py`](../../classify_startups_green_strong_terms.py)
  (and helpers in `classify_startups_green_algorithmic.py`) to Keywords +
  Description for every firm. The **vertical stage is never used as a search
  signal**; `vertical_matches` is used only to split the Stage-1 firms into
  cohorts (CleanTech-only / Climate-Tech-only / both).

## Outputs (`data/outputs/chapter4/`)

- `keyword_recovery_firm_level.parquet` - 116,005 rows: baseline IDs/labels plus
  the per-firm diagnostics (`text_match_standalone`, `text_match_mwe`,
  `text_match_any`, `n_standalone`, `n_mwe`, `matched_standalone_terms`,
  `matched_mwes`, `is_stage1`, `vertical_cohort`).
- `T_keyword_recovery_stage1.csv` - headline recovery for the 6,636 Stage-1 firms.
- `T_keyword_recovery_by_vertical.csv` - the same metrics split by vertical cohort
  (cohorts sum to 6,636).
- `keyword_recovery_reconciliation.csv` - population/stage counts, vocabulary
  sizes, text-join coverage, the no-vertical-term guard, a `labels_modified=False`
  assertion, a dual-use sensitivity, and the resolved input paths for the run.
- `step9_keyword_recovery_report.txt` - this module's own separate, human-readable
  report.

## Run

Pure pandas + string matching (no network). From the repo root:

```
python -m empirical_analysis.step9_keyword_recovery.build
```

Every input can be pointed at a custom location, via CLI flags (highest priority)
or environment variables, falling back to the repo defaults:

```
python -m empirical_analysis.step9_keyword_recovery.build \
  --population /path/to/population_key.parquet \
  --spine      /path/to/startups_stages_filtered.csv \
  --standalone /path/to/strong_terms_active.csv \
  --phrases    /path/to/strong_term_phrases.csv \
  --out-dir    /path/to/outputs
```

Env vars: `KWR_POPULATION`, `KWR_CLEAN_DIR`, `KWR_SPINE`, `KWR_STANDALONE`,
`KWR_PHRASES`, `KWR_OUT_DIR`. The resolved paths are echoed into the reconciliation
CSV and the report so every run records exactly which inputs it consumed.

## Interpretation boundary

- This tests whether the independently-developed vocabulary can **recover** firms
  PitchBook already labels environmentally (CleanTech / Climate Tech). It is a
  convergent-validity check on the vocabulary, nothing more.
- It is **not** an estimate of classifier recall - PitchBook's vertical
  classification is not assumed to be complete ground truth.
- It is **not** a new definition of green start-ups, and it changes no existing
  label.

## Vocabulary caveat

The on-disk vocabulary carries **68 standalone tokens** and **456 multi-word
phrases**; the thesis text quotes **64 / 458**. The 64 reconciles exactly as the
68 minus the four dual-use tokens `nuclear`, `nuclears`, `biological`,
`biologicals` (a standalone-recovery sensitivity excluding these is reported in the
reconciliation file). The 458 has no exact on-disk source; the closest committed
count is 456. The module reports the actual sizes it applied alongside the thesis
figures.

## Thesis usage

Intended as a short robustness paragraph immediately after the existing sequential
identification table in Chapter 3: it quantifies how much of the vertical-only
Stage-1 cohort the environmental vocabulary would independently recover, supporting
the vocabulary's convergent validity without altering the classification.
