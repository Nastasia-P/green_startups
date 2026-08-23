# Step 2 — Build the firm-level table

Self-contained specification. Everything needed to understand, run, or rebuild this
step is in this document; no other file needs to be open.

**Implemented by:** `empirical_analysis/step2_firm_table/`
**Run with:** `python -m empirical_analysis.step2_firm_table.run --clean-dir <step1 output>`

---

## 1. Purpose

Step 1 produced eight clean relational tables, each at its own grain (one row per
deal, per deal x investor, and so on). None of them is a firm. Every Chapter 4
analysis — firm characteristics, geography, funding, investors — needs **one row
per firm** carrying that firm's attributes and a summary of its financing history.

Step 2 builds exactly that table: `company_analysis.parquet`, 116,005 rows, one per
firm. It joins the company spine scalars (founding year, employees, HQ location,
industry, TotalRaised) onto the population and collapses the four financing tables
(`deals_clean`, `deal_investors_clean`, `company_investors_clean`, `investors_clean`)
down to firm level.

This is the single keystone between the cleaned data and the analysis steps. Steps 3
through 6 read `company_analysis.parquet` and nothing else from the pipeline.

**Step 2 does no analysis and produces no thesis table.** It computes per-firm
variables only. Grouping, cohort comparisons, medians and figures are Steps 3-6.

---

## 2. Inputs

### 2.1 The Step 1 clean tables

The eight Parquet files written by Step 1. Step 2 uses five of them:

| File | Grain | Used for |
|---|---|---|
| `population_key.parquet` | 1 per firm | the row spine and green flags |
| `deals_clean.parquet` | 1 per deal | all deal aggregates and timing |
| `deal_investors_clean.parquet` | 1 per deal x investor | same-deal co-investment |
| `company_investors_clean.parquet` | 1 per firm x investor | lifetime investor flags |
| `investors_clean.parquet` | 1 per investor | investor type group and country |

The directory is found in this order (first match wins); `--clean-dir` overrides all:

1. environment variable `STEP2_CLEAN_DIR`
2. the target machine's OneDrive `...\09_Python_Empirical Analysis\clean_tables`
3. `<repo>/data/outputs/clean_tables`
4. `<repo>/data/interim`

### 2.2 The company spine

`startups_stages_filtered.csv` (94 columns, 116,005 rows) supplies the firm scalars
that never entered the relational tables. Step 2 reads only the columns it needs.
Override with `--spine`.

The green ledger is **not** re-read: green flags come from `population_key`, so
Step 1 and Step 2 can never disagree on who is green.

---

## 3. Output columns

One Parquet file, `company_analysis.parquet`, one row per firm. Columns below, with
their source and the spec variable number (V1.x from the master specification).

### 3.1 Identity and green flags (from `population_key`)

| Column | V | Meaning |
|---|---|---|
| `company_id` | 1.1 | firm key |
| `green` | 1.2 | 1 if identified green, else 0 |
| `green_stage` | 1.3 | vertical / token / phrase / none |
| `green_signal_group` | 1.4 | Stage 1 / Stage 2+3 / none |

### 3.2 Firm scalars (from the spine)

| Column | V | Source column | Meaning |
|---|---|---|---|
| `year_founded` | 1.5 | `YearFounded` | founding year (2016-2026, always present) |
| `age_years` | 1.6 | derived | `2026 - year_founded` |
| `cohort` | 1.7 | derived | 2016-2018 / 2019-2021 / 2022-2024 / 2025-2026 |
| `hq_country` | 1.8 | `HQCountry` | 100% populated |
| `hq_city` | 1.9 | `HQCity` | 99.3% |
| `employees` | 1.10 | `Employees` | numeric; 52% populated |
| `employee_band` | 1.11 | derived | 1-10 / 11-50 / 51-200 / 200+ |
| `business_status` | 1.12 | `BusinessStatus` | raw; grouping is deferred to Step 3 |
| `primary_sector` | 1.14 | `PrimaryIndustrySector` | |
| `primary_industry_group` | added | `PrimaryIndustryGroup` | requested addition |
| `primary_industry_code` | added | `PrimaryIndustryCode` | requested addition |
| `total_raised` | 1.17 | `TotalRaised` | USD m; 27% populated. **Amount only, never access** |

### 3.3 Deal aggregates (from `deals_clean`)

| Column | V | Meaning |
|---|---|---|
| `n_deals` | 1.18 | count of qualifying deals |
| `n_rounds_vc` | 1.19 | count where `stage_group` is a VC stage |
| `financed` | 1.20 | 1 if `n_deals >= 1`. **Access measure. Never `total_raised > 0`** |
| `any_vc` | 1.21 | 1 if any VC-stage deal |
| `any_grant` | 1.22 | 1 if any `stage_group == 'Grant'` |
| `any_debt` | 1.23 | 1 if any `deal_class == 'Debt'` or `stage_group == 'Debt'` |
| `any_accelerator` | 1.24 | 1 if any `stage_group == 'Accelerator/Incubator'` |
| `any_growth_pe` | 1.25 | 1 if any `stage_group == 'Growth/PE'` |
| `any_crowdfunding` | 1.26 | 1 if any `stage_group == 'Crowdfunding'` |
| `first_deal_date` | 1.27 | earliest qualifying deal date |
| `first_deal_type` | 1.28 | `deal_type` at the first deal |
| `first_deal_size` | 1.29 | `deal_size` at the first deal (may be null) |
| `last_deal_date` | added | latest qualifying deal date |
| `last_deal_type` | added | `deal_type` at the last deal |
| `last_deal_size` | added | `deal_size` at the last deal |
| `median_deal_size` | added | firm's typical round size (median over deals with a size) |
| `total_deal_size_obs` | 1.41 | sum of `deal_size` over deals that have one |
| `n_deals_with_size` | added | how many deals carried a size (context for the two totals above) |
| `first_vc_date` | 1.30 | earliest VC-stage deal date |
| `first_funding_lag` | 1.31 | `year(first_deal_date) - year_founded`. **Negative -> NA** |
| `first_vc_lag` | 1.32 | `year(first_vc_date) - year_founded`. **Negative -> NA** |

The **VC stage set** is `{Angel/Seed, Early-stage VC, Later-stage VC}`, matching spec
V1.19/V1.21. It is a configurable constant; if the literature comparison for "first
VC" should exclude seed, drop `Angel/Seed` from `VC_STAGE_GROUPS` in `config.py`.

### 3.4 Investor aggregates (from `company_investors_clean` x `investors_clean`)

| Column | V | Meaning |
|---|---|---|
| `n_investors_lifetime` | 1.33 | distinct lifetime investors |
| `any_public_investor` | 1.34 | any `investor_type_grp == 'Public/Government'` |
| `any_corporate_investor` | 1.35 | any `== 'Corporate'` |
| `any_ivc_investor` | 1.36 | any `== 'Independent VC'` |
| `any_accelerator_investor` | 1.37 | any `== 'Accelerator/Incubator'` |
| `any_lender_investor` | 1.37b | any `== 'Lender/Debt'` |
| `share_investors_domestic` | 1.40 | share of located investors in the firm's own country |
| `share_investors_eu_cross_border` | 1.40 | share European but not domestic |
| `share_investors_non_european` | 1.40 | share outside Europe |

Investor-origin shares use only investors whose country is known; a firm with no
located investor gets NA on all three. The European country set lives in `config.py`
and should be validated against `investor_types_seen` country values before the Step 6
investor-origin table is finalised.

### 3.5 Public and private capital

| Column | V | Meaning |
|---|---|---|
| `public_private_lifetime` | 1.38 | 1 if `any_public_investor` AND (`any_corporate_investor` OR `any_ivc_investor`). **Lifetime combination** |
| `public_private_same_deal` | 1.39 | 1 if at least one `deal_id` carried both a public and a private investor. **True co-investment: the stronger measure** |

"Private" for both measures is `{Independent VC, Corporate}`, matching V1.38, and is a
configurable set (`PRIVATE_INVESTOR_GRPS`).

---

## 4. Rules that apply throughout

- **Missing is "unknown", never "zero".** A firm with no deal record has *unobserved*
  funding, not zero. `total_raised`, `employees` and the deal-size columns stay null
  when the source is blank. Only the count-based flags (`financed`, `any_*`) are 0
  when there is genuinely no qualifying record, because absence of a record *is* the
  measurement (rule N2).
- **`financed` is defined by a surviving deal record, never by `total_raised > 0`**
  (rule N2). A firm can be financed with a null `total_raised`, and can have a
  non-null `total_raised` with no qualifying deal.
- **Negative funding lags are flagged and excluded.** A first deal dated before the
  founding year is a data error; the lag is set to NA and counted in the audit
  (V1.31).
- **Nothing is merged before it is aggregated.** Each financing table is reduced to
  one row per firm *first*, then joined onto the spine. A deal with six investors is
  never allowed to multiply a firm's row (spec Part II.A3).

---

## 5. Outputs

Written to (first match wins); `--output-dir` overrides all:

1. environment variable `STEP2_OUTPUT_DIR`
2. the target machine's OneDrive `...\09_Python_Empirical Analysis`
3. `<repo>/data/outputs`

| File | Contents |
|---|---|
| `company_analysis.parquet` | the firm-level table, 116,005 rows |
| `step2_coverage.csv` | per-column non-null share, split green vs other, so the T4.0 coverage asymmetry stays visible |
| `step2_audit.csv` | row count, financed count, negative-lag count, and each join's match rate |

---

## 6. Acceptance checks

The run prints these at the end. Step 2 is done when they pass.

- [ ] `company_analysis` has exactly **116,005** rows, one per firm, `company_id` unique
- [ ] `green` sums to the population_key green total (8,306 on the target ledger)
- [ ] `financed` sums to **47,714**, matching the distinct financed firms in the Step 1 audit
- [ ] every firm has a `cohort` (founding years are a clean 2016-2026)
- [ ] no negative funding lag survives into `first_funding_lag` / `first_vc_lag`
- [ ] `total_deal_size_obs` is reported alongside `n_deals_with_size`, never as a lone total
- [ ] the coverage report shows the expected asymmetry (green firms far better documented)

---

## 7. Decisions taken, with defaults

| Decision | Default | Where to change |
|---|---|---|
| VC stage set for `any_vc` / `n_rounds_vc` / `first_vc_date` | `{Angel/Seed, Early-stage VC, Later-stage VC}` (spec V1.19) | `VC_STAGE_GROUPS` in `config.py` |
| "Private" set for the public/private measures | `{Independent VC, Corporate}` (spec V1.38) | `PRIVATE_INVESTOR_GRPS` in `config.py` |
| Reference year for age and lag | 2026 (extract year) | `REFERENCE_YEAR` in `config.py` |
| Cohort bin edges | 2016-2018 / 2019-2021 / 2022-2024 / 2025-2026 | `COHORT_BINS` in `config.py` |
| Which countries count as European for investor origin | EU27 + EEA + UK + CH + neighbours | `EUROPEAN_COUNTRIES` in `config.py` |

---

## 8. Out of scope

- Any grouping, median, cohort table or figure — Steps 3-6.
- Debt lender-type breakdown from `DealDebtLenderRelation.csv` — requires a Step 1
  amendment to read that raw table; noted in the roadmap.
- Re-deriving the population, the green flags, or the deal/investor taxonomies —
  fixed by Chapter 3 and Step 1.

---

## 9. How to run it

```bash
# smoke test on the fixture-built clean tables (no target machine needed)
python -m empirical_analysis.step2_firm_table.run --clean-dir data/interim

# the real run, pointing at the Step 1 outputs
python -m empirical_analysis.step2_firm_table.run \
    --clean-dir "data/outputs/clean_tables"

# explicit paths if the defaults do not resolve
python -m empirical_analysis.step2_firm_table.run \
    --clean-dir "D:\path\to\clean_tables" \
    --spine     "D:\path\to\startups_stages_filtered.csv" \
    --output-dir "D:\path\to\09_Python_Empirical Analysis"
```

Tests: `python -m pytest empirical_analysis/step2_firm_table/tests/ -q`
