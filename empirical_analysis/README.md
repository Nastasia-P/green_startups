# Empirical analysis pipeline

Chapter 4 analysis of green start-ups in Europe. The pipeline turns the raw 43-table
PitchBook extract into clean tables, a firm-level analysis table, and (in later steps)
the thesis exhibits. Each step is a self-contained Python module with its own spec
under [`specs/`](specs/).

See [`specs/ROADMAP.md`](specs/ROADMAP.md) for the full step-by-step plan and how each
step maps to the thesis output register.

## Steps

| Step | Module | Produces | Status |
|---|---|---|---|
| 1 | `step1_clean_raw_data` | 8 clean relational tables | done |
| 2 | `step2_firm_table` | `company_analysis.parquet` (1 row per firm) | done |
| 3-7 | `step3..step7` | Chapter 4 exhibits | planned (see ROADMAP) |

## Prerequisites

Python 3.12 with the packages in [`requirements.txt`](requirements.txt):

```bash
# on the analysis node, load the interpreter first
module load python/3.12.13-aocl5.3

pip install -r empirical_analysis/requirements.txt
```

Run every command from the repository root, as a module (`python -m ...`), so the
package imports resolve.

## Step 1 — Clean the raw data

Reads seven of the 43 raw CSVs and writes eight clean per-grain Parquet tables plus
reference lists and an audit. Full spec:
[`specs/step1_clean_raw_data/design.md`](specs/step1_clean_raw_data/design.md).

```bash
# smoke test on the committed sample (no raw extract needed)
python -m empirical_analysis.step1_clean_raw_data.run --mode fixture

# full run against the real extract
python -m empirical_analysis.step1_clean_raw_data.run --mode full
```

Paths resolve automatically; override if needed:

- extract dir: `--extract-dir` > `PITCHBOOK_EXTRACT_DIR` > OneDrive `02_Data\esade_20260707` > `data/raw`
- output dir: `--output-dir` > `STEP1_OUTPUT_DIR` > OneDrive `09_...\clean_tables` > `data/interim`

Inspect the output without writing a script:

```bash
python -m empirical_analysis.step1_clean_raw_data.peek --list
python -m empirical_analysis.step1_clean_raw_data.peek deals_clean --value-counts stage_group
```

## Step 2 — Build the firm-level table

Collapses the Step 1 tables to one row per firm and joins the company spine scalars,
producing `company_analysis.parquet` (116,005 rows). This is the single input for the
analysis steps. Full spec:
[`specs/step2_firm_table/design.md`](specs/step2_firm_table/design.md).

```bash
# build from the local Step 1 outputs
python -m empirical_analysis.step2_firm_table.run --clean-dir data/outputs/clean_tables --output-dir data/outputs

# on the target machine, the OneDrive paths resolve on their own
python -m empirical_analysis.step2_firm_table.run
```

Paths resolve automatically; override if needed:

- clean tables: `--clean-dir` > `STEP2_CLEAN_DIR` > OneDrive `09_...\clean_tables` > `data/outputs/clean_tables` > `data/interim`
- spine CSV: `--spine` (default `startups_stages_filtered.csv`)
- output dir: `--output-dir` > `STEP2_OUTPUT_DIR` > OneDrive `09_Python_Empirical Analysis` > `data/outputs`

Outputs: `company_analysis.parquet`, `step2_coverage.csv` (per-column completeness,
green vs other), `step2_audit.csv`.

## Acceptance anchors

A correct full run reproduces:

- population 116,005; green 8,306; green stages 6,636 / 834 / 836
- financed firms 47,714 (firms with at least one qualifying deal)
- coverage asymmetry: employees 82% green vs 50% other; total_raised 59% vs 24%

## Tests

```bash
python -m pytest empirical_analysis/ -q
```

## Data layout

| Path | Contents |
|---|---|
| `startups_stages_filtered.csv` | company spine, 94 columns, 116,005 firms |
| `data/outputs/startup_population_green_classification_strong_terms.csv` | green ledger |
| `data/outputs/clean_tables/` | Step 1 output |
| `data/outputs/company_analysis.parquet` | Step 2 output |
