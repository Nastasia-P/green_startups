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
| 3 | `step3_firm_characteristics` | firm-characteristic tables (T4.1-T4.5, F4.1) + sample register | done |
| 4 | `step4_geography` | geography tables (T4.6-T4.8, AP2, F4.2, F4.3) | done |
| 5-7 | `step5..step7` | Chapter 4 exhibits | planned (see ROADMAP) |

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
# run against the raw extract
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

## Step 3 — Firm characteristics

Describes the two groups (green vs other European start-ups) before any funding
comparison: how old they are, how large, what they do, and where they sit in the
business-status and industry mix. This establishes whether a later funding gap could
be a composition effect (younger, larger, or capital-heavy firms) rather than a green
effect. Descriptive only — it computes no new per-firm variables and no funding
amounts; those come in later steps.

Reads the Step 2 firm table (`company_analysis.parquet`) plus three Step 1 clean
tables (`industries_clean`, `verticals_clean`, `deals_clean`).

```bash
# build from the local Step 2 + Step 1 outputs
python -m empirical_analysis.step3_firm_characteristics.run \
    --firm-table data/outputs/company_analysis.parquet \
    --clean-dir data/outputs/clean_tables \
    --output-dir data/outputs/chapter4

# on the target machine, the OneDrive paths resolve on their own
python -m empirical_analysis.step3_firm_characteristics.run
```

Paths resolve automatically; override if needed:

- firm table: `--firm-table` > `STEP3_FIRM_TABLE` > OneDrive `09_...\company_analysis.parquet` > `data/outputs/company_analysis.parquet`
- clean tables: `--clean-dir` > `STEP2_CLEAN_DIR` > OneDrive `09_...\clean_tables` > `data/outputs/clean_tables` > `data/interim`
- output dir: `--output-dir` > `STEP3_OUTPUT_DIR` > OneDrive `09_...\chapter4_outputs` > `data/outputs/chapter4`

What to expect (CSV files in the output dir):

| File | Contents |
|---|---|
| `T4_00_sample_register.csv` | For every Chapter 4 statistic: the population used, effective n (total / green / other), the inclusion rule, and why |
| `T4_01_master_descriptive.csv` | n, founding year/age, employees, business status, top industries, financing status, green vs other |
| `T4_02_business_status.csv` | business-status distribution, green vs other (raw, ungrouped) |
| `T4_03_industry_composition.csv` | industry mix; percentages can exceed 100% (firms carry multiple tags) |
| `T4_04_green_subsegments.csv` | green population broken down by PitchBook vertical |
| `T4_05_employment_by_cohort.csv` | median employees by founding cohort, green vs other |
| `F4_01_green_share_by_cohort.csv` | green share per founding cohort (cohort composition, not a time trend) |
| `captions.csv` | fixed captions that must travel with the figures |

Every statistic reports its own n, and missing values are treated as unknown (never
zero). The run ends by printing an acceptance report; a correct run shows 8,306 green
/ 107,699 other (116,005 total) and the cohort green counts summing to 8,306.

## Step 4 — Geography

Describes *where* European green start-ups are, and separates two things raw counts
conflate: **size** (how many green firms a country has) and **specialisation** (how
green its start-up base is relative to Europe, via the location quotient). A country
can be large and unremarkable or small and highly specialised — the location quotient
routinely inverts the raw-count ranking (in the current data the UK leads by green
count but Finland, Spain and Switzerland lead by specialisation). Descriptive only.

Reads the Step 2 firm table (`company_analysis.parquet`) plus a committed Eurostat
population file (`data/sources/eurostat_population.csv`) for the per-capita
cross-check. Country denominators use the full 116,005 population; a country needs
≥500 start-ups to get a row and a city ≥100.

```bash
# optional: refresh the Eurostat population file (needs network)
python -m empirical_analysis.step4_geography.fetch_eurostat

# build from the local Step 2 output
python -m empirical_analysis.step4_geography.run \
    --firm-table data/outputs/company_analysis.parquet \
    --population data/sources/eurostat_population.csv \
    --output-dir data/outputs/chapter4

# on the target machine, the OneDrive paths resolve on their own
python -m empirical_analysis.step4_geography.run
```

Paths resolve automatically; override if needed:

- firm table: `--firm-table` > `STEP4_FIRM_TABLE` > OneDrive `09_...\company_analysis.parquet` > `data/outputs/company_analysis.parquet`
- population: `--population` > `STEP4_POPULATION` > `data/sources/eurostat_population.csv`
- output dir: `--output-dir` > `STEP4_OUTPUT_DIR` > OneDrive `09_...\chapter4_outputs` > `data/outputs/chapter4`

What to expect (CSV files in the output dir):

| File | Contents |
|---|---|
| `T4_06_country_specialisation.csv` | per country (≥500 firms): green count, share of European green, green intensity, location quotient, plus Stage 1 / Stage 2+3 LQ variants |
| `T4_07_per_capita_crosscheck.csv` | same countries joined to Eurostat population: start-ups and green per million; unmatched countries (Russia, the post-2020 UK) kept with NA |
| `T4_08_concentration.csv` | top-5 / top-10 country and top-5 city shares, green vs other, each on its own denominator |
| `AP2_city_ranking.csv` | per city (≥100 firms): green count, share, intensity, modal country |
| `F4_02_green_count_by_country.csv` | figure data: absolute green count by country |
| `F4_03_lq_by_country.csv` | figure data: location quotient by country, with the LQ=1 reference line |
| `captions_step4.csv` | fixed captions that must travel with the tables/figures |

The location quotient uses the fixed EU-wide reference (green / population); `lq > 1`
means a country is more green-specialised than Europe overall. The run ends by printing
an acceptance report; a correct run shows 20 countries at ≥500 firms and a
Spearman(start-ups per million, green intensity) of about −0.63.

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
