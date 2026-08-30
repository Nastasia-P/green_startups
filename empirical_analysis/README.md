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
| 5 | `step5_funding` | funding tables (T4.9-T4.17 incl. T4.12, F4.4) | done |
| 6 | `step6_investors` | investor & grant tables (T4.18-T4.19, T4.21-T4.23, T4.25, F4.5) | done |
| 7 | `step7_geo_finance` | geography x finance (T4.26, T4.28, T4.29, F-data) + by-country comparison of all Step 5/6 tables | done |
| 8 | `step8_verify` | cross-table reconciliation (`step8_reconciliation.csv`) | done |

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

`step2_coverage.csv` has six columns: `column`, `origin`, `derivation`, `pct_all`,
`pct_green`, `pct_other`. The `origin` says where each firm-table column comes from and
`derivation` states the rule that produces it, so the coverage numbers are
self-explaining. The `origin` values are:

| `origin` value | Meaning |
|---|---|
| `spine` | the company spine CSV (`startups_stages_filtered.csv`), i.e. PitchBook company scalars like founding year, country, employees, industry, `TotalRaised` |
| `green classification` | the green-label file (loaded as `population_key`, from `startup_population_green_classification_strong_terms.csv`): `green` is the 1/0 green-start-up flag, with `green_stage` / `green_signal_group` recording how the label was assigned |
| `deals_clean` | the Step 1 deal table — one row per financing deal; source of every deal count, flag, date and size |
| `company_investors_clean` (× `investors_clean`) | the Step 1 firm↔investor links, joined to the investor table for type and country — source of the investor count, type flags and origin shares |
| `deal_investors_clean × investors_clean × deals_clean` | the deal↔investor links joined through to firms — source of same-deal public/private co-investment |
| `derived` | computed inside Step 2 from the columns named in `derivation` (e.g. `age_years = REFERENCE_YEAR - year_founded`, `financed = n_deals >= 1`) |

`step2_coverage.csv` is the ground truth for every coverage figure quoted below. The
analysis steps read from three **confidence tiers**, and the sections that follow tag
each column accordingly:

- **High** — populated for ~95%+ of both groups (structural fields and the count/flag
  columns Step 2 derives directly). Group comparisons are on equal footing.
- **Medium (asymmetric)** — well-covered for green but thin for other (the 2-2.5x
  coverage gap). Directional and reliable *within a subsample that conditions on having
  a record*, but a raw full-population comparison would measure coverage, not substance.
  This asymmetry is the reason Steps 5-6 report on the financed / INVESTED subsamples.
- **Low** — sparse even within the subsample (deal sizes, valuations, lead flags).
  Reported with n shown prominently and read as indicative, not precise.

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

### Columns used and data coverage

| Column(s) | Used for | Coverage (green / other) | Confidence |
|---|---|---|---|
| `green`, `green_signal_group` | group split; R1 Stage 1 vs Stage 2+3 | 100% / 100% | High |
| `year_founded`, `age_years`, `cohort` | age and founding-cohort rows (T4.1, T4.5, F4.1) | 100% / 100% | High |
| `hq_country` | restrict to European firms | 100% / 100% | High |
| `primary_sector`, `primary_industry_group`, `primary_industry_code` | industry mix (T4.3) | 100% / 99% | High |
| `financed`, `any_*` flags, `n_deals` | financing-status snapshot in the master descriptive (T4.1) | 100% / 100% | High |
| `employees`, `employee_band` | size medians and bands (T4.1, T4.5) | 82% / 50% | Medium — green solid, other thin; read the "other" size as a floor |
| `business_status` | status mix (T4.2) | 98% / 45% | Medium — "other" shares rest on under-half coverage |
| `verticals_clean` (Step 1) | green subsegments (T4.4) | green vertical-tagged only | Medium — covers Stage-1 (tagged) green; text-signal green may carry no vertical |

Age, cohort, geography and industry are fully populated, so the composition story
(T4.1-T4.4) rests on high-confidence fields. The one caution is **size and status**:
green firms are far better documented, so the median-employee and status comparisons
are directional rather than exact for the "other" group.

## Step 4 — Geography

Describes *where* European green start-ups are, and separates two things raw counts
conflate: **size** (how many green firms a country has) and **specialisation** (how
green its start-up base is relative to Europe, via the location quotient). A country
can be large and unremarkable or small and highly specialised — the location quotient
routinely inverts the raw-count ranking (in the current data the UK leads by green
count but Finland, Spain and Switzerland lead by specialisation). Descriptive only.

Reads the Step 2 firm table (`company_analysis.parquet`) plus a committed World Bank
population file (`data/sources/worldbank_population.csv`) for the per-capita
cross-check. Country denominators use the full 116,005 population. The country floor
was dropped (per request): every country with at least one start-up gets a row and
thin cells carry `low_n_flag` (green < 30); cities still need ≥100 start-ups.

```bash
# optional: refresh the World Bank population file (needs network)
python -m empirical_analysis.step4_geography.fetch_worldbank

# build from the local Step 2 output
python -m empirical_analysis.step4_geography.run \
    --firm-table data/outputs/company_analysis.parquet \
    --population data/sources/worldbank_population.csv \
    --output-dir data/outputs/chapter4

# on the target machine, the OneDrive paths resolve on their own
python -m empirical_analysis.step4_geography.run
```

Paths resolve automatically; override if needed:

- firm table: `--firm-table` > `STEP4_FIRM_TABLE` > OneDrive `09_...\company_analysis.parquet` > `data/outputs/company_analysis.parquet`
- population: `--population` > `STEP4_POPULATION` > `data/sources/worldbank_population.csv`
- output dir: `--output-dir` > `STEP4_OUTPUT_DIR` > OneDrive `09_...\chapter4_outputs` > `data/outputs/chapter4`

What to expect (CSV files in the output dir):

| File | Contents |
|---|---|
| `T4_06_country_specialisation.csv` | per country (all countries): green count, share of European green, green intensity, location quotient, plus Stage 1 / Stage 2+3 LQ variants; `low_n_flag` marks thin rows |
| `T4_07_per_capita_crosscheck.csv` | same countries joined to World Bank population (SP.POP.TOTL): start-ups and green per million; all 46 countries matched |
| `T4_08_concentration.csv` | top-5 / top-10 country and top-5 city shares, green vs other, each on its own denominator |
| `AP2_city_ranking.csv` | per city (≥100 firms): green count, share, intensity, modal country |
| `F4_02_green_count_by_country.csv` | figure data: absolute green count by country |
| `F4_03_lq_by_country.csv` | figure data: location quotient by country, with the LQ=1 reference line |
| `captions_step4.csv` | fixed captions that must travel with the tables/figures |

The location quotient uses the fixed EU-wide reference (green / population); `lq > 1`
means a country is more green-specialised than Europe overall. The run ends by printing
an acceptance report; a correct run shows all 46 countries reported (20 at the former
≥500 floor, printed as a sensitivity), the full 116,005 firms retained in the
denominators, 21 rows flagged `low_n_flag`, and a Spearman(start-ups per million, green
intensity) of about −0.63.

### Columns used and data coverage

| Column(s) | Used for | Coverage (green / other) | Confidence |
|---|---|---|---|
| `hq_country` | country counts, intensity, location quotient (T4.6-T4.8, F4.2, F4.3) | 100% / 100% | High |
| `hq_city` | city ranking (AP2), top-5 city concentration (T4.8) | 98.5% / 99.4% | High |
| `green`, `green_signal_group` | green counts/intensity; Stage 1 vs Stage 2+3 LQ variants | 100% / 100% | High |
| `worldbank_population.csv` (external) | per-capita cross-check (T4.7) | matched for all 46/46 countries (single latest World Bank vintage, SP.POP.TOTL) | Medium — external join; World Bank current-year estimate |

Location fields are essentially complete, so the specialisation ranking is
high-confidence. Only the **per-capita cross-check** carries a caveat, and it is a
cross-check rather than a headline, and with World Bank every country is matched, so
no country carries NA population. The country floor is off (`MIN_COUNTRY_N = 1`), so every
country appears and thin rows are marked with `low_n_flag` rather than dropped; cities
keep their `MIN_CITY_N = 100` floor.

## Step 5 — Funding

The core of the chapter: does green start-ups' financing differ from other European
start-ups? It follows **access -> amount -> timing/stage -> trajectory**. The central
design choice is that **access is measured on the full 116,005 population, but amounts
are compared only within the financed subsample** (firms with a real deal record).
Green firms are 2-2.5x better documented, so comparing raw amounts across everyone
would measure coverage, not capital. Missing funding is treated as unobserved, never as
zero. Lifetime amounts are reported within founding cohort (a 2017 firm has had far
longer to raise than a 2025 one); horizon and follow-on measures are censored to firms
old enough to have a full observation window.

Reads the Step 2 firm table (`company_analysis.parquet`) plus the Step 1 `deals_clean`
table (for the deal-level stage and size cuts).

```bash
# build from the local Step 2 + Step 1 outputs
python -m empirical_analysis.step5_funding.run \
    --firm-table data/outputs/company_analysis.parquet \
    --clean-dir data/outputs/clean_tables \
    --output-dir data/outputs/chapter4

# on the target machine, the OneDrive paths resolve on their own
python -m empirical_analysis.step5_funding.run
```

Paths resolve automatically; override if needed:

- firm table: `--firm-table` > `STEP5_FIRM_TABLE` > OneDrive `09_...\company_analysis.parquet` > `data/outputs/company_analysis.parquet`
- clean tables: `--clean-dir` > `STEP2_CLEAN_DIR` > OneDrive `09_...\clean_tables` > `data/outputs/clean_tables` > `data/interim`
- output dir: `--output-dir` > `STEP5_OUTPUT_DIR` > OneDrive `09_...\chapter4_outputs` > `data/outputs/chapter4`

What to expect (CSV files in the output dir):

| File | Contents |
|---|---|
| `T4_09_funding_access.csv` | access flags (any financing / VC / grant / debt / accelerator / growth-PE / crowdfunding), green vs other, full population |
| `T4_09b_funding_access_by_cohort.csv` | founding-cohort-adjusted access: any financing / VC / grant / accelerator, green vs other, within each cohort (shares use the cohort group's own denominator; `low_n_flag` marks thin cohorts) |
| `T4_10_total_raised_by_cohort.csv` | total_raised (plus last and typical deal size) by cohort, financed subsample: median, IQR, mean, P90, ratio |
| `T4_11_first_financing_size_by_stage.csv` | first deal size by stage, with the Actual-vs-Estimated share |
| `T4_12_post_valuation.csv` | post-money valuation, green vs other; low coverage, so n is reported prominently |
| `T4_13_time_to_financing.csv` | years to first financing and to first VC, overall and by cohort (the headline timing result) |
| `T4_14_first_financing_type.csv` | composition of the first deal's stage, green vs other |
| `T4_15_stage_composition.csv` | share of all deals at each stage (deal grain) |
| `T4_16_median_deal_size_by_stage.csv` | median deal size by stage, incl. a Grant row |
| `T4_17_financing_trajectories.csv` | rounds per firm, follow-on interval, stage progression (censored) |
| `F4_04_cumulative_financed.csv` | figure data: cumulative share financed (and VC-backed) by years since founding |
| `captions_step5.csv` | fixed captions that must travel with the tables |

Every statistic reports its own n, amount tables carry only financed firms, and each
table ends with `n_green`, `n_others`, `n_startups`. The run ends by printing an
acceptance report; a correct run shows the financed subsample of 47,714, T4.15 deals
equal to the `deals_clean` row count, and green reaching first financing about as fast
as others but first VC more slowly.

### Columns used and data coverage

Firm-table columns (`company_analysis.parquet`):

| Column(s) | Used for | Coverage (green / other) | Confidence |
|---|---|---|---|
| `financed`, `any_vc`/`any_grant`/`any_debt`/`any_accelerator`/`any_growth_pe`/`any_crowdfunding`, `n_deals`, `n_deals_with_size` | access on the full population (T4.9); F4.4 curve | 100% / 100% | High |
| `age_years`, `cohort`, `green_signal_group` | cohort adjustment, R4 censoring, R1 split, F4.4 | 100% / 100% | High |
| `total_raised` | lifetime amount by cohort (T4.10) | 59% / 24% | Medium — compared only within the financed subsample; the gap is coverage, not a zero |
| `median_deal_size`, `last_deal_size` | secondary firm-level amount columns (T4.10) | 62% / 25% and 46% / 20% | Low-medium |
| `first_funding_lag` | years to first financing (T4.13) | 88% / 37% | Medium — strong for green, thinner for other |
| `first_vc_lag` | years to first VC (T4.13, F4.4) | 54% / 24% | Medium-low — the headline timing gap; report n |

Deal-table columns (`deals_clean`, 116,505 rows):

| Column(s) | Used for | Coverage | Confidence |
|---|---|---|---|
| `deal_date`, `stage_group`, `is_first_deal` | first-deal stage (T4.11, T4.14), stage composition (T4.15), progression (T4.17) | 100% | High |
| `deal_size`, `size_is_actual` | first size and median size by stage (T4.11, T4.16) | 59% (100% actuality flag) | Medium — `size_is_actual` marks estimated vs actual |
| `post_valuation` | post-money valuation (T4.12) | 25% | Low — lowest coverage in the chapter; n shown prominently, treated as indicative |

Confidence summary: **access and stage composition are high-confidence** (flags and
stage are fully populated); **amounts are medium** and only ever compared within the
financed subsample; **post-money valuation (T4.12) is the weakest table** at ~25%
coverage and is read with caution.

## Step 6 — Investors and grants

Answers the **by whom** half of the research question: which investor types back green
start-ups, whether public and private capital combine, whether grants precede venture
capital, and where the money comes from geographically. The master population is the
**INVESTED subsample** (firms with at least one recorded investor, ~50,815), the
investor-side analogue of Step 5's financed subsample: green firms are far better
documented, so a full-population composition comparison would measure coverage rather
than backing. Investor-type and origin questions are answered at the relation grain
(firm x investor), syndication at the deal grain, and grant -> VC sequencing uses deal
dates and is **descriptive only** (a grant preceding VC is an ordering, not causation).

Reads the Step 2 firm table (which already carries the company-level investor flags,
distinct-investor count, public/private indicators, and origin shares) plus four Step 1
clean tables: `deals_clean`, `company_investors_clean`, `investors_clean`, and
`deal_investors_clean`.

```bash
# build from the local Step 2 + Step 1 outputs
python -m empirical_analysis.step6_investors.run \
    --firm-table data/outputs/company_analysis.parquet \
    --clean-dir data/outputs/clean_tables \
    --output-dir data/outputs/chapter4

# on the target machine, the OneDrive paths resolve on their own
python -m empirical_analysis.step6_investors.run
```

Paths resolve automatically; override if needed:

- firm table: `--firm-table` > `STEP6_FIRM_TABLE` > OneDrive `09_...\company_analysis.parquet` > `data/outputs/company_analysis.parquet`
- clean tables: `--clean-dir` > `STEP2_CLEAN_DIR` > OneDrive `09_...\clean_tables` > `data/outputs/clean_tables` > `data/interim`
- output dir: `--output-dir` > `STEP6_OUTPUT_DIR` > OneDrive `09_...\chapter4_outputs` > `data/outputs/chapter4`

What to expect (CSV files in the output dir):

| File | Contents |
|---|---|
| `T4_18_investor_type_distribution.csv` | investor-type mix (relation share and firm-with-≥1 share), green vs other, using PitchBook's `investor_type_grp` |
| `T4_19_investor_flags.csv` | company-level any public / corporate / independent-VC / accelerator / lender flags, plus median distinct investors |
| `T4_21_public_private.csv` | lifetime combination vs same-deal co-investment of public and private capital, reported separately, plus their ratio |
| `T4_22_grant_to_vc.csv` | grant -> VC sequencing among firms with both; share where the grant preceded VC and the median months between (descriptive) |
| `T4_23_investor_origin.csv` | domestic / European cross-border / non-European origin shares, known-country relations only (coverage reported) |
| `T4_25_syndication.csv` | investors per round, multi-investor share, new investors, and lead presence, within stage group (deal grain) |
| `F4_05_investor_participation.csv` | figure data: share of firms with ≥1 investor of each type, green vs other |
| `captions_step6.csv` | fixed captions that must travel with the tables |

Every table ends with `n_green`, `n_others`, `n_startups` (relations on T4.18/T4.23,
rounds on T4.25, firms elsewhere; the grain is stated in each caption). The run prints
an acceptance report; a correct run shows the INVESTED subsample of 50,815, T4.19 flag
shares matching the firm-column means, a grant-and-VC population of 3,960, and origin
shares that sum to one within each group.

### Columns used and data coverage

Firm-table columns (`company_analysis.parquet`):

| Column(s) | Used for | Coverage (green / other) | Confidence |
|---|---|---|---|
| `n_investors_lifetime` | INVESTED base; median distinct investors (T4.19) | 100% / 100% | High |
| `any_public_investor`/`any_corporate_investor`/`any_ivc_investor`/`any_accelerator_investor`/`any_lender_investor` | company-level flags (T4.19) | 100% / 100% | High |
| `public_private_lifetime`, `public_private_same_deal` | lifetime vs same-deal capital (T4.21) | 100% / 100% | High |
| `hq_country`, `green_signal_group` | domestic classification for origin; R1 split | 100% / 100% | High |
| `any_grant`, `any_vc` | reconcile the grant-and-VC population (T4.22) | 100% / 100% | High |

Clean-table columns:

| Column(s) | Source | Used for | Coverage | Confidence |
|---|---|---|---|---|
| `investor_type_grp` | `investors_clean` | investor-type mix (T4.18, F4.5) | 100% | High |
| `company_id`↔`investor_id` links | `company_investors_clean` (194,790) | relation grain for T4.18, T4.23 | full | High |
| `investor_country` | `investors_clean` | origin: domestic / EU / non-European (T4.23) | 77% of investors (~93% of relations) | Medium — known-country only; coverage is printed on the table |
| `deal_date`, `stage_group` | `deals_clean` | grant vs VC dates (T4.22) | 100% | High |
| `n_investors`, `n_new_investors` | `deals_clean` | syndication medians (T4.25) | 85% / 79% | Medium-high |
| `is_lead` | `deal_investors_clean` (170,637) | lead presence per round (T4.25) | only 9% of links tagged "Yes" | Low — leads are sparsely tagged, so `pct_with_lead` is a floor, not a true lead rate |

Confidence summary: the **investor-type distribution, company flags and public/private
tables are high-confidence** (types and flags are fully populated); **syndication
counts are medium** and the **lead-presence share is low** because leads are rarely
tagged; **investor origin is medium** and restricted to known-country relations, with
coverage reported on every row.

## Step 7 — Geography x finance

Crosses geography with finance to answer three questions the earlier steps deferred:
**does green punch above its weight in capital** (T4.26: each country's green share of
firms vs its green share of capital), **where does the money come from country by
country** (T4.28: domestic / European cross-border / non-European investor origin per
country), and **what kind of financing does each country raise** (T4.29: green vs other
disclosed deal capital by country x stage). It also emits **block B**: a collapsed
by-country comparison of every Step 5 and Step 6 table — one row per country with that
table's headline statistic green vs other, the secondary dimension (cohort/stage/
measure) collapsed. Block B redefines nothing: it reuses the Step 5/6 builders on
per-country slices, so a by-country value equals the Europe-wide builder run on that
country. Descriptive only, and a 2026 snapshot of recorded capital, not an
investment-flow series.

There is **no country floor** (per request, consistent with the amended Step 4): every
country with a start-up is reported and thin cells carry `low_n_flag` (fewer than 30
green firms / relations / deals, per the table's grain).

Reads the Step 2 firm table plus four Step 1 clean tables (`deals_clean`,
`company_investors_clean`, `investors_clean`, `deal_investors_clean`). Full spec:
[`specs/step7_geo_finance/design.md`](specs/step7_geo_finance/design.md).

```bash
# build from the local Step 2 + Step 1 outputs
python -m empirical_analysis.step7_geo_finance.run \
    --firm-table data/outputs/company_analysis.parquet \
    --clean-dir data/outputs/clean_tables \
    --output-dir data/outputs/chapter4

# on the target machine, the OneDrive paths resolve on their own
python -m empirical_analysis.step7_geo_finance.run
```

Paths resolve automatically; override if needed:

- firm table: `--firm-table` > `STEP7_FIRM_TABLE` > OneDrive `09_...\company_analysis.parquet` > `data/outputs/company_analysis.parquet`
- clean tables: `--clean-dir` > `STEP2_CLEAN_DIR` > OneDrive `09_...\clean_tables` > `data/outputs/clean_tables` > `data/interim`
- output dir: `--output-dir` > `STEP7_OUTPUT_DIR` > OneDrive `09_...\chapter4_outputs` > `data/outputs/chapter4`

What to expect (CSV files in the output dir):

| File | Contents |
|---|---|
| `T4_26_green_share_firms_vs_capital.csv` | per country: green share of firms vs green share of capital (both `total_raised` and disclosed `deal_size`, coverage shown), and the ratio |
| `T4_10_cumulative_total_raised_by_country.csv` | per country: summed lifetime `total_raised` (USD m) for green, other, and total — recorded amounts only, not median or share |
| `T4_28_investor_origin_by_country.csv` | per country: domestic / EU cross-border / non-European investor relation shares, green vs other (known-country only, coverage shown) |
| `T4_29_country_funding_by_type.csv` | per country x stage: green / other / total disclosed deal capital and green amount share |
| `F4_26_green_share_scatter.csv` | figure data: green firm share (x) vs green funding share (y) with the y = x reference |
| `<table>_by_country.csv` (15 files) | block B: one row per country, headline statistic green vs other, for every Step 5/6 table (F4.4 excluded — multi-horizon curve stays in Step 5) |
| `captions_step7.csv` | fixed captions that must travel with the tables |

Every table ends with `n_green`, `n_others`, `n_startups` (the grain — firms, financed
firms, INVESTED firms, relations or deals — is stated in each caption). The run prints
an acceptance report; a correct run shows all 46 countries in T4.26 (20 at the former
≥500 floor), origin shares summing to one within each group per country, and green
capital-concentrated (ratio > 1) in the UK, Italy and the Netherlands among others.

### Columns used and data coverage

| Column(s) | Source | Used for | Coverage | Confidence |
|---|---|---|---|---|
| `hq_country`, `green` | `company_analysis` | per-country population and green firm share (T4.26) | 100% | High |
| `total_raised` | `company_analysis` | green funding share (T4.26) | 27% overall, 5-45% per country | Medium — recorded amounts only; `coverage_total_raised` is on every row |
| `deal_size` | `deals_clean` | funding share cross-check (T4.26), country x stage capital (T4.29) | ~59% of deals | Medium — recorded amounts only; `coverage_dealsize` reported |
| `investor_country` (× relations) | `investors_clean` / `company_investors_clean` | investor origin by country (T4.28) | ~77% of investors | Medium — known-country only; coverage per country on the row |
| Step 5/6 columns | as in Steps 5/6 | block B headline metrics | as in Steps 5/6 | inherits the source table's tier |

Because the country floor is off, small countries appear with `low_n_flag = 1` and are
read as indicative; the two capital measures in T4.26 answer the funding-share question
two ways, and both carry their coverage so a low share is not confused with a low count.

## Step 8 — Verification

Verification is distinct from robustness. Robustness (R1-R4) asks whether a finding
survives a different sample; **verification asks whether the reported number is
correct**. Step 8 reconciles counts and shares across every Chapter 4 table so no two
tables contradict each other and no headline rests on an unflagged tiny cell. It adds
no new analytical numbers.

It is **self-contained**: it re-runs Steps 3-7 in-memory (each step's `build_all`, plus
Step 7's by-country block) to get a canonical set of tables, then runs structural checks
over them — so verification always has a source of truth even on a clean checkout. For
each output CSV that exists in the output dir it also compares the on-disk file to the
re-run and flags divergence as `STALE` (a warning: the file predates the current code or
data, not a contradiction in the numbers). Full spec:
[`specs/step8_verify/design.md`](specs/step8_verify/design.md).

```bash
# re-runs Steps 3-7 and reconciles
python -m empirical_analysis.step8_verify.run \
    --firm-table data/outputs/company_analysis.parquet \
    --clean-dir data/outputs/clean_tables \
    --output-dir data/outputs/chapter4

# fail the process if any check FAILs (for CI)
python -m empirical_analysis.step8_verify.run --strict
```

Checks (each is one reconciliation row, `status` PASS / WARN / FAIL):

| Category | What it asserts |
|---|---|
| population | firm rows 116,005; green 8,306; other 107,699; green stages 6,636/834/836; financed 47,714; INVESTED 50,815; grant-and-VC 3,960 |
| trio_identity | `n_green + n_others == n_startups` on every table carrying the trio |
| shares_sum | T4.14/T4.15 stage shares, T4.18/T4.23 relation shares, T4.28 per-country origin shares sum to 1; T4.29 `green_amount + other_amount == total_amount` and share in [0,1] |
| median_in_iqr | `q25 <= median <= q75` on T4.10/T4.11/T4.13 |
| low_n_flag | `(n_green < 30) == (low_n_flag == 1)` on every flagged table; headline/country tables carry the column |
| source_totals | T4.15 == deals rows (116,505); T4.18 == links on INVESTED firms; T4.29 <= disclosed `deal_size`; T4.6 == population/green; T4.26 firm share recomputes |
| double_counting | relations exceed firms (grain kept); INVESTED base is firm-grain, not relation-grain |
| stale_files | each present output CSV matches the re-run within tolerance, else `STALE` |

Output is `step8_reconciliation.csv` (one row per check: `check_id`, `category`,
`description`, `expected`, `observed`, `status`, `detail`). The run prints a
PASS/WARN/FAIL summary and every non-PASS line; `--strict` exits non-zero on any `FAIL`.
Deferred (see spec §8): the end-to-end trace of ~10 firms (5.3) and the Stage 2+3 re-run
of headline results (5.6, already carried by the R1 columns on the Step 3-7 tables).

## Acceptance anchors

A correct full run reproduces:

- population 116,005; green 8,306; green stages 6,636 / 834 / 836
- financed firms 47,714 (firms with at least one qualifying deal)
- INVESTED firms 50,815 (firms with at least one recorded investor); grant-and-VC firms 3,960
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
