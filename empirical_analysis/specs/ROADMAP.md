# Pipeline roadmap — from clean data to Chapter 4 exhibits

This is the durable plan for aligning the pipeline with the Chapter 4 analysis. It
records the eight steps, which thesis outputs each produces, the additions to the
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
Step 3  Firm characteristics    DONE   -> areas 1, 2, 3
Step 4  Geography               DONE   -> area 4
Step 5  Funding                 DONE   -> areas 5, 6, 7
Step 6  Investors and grants    DONE   -> areas 8, 9
Step 7  Geography x finance      DONE   -> T4.26/T4.28/T4.29 + by-country cross
Step 8  Verification            DONE   -> cross-table reconciliation (step8_reconciliation.csv)
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

Spec written: `empirical_analysis/specs/step3_firm_characteristics/design.md`.
Implemented: module `empirical_analysis/step3_firm_characteristics/` (run with
`python -m empirical_analysis.step3_firm_characteristics.run`). Verified on the full
firm table: 8,306 green / 107,699 other, cohort green-share and coverage anchors reproduced.

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

Spec written: `empirical_analysis/specs/step4_geography/design.md`. Implemented: module
`empirical_analysis/step4_geography/` (run with
`python -m empirical_analysis.step4_geography.run`). Reads `company_analysis` plus a
committed World Bank population file (`data/sources/worldbank_population.csv`, refreshed
with `python -m empirical_analysis.step4_geography.fetch_worldbank`). Country
denominators use the 116,005 population (rule N9); the location-quotient reference is
fixed at the EU level. **The country floor from decision D4 was dropped (per request):**
`MIN_COUNTRY_N` is set to 1 so every country with a start-up gets a row and thin cells
carry `low_n_flag` (green < 30); the former 500 gate is printed only as a sensitivity
count. Cities keep the 100 floor (`MIN_CITY_N`). Verified on the full firm table: all
46 countries reported (20 at the former >=500 floor, 21 low-n flagged); T4.7 uses World
Bank `SP.POP.TOTL` (single latest vintage, all 46 countries matched, no NA), with
Spearman(startups per million, green intensity) ~ -0.53 on the 20 large countries and
~ -0.14 across all 46.

| Output | Register | Content |
|---|---|---|
| `F4_02_green_count_by_country.csv` | F4.2 | N green by country (figure data; PDF is a later cosmetic step) |
| `T4_06_country_specialisation.csv` | T4.6 | share of European green, green intensity, location quotient (+ Stage 1 / Stage 2+3 variants, R1) |
| `F4_03_lq_by_country.csv` | F4.3 | location quotient ranked, with the LQ=1 reference (figure data) |
| `T4_07_per_capita_crosscheck.csv` | T4.7 | startups/green per capita from World Bank `SP.POP.TOTL`; all 46 countries matched |
| `T4_08_concentration.csv` | T4.8 | top-5/top-10 country and top-5 city shares, green vs other (own denominators) |
| `AP2_city_ranking.csv` | AP2 | city count, share, intensity, modal country (>=100 firms) |

## Step 5 — Funding (areas 5, 6, 7)

Spec written: `empirical_analysis/specs/step5_funding/design.md`. Implemented: module
`empirical_analysis/step5_funding/` (run with
`python -m empirical_analysis.step5_funding.run`). Reads `company_analysis` and
`deals_clean` (for deal-level cuts). Access is measured on the full population (rule
N2); amounts, sizes, valuations, lags and trajectories run on the financed subsample
(rule N1); every lifetime measure is within cohort (rule N4); horizon and follow-on
measures are censored (rule R4); medians primary (rule N6). Verified on the full firm
table: financed subsample 47,714, T4.15 deals = 116,505, green reaches first financing
about as fast as others (median 1 year) but first VC more slowly (2 vs 1).

| Output | Register | Content |
|---|---|---|
| `T4_09_funding_access.csv` | T4.9 | access flags: any financing/VC/grant/debt/accelerator/growth-PE/crowdfunding (+ R1 stage split) |
| `T4_10_total_raised_by_cohort.csv` | T4.10 | total_raised (+ last/typical deal size) n/median/Q25/Q75/mean/P90 by cohort |
| `T4_11_first_financing_size_by_stage.csv` | T4.11 | first financing size by stage_group, with the Actual share |
| `T4_12_post_valuation.csv` | T4.12 | post-money valuation, green vs other; low coverage, n reported prominently |
| `T4_13_time_to_financing.csv` | T4.13 | first_funding_lag and first_vc_lag, overall and by cohort |
| `T4_14_first_financing_type.csv` | T4.14 | first financing type composition |
| `T4_15_stage_composition.csv` | T4.15 | share of deals at each stage_group (deal grain) |
| `T4_16_median_deal_size_by_stage.csv` | T4.16 | median deal size by stage_group (incl. a Grant row) |
| `T4_17_financing_trajectories.csv` | T4.17 | rounds per firm, inter-round intervals, stage progression (censored, R4) |
| `F4_04_cumulative_financed.csv` | F4.4 | cumulative share financed (and VC-backed) by years since founding (figure data; PDF is a later cosmetic step) |

R3 (repeat headline funding within industry) is deferred; `primary_sector` is present
in `company_analysis` so it can be added later without new inputs.

## Step 6 — Investors and grants (areas 8, 9) — DONE

Module `step6_investors`. Reads `company_analysis` plus four Step 1 clean tables:
`deals_clean` (grant/VC dates, stage-group round counts), `company_investors_clean`
and `investors_clean` (relation grain for type and origin), and
`deal_investors_clean` (lead flag per round). Master population is the INVESTED
subsample (`n_investors_lifetime >= 1`), the investor-side analogue of Step 5's
financed subsample. Spec: `specs/step6_investors/design.md`.

| Output | Register | Content |
|---|---|---|
| `T4_18_investor_type_distribution.csv` | T4.18 | investor_type_grp distribution (relation share + firm-with-≥1), green vs other, R1 split |
| `T4_19_investor_flags.csv` | T4.19 | company-level any public/corporate/IVC/accelerator/lender, median distinct investors |
| `T4_21_public_private.csv` | T4.21 | lifetime combination vs same-deal co-investment, reported separately, plus ratio |
| `T4_22_grant_to_vc.csv` | T4.22 | grant->VC sequencing; share with prior grant among VC-backed. Descriptive, not causal |
| `T4_23_investor_origin.csv` | T4.23 | domestic / EU cross-border / non-European shares (known-country only) |
| `T4_25_syndication.csv` | T4.25 | investors per round, multi-investor share, lead presence, within stage_group |
| `F4_05_investor_participation.csv` | F4.5 | figure data: investor-type participation (firm-with-≥1), green vs other |

Verified on the local build: INVESTED subsample 50,815 (green 7,585 / other 43,230);
T4.19 flag shares reconcile with firm-column means; T4.18 investor relations 194,531,
Other/Unclassified relation share 2.6% (well under 10%); grant-and-VC population 3,960;
T4.23 origin shares sum to 1 within group at 92.9% country coverage. Headline findings:
green firms lean more on accelerators (+11.8 pp firms), public/government (+9.3 pp) and
impact investors (+8.9 pp), combine public and private capital more often (15.7% vs
8.8% lifetime), and are more domestic / European and less non-European (-5.8 pp on the
non-European relation share) — coherent with the Draghi framing.

**Deferred (same posture as Step 5's R3, no new inputs blocked):** T4.20 (investor
composition by green subsegment), T4.24 (non-European participation by stage), and F4.6
main-text figure selection (decision D7). T4.26 (green share of firms vs green share of
capital by country — the geography x finance bridge, decision D6) is now **built in
Step 7** and no longer deferred. The debt lender-type breakdown remains blocked on a
Step 1 amendment to read `DealDebtLenderRelation.csv` (see open items).

## Step 7 — Geography x finance — DONE

Module `step7_geo_finance`, spec `specs/step7_geo_finance/design.md` (run with
`python -m empirical_analysis.step7_geo_finance.run`). Crosses geography with finance.
Reads `company_analysis` plus four Step 1 clean tables (`deals_clean`,
`company_investors_clean`, `investors_clean`, `deal_investors_clean`). **No country
floor** (consistent with the amended Step 4): every country with a start-up is
reported and thin cells carry `low_n_flag`.

Block A — three purpose-built country-grain outputs:

| Output | Register | Content |
|---|---|---|
| `T4_26_green_share_firms_vs_capital.csv` | T4.26 | per country: green firm share vs green funding share (both `total_raised` and disclosed `deal_size`, coverage shown) and the ratio |
| `T4_10_cumulative_total_raised_by_country.csv` | T4.10 (addition) | per country: summed lifetime `total_raised` green / other / total (USD m, recorded amounts only) |
| `T4_28_investor_origin_by_country.csv` | T4.28 (new) | per country: domestic / EU cross-border / non-European investor relation shares, green vs other (known-country only) |
| `T4_29_country_funding_by_type.csv` | T4.29 (new) | per country x stage: green / other / total disclosed deal capital, green amount share |
| `F4_26_green_share_scatter.csv` | F-data | figure data for the T4.26 scatter (green firm share vs green funding share, y = x reference) |

Block B — a collapsed by-country comparison of every Step 5 and Step 6 table: for each
(T4.9-T4.17, T4.18/19/21/22/23/25) a `<table>_by_country.csv` with one row per
country carrying that table's headline statistic green vs other, the secondary
dimension (cohort/stage/measure) collapsed. Block B reuses the Step 5/6 builders on
per-country slices, so a by-country value equals the Europe-wide builder run on that
country; Steps 5/6 are unchanged.

**Both capital measures** are reported per user decision: `total_raised` (firm-level,
27% overall / 5-45% per-country coverage) and summed disclosed `deal_size` (~59%), each
with its coverage on the row, so a low funding share is never confused with low
coverage. Verified on the local build: 46 countries in T4.26 (20 at the former >=500
floor, 21 low-n flagged); origin shares sum to 1 within each group per country; green is
capital-concentrated (ratio_tr > 1) in the UK (0.087 firms -> 0.132 capital), Italy and
the Netherlands, among others.

## Step 8 — Verification (DONE)

Module `step8_verify`. Reconciles counts and shares across every Chapter 4 output so no
two tables contradict each other and no headline rests on an unflagged tiny cell. No new
analytical numbers (spec Phase 5). Spec: [`step8_verify/design.md`](step8_verify/design.md).

**Re-run + stale-guard.** The step is self-contained: it re-runs Steps 3-7 in-memory
(each `build_all`, plus Step 7's by-country block) to get the source of truth, runs the
structural checks over those tables, and — for every output CSV present in the output
dir — compares the on-disk file to the re-run, flagging divergence as `STALE` (a warning,
not a `FAIL`: a stale artifact is a rebuild issue, not a contradiction in the numbers).

**Check catalogue** (each is one row in `step8_reconciliation.csv`, `status` PASS / WARN
/ FAIL; anchors and tolerances in `config.py`, `SHARE_TOL = 1e-2`, `REL_TOL = 1e-6`):

| Category | Phase 5 | Asserts |
|---|---|---|
| population | 5.1 | 116,005 rows; green 8,306; other 107,699; stages 6,636/834/836; financed 47,714; INVESTED 50,815; grant-and-VC 3,960 |
| trio_identity | 5.1 | `n_green + n_others == n_startups` on every table with the trio |
| shares_sum | 5.2 | T4.14/T4.15/T4.18/T4.23 shares sum to 1; T4.28 per-country origin shares sum to 1; T4.29 amount identity and share range |
| median_in_iqr | 5.2 | `q25 <= median <= q75` on T4.10/T4.11/T4.13 |
| low_n_flag | 5.5 | `(n_green < 30) == (low_n_flag == 1)`; headline/country tables carry the column |
| source_totals | 5.1/5.4 | T4.15 == deals (116,505); T4.18 == links on INVESTED; T4.29 <= disclosed deal_size; T4.6 == population/green; T4.26 firm share recomputes |
| double_counting | 5.7 | relations exceed firms (grain kept); INVESTED base is firm-grain, not relation-grain |
| stale_files | — | each present output CSV matches the re-run, else `STALE` |

`run.py` prints a PASS/WARN/FAIL summary and each non-PASS line; `--strict` exits
non-zero on any `FAIL`. **Deferred:** 5.3 end-to-end trace of ~10 firms (manual/audit)
and 5.6 Stage 2+3 re-run of headline results (already carried by the R1 columns on the
Step 3-7 tables).

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
| Investor origin by country (T4.28) | Step 7 | per-country resolution of the T4.23 origin split |
| Country funding by financing type (T4.29) | Step 7 | per country x stage green/other disclosed deal capital |
| By-country comparison of all Step 5/6 tables | Step 7 (block B) | one collapsed `<table>_by_country.csv` per Step 5/6 table |

## Open items to resolve before Steps 5-6

1. **Green count reconciliation.** The local ledger yields 8,698 green firms; the
   committed `population_key` and the thesis anchor are 8,306. Results must be produced
   from the 8,306 population. Confirm which ledger is final before publishing.
2. **Debt lender types.** `DealDebtLenderRelation.csv` is one of the 36 raw tables Step
   1 does not read. Area 9's lender-type breakdown needs it added as a ninth clean
   table in Step 1 (`USECOLS`, `FILTER_COL`, a `build_relation_clean` call).
3. **Populations.** RESOLVED. T4.7 (per-capita cross-check) reads a committed
   `data/sources/worldbank_population.csv` (World Bank `SP.POP.TOTL`, fetched by
   `step4_geography.fetch_worldbank`). World Bank covers all 46 countries from one source
   and a single latest year, so every country is matched (the UK and Russia included);
   an earlier Eurostat `demo_pjan` source was dropped because it omitted the UK, Russia
   and several others.

## Rules and decisions that constrain every step

Rules N1-N10 and decisions D1-D7 live in `HANDOVER.md`. The load-bearing ones here:
N1 (amounts on the financed subsample only), N2 (financed by deal record, not
`total_raised > 0`), N4 (lifetime measures within cohort), N6 (medians primary), N9
(country denominators use the 116,005 population), N10 (label "Other European
start-ups", never "non-green").
