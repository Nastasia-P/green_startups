# Pipeline roadmap — from clean data to Chapter 4 exhibits

This is the durable plan for aligning the pipeline with the Chapter 4 analysis. It
records the seven steps, which thesis outputs each produces, the additions to the
output register, and the open decisions. Each step is a self-contained module with
its own spec under `empirical_analysis/specs/<step>/design.md`.

The author's nine analysis areas (firm characteristics; employees; industry;
geography; funding access and amounts; deal stage taxonomy; first-financing timing;
grants; public/private capital and debt) map onto the existing T4.x output register.
This roadmap is the crosswalk.

## Step overview

```
Step 1  Clean raw data          DONE   -> 8 clean relational tables
Step 2  Firm-level table        DONE   -> company_analysis.parquet (1 row per firm)
Step 3  Firm characteristics    TODO   -> areas 1, 2, 3
Step 4  Geography               TODO   -> area 4
Step 5  Funding                 TODO   -> areas 5, 6, 7
Step 6  Investors and grants    TODO   -> areas 8, 9
Step 7  Verification            TODO   -> cross-table reconciliation
```

Steps 3-6 are independent of each other; all four read only `company_analysis.parquet`
(Step 4 also needs the country/city denominators, Steps 5-6 also read the deal and
investor clean tables for deal-level and deal x investor cuts).

## Step 2 — Firm-level table (built)

Module `empirical_analysis/step2_firm_table/`, spec
`empirical_analysis/specs/step2_firm_table/design.md`.

Produces `company_analysis.parquet`: one row per firm (116,005), carrying spec
variables V1.1-V1.41 plus the requested additions (last deal size, firm-level typical
deal size, `n_deals_with_size`). Verified: 116,005 rows, green 8,306, financed 47,714,
coverage asymmetry reproduced (employees 82% green vs 50% other; total_raised 59% vs
24%). This is the input for every step below.

## Step 3 — Firm characteristics (areas 1-3)

Module `step3_firm_characteristics`. Reads `company_analysis`, plus
`industries_clean`, `verticals_clean`, `employee_history_clean` where a relational cut
is needed.

| Output | Register | Content |
|---|---|---|
| `T4_01_master_descriptive.csv` | T4.1 | n, founding year/age, employees, business status, primary industry, financing status, green vs other |
| `T4_02_business_status.csv` | T4.2 | business status distribution (inspect frequencies first, decision D2) |
| `T4_03_industry_composition.csv` | T4.3 | industry composition from `industries_clean`, long format |
| `T4_04_green_subsegments.csv` | T4.4 | green subsegment decomposition from `verticals_clean` |
| `T4_05_employment_by_cohort.csv` | T4.5 | median employees by cohort, green vs other |
| `F4_01_green_share_by_cohort.pdf` | F4.1 | green share per founding cohort. Label "cohort composition", not a time trend |

## Step 4 — Geography (area 4)

Module `step4_geography`. Reads `company_analysis`. Country denominators use the
116,005 population (rule N9), minimum 500 firms per country and 100 per city
(decision D4).

| Output | Register | Content |
|---|---|---|
| `F4_02_green_count_by_country.pdf` | F4.2 | N green by country |
| `T4_06_country_specialisation.csv` | T4.6 | share of European green, green intensity, location quotient |
| `F4_03_lq_by_country.pdf` | F4.3 | location quotient ranked/choropleth |
| `T4_07_per_capita_crosscheck.csv` | T4.7 | startups per capita (needs external Eurostat populations) |
| `T4_08_concentration.csv` | T4.8 | top-5 country share, green vs other |
| `AP2_city_ranking.csv` | AP2 | city count, share, intensity (>=100 firms) |

## Step 5 — Funding (areas 5, 6, 7)

Module `step5_funding`. Reads `company_analysis` and `deals_clean` (for deal-level
cuts). Every lifetime measure is reported within cohort (rule N4); amount comparisons
run on the financed subsample (rule N1); medians primary (rule N6).

| Output | Register | Content |
|---|---|---|
| `T4_09_funding_access.csv` | T4.9 | access flags: any financing/VC/grant/debt/accelerator/growth-PE/crowdfunding |
| `T4_10_total_raised_by_cohort.csv` | T4.10 | total_raised n/median/Q25/Q75/mean/P90 by cohort |
| `T4_11_first_financing_size_by_stage.csv` | T4.11 | first financing size by stage_group |
| `T4_13_time_to_financing.csv` | T4.13 | first_funding_lag and first_vc_lag, median and distribution |
| `T4_14_first_financing_type.csv` | T4.14 | first financing type composition |
| `T4_15_stage_composition.csv` | T4.15 | share of deals at each stage_group |
| `T4_16_median_deal_size_by_stage.csv` | T4.16 | median deal size by stage_group (incl. a Grant row: see additions) |
| `T4_17_financing_trajectories.csv` | T4.17 | rounds per firm, inter-round intervals (censored, R4) |
| `F4_04_cumulative_financed.pdf` | F4.4 | cumulative share financed by years since founding |

## Step 6 — Investors and grants (areas 8, 9)

Module `step6_investors`. Reads `company_analysis`, `deal_investors_clean`,
`investors_clean`.

| Output | Register | Content |
|---|---|---|
| `T4_18_investor_type_distribution.csv` | T4.18 | investor_type_grp distribution, green vs other |
| `T4_19_investor_flags.csv` | T4.19 | company-level any public/corporate/IVC/accelerator/lender, median distinct investors |
| `T4_21_public_private.csv` | T4.21 | lifetime combination vs same-deal co-investment, reported separately |
| `T4_22_grant_to_vc.csv` | T4.22 | grant->VC sequencing; share with prior grant among VC-backed. Descriptive, not causal |
| `T4_23_investor_origin.csv` | T4.23 | domestic / EU cross-border / non-European shares |
| `T4_25_syndication.csv` | T4.25 | investors per round, multi-investor share, within stage_group |
| `F4_05_investor_participation.pdf` | F4.5 | investor-type participation, green vs other |

## Step 7 — Verification

Module `step7_verify`. Reconciles firm counts across every output (population totals,
financed subsample, green totals by stage) so no two tables contradict each other.
Produces `step7_reconciliation.csv`. No new analytical numbers (spec Phase 5).

## Additions to the output register

Six statistics the author asked for that the current spec does not yet produce. Step 2
already carries the firm-level columns needed for all of them; the additions are in
the reporting steps.

| Addition | Where | Note |
|---|---|---|
| Mean age and full age distribution | Step 3 (T4.1 + a distribution figure) | means become a secondary column; medians stay primary (rule N6) |
| Employee IQR and size bands within cohorts | Step 3 (extend T4.1 / T4.5) | bands 1-10 / 11-50 / 51-200 / 200+ crossed with cohort |
| `primary_industry_group`, `primary_industry_code` | Step 3 (extend T4.3) | already in `company_analysis` |
| Last financing size, firm-level typical deal size | Step 5 | `last_deal_size`, `median_deal_size` already in `company_analysis` |
| Dedicated median grant amount | Step 5 (T4.16 Grant row + a standalone line) | grant deal sizes from `deals_clean` where stage_group == Grant |
| Debt lender-type breakdown | Step 6, **needs a Step 1 amendment** | requires reading `DealDebtLenderRelation.csv` (see open items) |

## Open items to resolve before Steps 5-6

1. **Green count reconciliation.** The local ledger yields 8,698 green firms; the
   committed `population_key` and the thesis anchor are 8,306. Results must be produced
   from the 8,306 population. Confirm which ledger is final before publishing.
2. **Debt lender types.** `DealDebtLenderRelation.csv` is one of the 36 raw tables Step
   1 does not read. Area 9's lender-type breakdown needs it added as a ninth clean
   table in Step 1 (`USECOLS`, `FILTER_COL`, a `build_relation_clean` call).
3. **Eurostat populations.** T4.7 (per-capita cross-check) needs external country
   population data, not in the PitchBook extract.

## Rules and decisions that constrain every step

Rules N1-N10 and decisions D1-D7 live in `HANDOVER.md`. The load-bearing ones here:
N1 (amounts on the financed subsample only), N2 (financed by deal record, not
`total_raised > 0`), N4 (lifetime measures within cohort), N6 (medians primary), N9
(country denominators use the 116,005 population), N10 (label "Other European
start-ups", never "non-green").
