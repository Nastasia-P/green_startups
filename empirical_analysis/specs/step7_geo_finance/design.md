# Step 7 — Geography x Finance

Self-contained specification. Everything needed to understand, run, or rebuild this
step is in this document; no other file needs to be open.

**Implements:** thesis output T4.26 plus two additions (T4.28 investor origin by
country, T4.29 country funding by financing type), figure data for the T4.26 scatter,
and a collapsed by-country comparison of every Step 5 and Step 6 table
**Implemented by:** `empirical_analysis/step7_geo_finance/`
**Run with:** `python -m empirical_analysis.step7_geo_finance.run`

---

## 1. Purpose

Steps 4-6 answered *where* green start-ups are (geography), *how much* they raise
(funding), and *by whom* they are financed (investors) as three separate cuts. Step 7
crosses geography with finance to answer three questions the earlier steps deferred:

- **Does green punch above its weight in capital? (T4.26)** For each country, compare
  the green **share of firms** with the green **share of capital**. If green firms are
  10% of a country's start-ups but attract 30% of its capital, green is
  capital-concentrated there. This is the geography x finance bridge (decision D6),
  deferred from Step 6.
- **Where does the money come from, country by country? (T4.28)** For each HQ country,
  the domestic / European cross-border / non-European split of its start-ups'
  investors, green vs other — the Step 6 T4.23 origin question resolved per country.
- **What kind of financing does each country raise? (T4.29)** Per country x
  `stage_group`, the green vs other split of disclosed deal capital.
- **How much capital is recorded in each country? (T4.10 addition)** Per country,
  the summed lifetime `total_raised` for green, other, and total — absolute USD
  millions, not medians or shares.

Step 7 also provides **block B**: a collapsed by-country comparison of every Step 5
and Step 6 table, so any headline funding or investor statistic can be read country by
country without re-running those steps. Block B redefines no statistic — it reuses the
Step 5/6 builders on per-country slices (see §5).

Step 7 is **descriptive only** and is a 2026 snapshot of *recorded* capital, not a
historical investment-flow series.

**The central design constraint** carries over from Steps 5-6: green firms are 2-2.5x
better documented, so raw amount comparisons measure coverage, not capital. Firm
*shares* (T4.26 numerator) use the full population; *capital* measures are reported
with their coverage shown, and amount/access comparisons in block B reuse the financed
/ INVESTED subsamples exactly as Steps 5-6 do.

**No country floor (per user).** Unlike the earlier draft (decision D4's
`MIN_COUNTRY_N = 500`), Step 7 reports **every country with at least one start-up**,
and Step 4 was amended to do the same. Thin cells are marked with `low_n_flag`
(green < 30) rather than dropped. This keeps Step 4 and Step 7 consistent. Cities keep
their own floor in Step 4 (`MIN_CITY_N = 100`); that is unchanged.

---

## 2. Inputs

| Input | Grain | Used for |
|---|---|---|
| `company_analysis.parquet` (Step 2) | 1 per firm | per-country population, firm share, `total_raised` capital, block B firm-grain metrics |
| `deals_clean.parquet` (Step 1) | 1 per deal | disclosed `deal_size` capital (T4.26 cross-check, T4.29), block B deal-grain metrics |
| `company_investors_clean.parquet` (Step 1) | 1 per firm x investor | T4.28 relation grain, block B T4.18/T4.23 |
| `investors_clean.parquet` (Step 1) | 1 per investor | investor `investor_country` / `investor_type_grp` for T4.28 |
| `deal_investors_clean.parquet` (Step 1) | 1 per deal x investor | block B T4.25 lead flag |

Firm columns consumed: `company_id`, `green`, `hq_country`, `total_raised`, plus every
column the reused Step 5/6 builders need (`financed`, `cohort`, `age_years`, the
`any_*` flags, `first_funding_lag`, `first_vc_lag`, `n_deals`, `n_investors_lifetime`,
the investor flags, `public_private_*`, `any_grant`, `any_vc`, `green_signal_group`).

Deal columns consumed: `company_id`, `deal_id`, `deal_date`, `stage_group`,
`deal_size`, plus what block B needs (`size_is_actual`, `post_valuation`,
`n_investors`, `n_new_investors`, `is_first_deal`).

Path resolution copies Step 6; `--firm-table` overrides and accepts either the Parquet
file or the Step 2 output directory that contains it:

1. environment variable `STEP7_FIRM_TABLE`
2. the target machine's OneDrive `...\09_Python_Empirical Analysis\company_analysis.parquet`
3. `<repo>/data/outputs/company_analysis.parquet`

The clean tables resolve as `--clean-dir` > `STEP2_CLEAN_DIR` > OneDrive `clean_tables`
> `<repo>/data/outputs/clean_tables` > `<repo>/data/interim`. Output resolves as
`--output-dir` > `STEP7_OUTPUT_DIR` > OneDrive `chapter4_outputs` >
`<repo>/data/outputs/chapter4`.

---

## 3. Conventions for every output

- Group labels are always **"Green start-ups"** and **"Other European start-ups"**
  (rule N10). Never "non-green".
- **No country floor.** Every country present in `hq_country` gets a row. `low_n_flag`
  is 1 where `n_green < 30`; such rows are indicative only.
- **Firm share uses the full population** of the country (rule N9-style): `n_startups`
  is all firms in the country, green or not.
- **Two capital measures, both reported:**
  - `total_raised` (firm-level, PitchBook lifetime) — the headline funding-share
    numerator. Coverage is ~27% overall and 5-45% per country, so
    `coverage_total_raised` is on every T4.26 row.
  - summed disclosed `deal_size` from `deals_clean` — a cross-check and the basis for
    the by-type table (T4.29). `coverage_dealsize` is reported.
- **N1 — capital sums use only firms/deals with a recorded amount;** missing is
  unobserved, never zero.
- **Investor origin (T4.28)** is relation grain over the INVESTED subsample, known
  investor-country only, with `country_coverage` reported (mirrors Step 6 T4.23).
- **Descriptive snapshot** — the caption states this is recorded 2026 capital, not a
  time series.
- **Every table** ends with the uniform sample-size trio `n_green`, `n_others`,
  `n_startups` (grain stated in the caption).

---

## 4. Outputs

All tables are CSV. The figure is written as figure *data*; the plotted PDF is a later
cosmetic step (as with F4.1-F4.5).

### 4.1 `T4_26_green_share_firms_vs_capital.csv` — firm share vs funding share (T4.26)

**Country grain**, one row per country. The bridge exhibit: green share of firms vs
green share of capital.

| Column | Meaning |
|---|---|
| `country` | HQ country |
| `green_firm_share` | green firms / all firms in the country (full population) |
| `green_funding_share_total_raised` | green `total_raised` sum / all `total_raised` sum (recorded amounts only) |
| `green_funding_share_dealsize` | green disclosed `deal_size` sum / all disclosed `deal_size` sum |
| `ratio_tr` | `green_funding_share_total_raised / green_firm_share` (>1 = green capital-concentrated) |
| `ratio_ds` | `green_funding_share_dealsize / green_firm_share` |
| `coverage_total_raised` | share of the country's firms with a recorded `total_raised` |
| `coverage_dealsize` | share of the country's firms with at least one disclosed-size deal |
| `low_n_flag` | 1 if `n_green < 30` |
| `n_green`, `n_others`, `n_startups` | firms in the country (green / other / total) |

Sorted by `n_startups` descending.

### 4.2 `T4_10_cumulative_total_raised_by_country.csv` — cumulative total raised (T4.10 addition)

**Country grain**, one row per country. The absolute-capital counterpart to T4.26's
funding shares and block B's median T4.10: summed lifetime `total_raised`, not a
median and not a share.

| Column | Meaning |
|---|---|
| `country` | HQ country |
| `green_total_raised` | sum of recorded `total_raised`, green firms (USD m) |
| `other_total_raised` | sum of recorded `total_raised`, other firms (USD m) |
| `total_total_raised` | green + other (recorded amounts only) |
| `coverage_total_raised` | share of the country's firms with a recorded `total_raised` |
| `low_n_flag` | 1 if `n_green < 30` |
| `n_green`, `n_others`, `n_startups` | firms in the country (full population) |

Sorted by `n_startups` descending. Sums reconcile to T4.26 funding shares where
`total_total_raised > 0`.

### 4.3 `T4_28_investor_origin_by_country.csv` — investor origin by country (T4.28)

**Relation grain over INVESTED, known-country only**, one row per country. Where each
country's start-ups' investors come from, green vs other.

| Column | Meaning |
|---|---|
| `country` | firm HQ country |
| `green_domestic`, `green_eu_cross_border`, `green_non_european` | green relation shares by origin (sum to 1) |
| `other_domestic`, `other_eu_cross_border`, `other_non_european` | same for other |
| `country_coverage` | share of the country's relations with a known investor country |
| `low_n_flag` | 1 if `n_green < 30` (green relations) |
| `n_green`, `n_others`, `n_startups` | **known-country relations** in the country (green / other / total) |

Origin classification matches Step 6 T4.23: domestic = investor country equals the
firm's `hq_country`; European cross-border = a different but European country;
non-European = a known non-European country. European = any country appearing as an
`hq_country`.

### 4.4 `T4_29_country_funding_by_type.csv` — country funding by financing type (T4.29)

**Country x `stage_group` grain**, from summed disclosed `deal_size`.

| Column | Meaning |
|---|---|
| `country` | firm HQ country |
| `stage_group` | deal stage |
| `green_amount` | green disclosed `deal_size` sum at this country x stage |
| `other_amount` | same for other |
| `total_amount` | green + other |
| `green_amount_share` | `green_amount / total_amount` |
| `low_n_flag` | 1 if `n_deals_green < 30` |
| `n_green`, `n_others`, `n_startups` | **deals with a disclosed size** at this country x stage (green / other / total) |

Rows are ordered by country (n_startups descending) then `STAGE_GROUP_ORDER`.

### 4.5 `F4_26_green_share_scatter.csv` — figure data for the T4.26 scatter

| Column | Meaning |
|---|---|
| `country` | HQ country |
| `green_firm_share` | x-axis |
| `green_funding_share_total_raised` | y-axis |
| `reference` | the y = x line value (equals `green_firm_share`) |
| `low_n_flag` | 1 if `n_green < 30` |
| `n_green`, `n_others`, `n_startups` | firms in the country |

### 4.6 Block B — collapsed by-country comparison (`*_by_country.csv`)

For every Step 5 and Step 6 table, one file with **one row per country** carrying that
table's **headline statistic** green vs other, plus a difference or ratio, the trio,
and `low_n_flag`. The table's secondary dimension (cohort / stage / measure / full
distribution) is **collapsed** — the Europe-wide Step 5/6 table remains the place to
see that detail. Values equal the corresponding Step 5/6 builder run on the country's
slice (§5), so nothing is redefined.

| Source | Output | Headline statistic(s) per country |
|---|---|---|
| T4.9 | `T4_09_funding_access_by_country.csv` | `share_financed`, `share_vc` (green/other, full population) |
| T4.10 | `T4_10_total_raised_by_cohort_by_country.csv` | median `total_raised` (financed), cohorts collapsed |
| T4.11 | `T4_11_first_financing_size_by_stage_by_country.csv` | median first-deal size (financed), stages collapsed |
| T4.12 | `T4_12_post_valuation_by_country.csv` | median `post_valuation` (financed) |
| T4.13 | `T4_13_time_to_financing_by_country.csv` | median `first_funding_lag`, median `first_vc_lag` (financed) |
| T4.14 | `T4_14_first_financing_type_by_country.csv` | share whose first deal is a VC-stage round |
| T4.15 | `T4_15_stage_composition_by_country.csv` | VC-stage share of deals (deal grain) |
| T4.16 | `T4_16_median_deal_size_by_stage_by_country.csv` | median deal size over deals with a size (stages collapsed) |
| T4.17 | `T4_17_financing_trajectories_by_country.csv` | median rounds per firm, share with >=2 rounds (financed) |
| T4.18/F4.5 | `T4_18_investor_type_distribution_by_country.csv` | share of INVESTED firms with >=1 independent-VC investor |
| T4.19 | `T4_19_investor_flags_by_country.csv` | median distinct investors (INVESTED) |
| T4.21 | `T4_21_public_private_by_country.csv` | share with lifetime public+private combination (INVESTED) |
| T4.22 | `T4_22_grant_to_vc_by_country.csv` | share where grant preceded VC among grant-and-VC firms |
| T4.23 | `T4_23_investor_origin_by_country.csv` | domestic / EU cross-border / non-European relation shares |
| T4.25 | `T4_25_syndication_by_country.csv` | median investors per round, multi-investor share (deal grain, stages pooled) |

Common columns on every block-B table: `country`, the headline green/other value(s),
`difference` or `ratio`, `low_n_flag` (green < 30), `n_green`, `n_others`,
`n_startups`. The grain (firms / financed firms / INVESTED firms / relations / rounds)
matches the source table and is stated in the caption.

---

## 5. Rules that apply throughout

- **No country floor.** Every country is reported; thin green cells carry
  `low_n_flag`. Step 4 uses the same rule (its `MIN_COUNTRY_N` is set to 1).
- **Firm share on the full population; capital with coverage shown.** T4.26's
  numerator is firm counts; its capital shares use recorded amounts only, with
  coverage on the row.
- **Two capital measures.** `total_raised` and summed disclosed `deal_size` are both
  reported; they answer the funding-share question two ways.
- **Block B reuses the Step 5/6 definitions.** Each headline metric is computed by the
  same helpers and subsample rules the Step 5/6 builders use (`_financed`,
  `_invested`, `_median`, `_split`, the VC/stage sets), applied to a single-country
  slice and reduced to one row. A by-country value equals the Europe-wide builder run
  on that country. Steps 5/6 are unchanged.
- **Known-country only (T4.28).** Origin shares exclude relations with a missing
  investor country; coverage is reported per country.
- **Grain is stated** in each caption; the trio names are uniform.

---

## 6. Acceptance checks

The run prints these at the end. Step 7 is done when they pass.

- [ ] T4.10 cumulative total_raised sums reconcile to T4.26 funding shares per country
- [ ] T4.26 reports every country (no floor); the count of `low_n_flag` rows is
      printed, and an informational count at the former >=500 floor is shown
- [ ] T4.26 `green_funding_share` uses recorded amounts only; `coverage_total_raised`
      and `coverage_dealsize` are on every row and < 1 where amounts are missing
- [ ] T4.26 `ratio_tr > 1` flags capital-concentrated countries (e.g. Germany ~10%
      firms -> ~31% capital; Sweden ~4% -> ~43%)
- [ ] T4.28 origin shares sum to 1 within each group per country; unknown-country
      relations are excluded and coverage is reported
- [ ] T4.29 amounts reconcile to the disclosed-size deal total when summed over
      country x stage
- [ ] Block B: each `*_by_country.csv` has a leading `country` column, one row per
      country, and a headline value that equals the Step 5/6 builder run on that
      country's slice
- [ ] every table ends with `n_green`, `n_others`, `n_startups`

## 7. Decisions taken, with defaults

| Decision | Default | Where to change |
|---|---|---|
| Country floor | none (report all; `MIN_COUNTRY_N = 1`) | `MIN_COUNTRY_N` in `config.py` |
| Capital measures | both `total_raised` and disclosed `deal_size` | `build.py` (T4.26) |
| Low-n flag threshold | green < 30 | `LOW_N_FLAG` in `config.py` |
| INVESTED threshold (block B) | `n_investors_lifetime >= 1` | reused from Step 6 `config.py` |
| Stage order | Step 5/6 `STAGE_GROUP_ORDER` | `config.py` |
| European set | firm `hq_country` domain | derived at runtime in `build.py` |

## 8. Out of scope

- Plotted PDF figures — this step writes figure *data* only.
- F4.4 cumulative financed curve — remains Europe-wide in Step 5 only (`F4_04_cumulative_financed.csv`); the multi-horizon access curve does not collapse to a single by-country headline.
- T4.20 (green subsegment x investor type) and T4.24 (non-European by stage) — remain
  deferred (Step 6 §3); Step 7 does not add the vertical or stage x country cuts.
- NUTS-2 regional grain (T4.27 stretch) — not attempted.

## 9. How to run it

```bash
# build from the local Step 2 + Step 1 outputs
python -m empirical_analysis.step7_geo_finance.run \
    --firm-table data/outputs/company_analysis.parquet \
    --clean-dir data/outputs/clean_tables \
    --output-dir data/outputs/chapter4

# on the target machine, the OneDrive paths resolve on their own
python -m empirical_analysis.step7_geo_finance.run
```

Tests: `python -m pytest empirical_analysis/step7_geo_finance/tests/ -q`
