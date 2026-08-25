# Step 5 — Funding

Self-contained specification. Everything needed to understand, run, or rebuild this
step is in this document; no other file needs to be open.

**Implements:** thesis outputs T4.9-T4.17 (incl. T4.12) and figure data F4.4
**Implemented by:** `empirical_analysis/step5_funding/`
**Run with:** `python -m empirical_analysis.step5_funding.run`

---

## 1. Purpose

Step 5 is the core of the chapter: it asks whether green start-ups raise capital
differently from other European start-ups. It follows the structure **access ->
amount -> timing/stage -> trajectory**:

- **Access** (extensive margin): what share of firms received any financing, VC, a
  grant, debt, and so on.
- **Amount**: how much financed firms raised, adjusted for how long they have had to
  raise it (founding cohort).
- **Timing**: how long firms took to reach first financing and first VC.
- **Stage and trajectory**: which stages deals sit at, how large they are, and how
  firms progress across rounds.

Step 5 is **descriptive only**. It reads the Step 2 firm table and the Step 1
`deals_clean` table, groups, and summarises. It computes no new per-firm variables:
Step 2 already carries every access flag, lag, and amount field it needs.

**The central design constraint.** Green firms are 2-2.5x better documented in
PitchBook than other start-ups (Step 3 / T4.0). Comparing raw funding amounts across
the full population would therefore measure coverage, not capital. So **amounts are
compared only within the financed subsample** (firms with a real deal record), while
**access is measured on the full population**. Missing funding is treated as
*unobserved*, never as *zero*.

---

## 2. Inputs

| Input | Grain | Used for |
|---|---|---|
| `company_analysis.parquet` (Step 2) | 1 per firm | T4.9-T4.14, T4.17, F4.4 |
| `deals_clean.parquet` (Step 1) | 1 per deal | T4.11 first-deal stage/size actuality, T4.12 valuation, T4.15-T4.16, T4.17 intervals |

Firm columns consumed: `company_id`, `green`, `green_signal_group`, `cohort`,
`age_years`, `financed`, `total_raised`, `last_deal_size`, `median_deal_size`,
`n_deals`, `n_deals_with_size`, the seven access flags (`any_vc`, `any_grant`,
`any_debt`, `any_accelerator`, `any_growth_pe`, `any_crowdfunding`, plus `financed`
itself), `first_funding_lag`, `first_vc_lag`.

Deal columns consumed: `company_id`, `deal_date`, `stage_group`, `deal_size`,
`size_is_actual`, `post_valuation`, `is_first_deal`.

Path resolution copies Steps 3-4; `--firm-table` overrides and accepts either the
Parquet file or the Step 2 output directory that contains it:

1. environment variable `STEP5_FIRM_TABLE`
2. the target machine's OneDrive `...\09_Python_Empirical Analysis\company_analysis.parquet`
3. `<repo>/data/outputs/company_analysis.parquet`

`deals_clean` resolves as `--clean-dir` > `STEP2_CLEAN_DIR` > OneDrive `clean_tables`
> `<repo>/data/outputs/clean_tables` > `<repo>/data/interim`. Output resolves as
`--output-dir` > `STEP5_OUTPUT_DIR` > OneDrive `chapter4_outputs` >
`<repo>/data/outputs/chapter4`.

---

## 3. Conventions for every output

- Group labels are always **"Green start-ups"** and **"Other European start-ups"**
  (rule N10). Never "non-green".
- **N1 — amounts on the financed subsample.** Every amount, size, valuation, lag and
  trajectory statistic is computed only over firms with `financed == 1`. Missing
  amount is unobserved, not zero.
- **N2 — access on the full population.** T4.9 and F4.4 use all 116,005 firms, and
  `financed` comes from the deal record, never from `total_raised > 0`.
- **N4 / R2 — cohort adjustment.** Lifetime amounts (`total_raised`) are reported
  within founding cohort. A 2017 firm has had far longer to raise than a 2025 one.
- **N5 / R4 — censoring.** Any "within N years" or follow-on measure restricts to
  firms with a full observation window. The snapshot year is **2026** (so
  `age_years = 2026 - year_founded`). The eligible n is stated on every such row.
- **N6 — medians primary.** Medians lead, always with Q25/Q75 and n. Means and P90
  appear only as secondary columns on T4.10.
- **N8 — accelerator is its own category.** Accelerator/Incubator is a separate access
  row and stage group; it is never folded into VC or seed.
- **R1 — green stage split.** Where marked, green firms are split into Stage 1
  (vertical) and Stage 2+3 (text) via `green_signal_group`, added as extra columns.
- **Every table reports its own n**, and ends with the uniform sample-size trio
  `n_green`, `n_others`, `n_startups` (same convention as Steps 3-4).

**R3 (repeat headline funding within industry) is deferred**, like the NUTS-2 cut in
Step 4. Step 2 carries `primary_sector`, so it can be added later without new inputs.

---

## 4. Outputs

All tables are CSV. F4.4 is written as figure *data*; the plotted PDF is a later,
cosmetic step (as with F4.1-F4.3).

### 4.1 `T4_09_funding_access.csv` — access to finance (T4.9)

Extensive margin, **full population** (rule N2). One row per financing type.

| Column | Meaning |
|---|---|
| `financing_type` | any_financing, any_vc, any_grant, any_debt, any_accelerator, any_growth_pe, any_crowdfunding |
| `green_pct` | share of green firms with the flag (denominator 8,306) |
| `other_pct` | share of other firms with the flag (denominator 107,699) |
| `pp_difference` | `(green_pct - other_pct) * 100` |
| `green_pct_stage1` | share among Stage 1 green (denominator 6,636) |
| `green_pct_stage2plus3` | share among Stage 2+3 green (denominator 1,670) |
| `n_green`, `n_others`, `n_startups` | firms carrying the flag (green / other / total) |

`any_financing` equals `financed`; its `green_pct` must match Step 3's `share_financed`.

### 4.2 `T4_10_total_raised_by_cohort.csv` — total raised by cohort (T4.10)

Amount comparison, **financed subsample** with non-null `total_raised`, within cohort
(rules N1, N4). One block of rows per amount field, one row per cohort.

| Column | Meaning |
|---|---|
| `amount_field` | `total_raised`, `last_deal_size`, `median_deal_size` |
| `cohort` | 2016-2018 / 2019-2021 / 2022-2024 / 2025-2026 |
| `green_median`, `green_q25`, `green_q75`, `green_mean`, `green_p90` | green distribution |
| `other_median`, `other_q25`, `other_q75`, `other_mean`, `other_p90` | other distribution |
| `median_ratio` | `green_median / other_median` |
| `green_median_stage1`, `green_median_stage2plus3` | R1 medians |
| `n_green`, `n_others`, `n_startups` | financed firms with the field present |

`total_raised` is the headline lifetime amount; `last_deal_size` and
`median_deal_size` are the requested firm-level additions (ROADMAP). The acceptance
report prints `n_deals_with_size / n_deals` context (spec V1.41).

### 4.3 `T4_11_first_financing_size_by_stage.csv` — first financing size by stage (T4.11)

**Financed subsample.** Each financed firm's earliest `deals_clean` row supplies the
first `stage_group` and first `deal_size`. Grain: `stage_group`.

| Column | Meaning |
|---|---|
| `stage_group` | stage of the firm's first deal |
| `green_median`, `green_q25`, `green_q75` | first-size distribution, green |
| `other_median`, `other_q25`, `other_q75` | first-size distribution, other |
| `median_ratio` | green / other |
| `share_size_actual` | share of first sizes with `size_is_actual == 1` (spec V2.7) |
| `n_green`, `n_others`, `n_startups` | firms with a non-null first size in that stage |

### 4.4 `T4_12_post_valuation.csv` — post-money valuation (T4.12)

**Financed subsample**, deals with a non-null `post_valuation`. Coverage is low, so n
is reported prominently and the table is written even if small (never dropped).

| Column | Meaning |
|---|---|
| `group` | Green start-ups / Other European start-ups / All financed |
| `median`, `q25`, `q75` | post-money valuation distribution |
| `n_green`, `n_others`, `n_startups` | firms with >=1 valued deal |

### 4.5 `T4_13_time_to_financing.csv` — time to first financing (T4.13)

**Financed subsample**, non-null lags (negatives already NA from Step 2). Rows for
`first_funding_lag` and `first_vc_lag`, overall and by cohort.

| Column | Meaning |
|---|---|
| `measure` | first_funding_lag / first_vc_lag |
| `cohort` | `all` or a cohort label |
| `green_median`, `green_q25`, `green_q75` | years, green |
| `other_median`, `other_q25`, `other_q75` | years, other |
| `difference` | green_median - other_median |
| `green_median_stage1`, `green_median_stage2plus3` | R1 medians (overall rows only) |
| `n_green`, `n_others`, `n_startups` | firms with the lag present |

The first-financing vs first-VC distinction is the chapter's headline timing result:
green firms may reach *some* capital as fast or faster, yet reach *VC* more slowly.

### 4.6 `T4_14_first_financing_type.csv` — first financing type (T4.14)

**Financed subsample.** Composition of the first deal's `stage_group`, within group.

| Column | Meaning |
|---|---|
| `stage_group` | stage of the first deal |
| `green_pct` | share of green financed firms whose first deal is this stage |
| `other_pct` | share of other financed firms |
| `pp_difference` | `(green_pct - other_pct) * 100` |
| `green_pct_stage1`, `green_pct_stage2plus3` | R1 shares |
| `n_green`, `n_others`, `n_startups` | firms whose first deal is this stage |

### 4.7 `T4_15_stage_composition.csv` — deal stage composition (T4.15)

**Deal grain** — every row of `deals_clean`, green attributed by firm join. Do not join
investors before aggregating. Share of *deals* at each stage, within each group's own
deal total.

| Column | Meaning |
|---|---|
| `stage_group` | deal stage |
| `green_pct` | share of green firms' deals at this stage |
| `other_pct` | share of other firms' deals at this stage |
| `pp_difference` | `(green_pct - other_pct) * 100` |
| `n_green`, `n_others`, `n_startups` | deals at this stage (green / other / total) |

Here `n_startups` counts **deals**, not firms (deal grain); the trio name is kept for
uniformity and the caption states the grain.

### 4.8 `T4_16_median_deal_size_by_stage.csv` — median deal size by stage (T4.16)

**Deals with a non-null `deal_size`.** Median deal size by `stage_group` x group. The
**Grant row is required** (the requested dedicated grant amount) and is checked in the
acceptance report.

| Column | Meaning |
|---|---|
| `stage_group` | deal stage |
| `green_median`, `other_median` | median deal size |
| `median_ratio` | green / other |
| `n_green`, `n_others`, `n_startups` | deals with a size at this stage |

### 4.9 `AP... T4_17_financing_trajectories.csv` — trajectories (T4.17)

**Financed subsample**, with censoring (rule R4). One row per measure.

| Column | Meaning |
|---|---|
| `measure` | median_n_deals; share_ge_2_rounds; median_months_round1_to_2; share_seed_to_early_vc; share_early_to_later_vc |
| `green_stat`, `other_stat` | value per group |
| `difference` | green - other |
| `eligibility` | the censoring rule applied to the row |
| `n_green`, `n_others`, `n_startups` | eligible firms for that measure |

The interval and progression rows exclude firms whose relevant first deal is too
recent to have permitted a follow-on within the observation window (snapshot 2026,
minimum window 1 year).

### 4.10 `F4_04_cumulative_financed.csv` — cumulative financed (F4.4)

Figure data. For each horizon `h = 0..10` years since founding, among firms old enough
to have a full h-year window (`age_years >= h`, rule R4), the share financed by year h.

| Column | Meaning |
|---|---|
| `years_since_founding` | h |
| `green_share_financed` | share of eligible green with `first_funding_lag <= h` |
| `other_share_financed` | same for other |
| `green_share_vc` | share of eligible green with `first_vc_lag <= h` |
| `other_share_vc` | same for other |
| `n_green`, `n_others`, `n_startups` | eligible firms at horizon h (`age_years >= h`) |

Access curve (rule N2) is on the **full population**; only the R4 window restricts it.

---

## 5. Rules that apply throughout

- **Financed = deal record (N2).** Never `total_raised > 0`. A firm with a recorded
  round but no disclosed size is financed; it just contributes no amount.
- **Missing is unknown (N1).** Firms without a size, valuation, or lag are dropped from
  that statistic only and their absence is disclosed as n, never imputed as zero.
- **Cohort controls exposure (N4).** Lifetime totals are only compared within cohort.
- **Censoring is explicit (R4).** Any horizon or follow-on measure states its eligible
  subsample; young firms without the full window are excluded, not counted as failures.

---

## 6. Acceptance checks

The run prints these at the end. Step 5 is done when they pass.

- [ ] financed subsample = 47,714 (green + other); T4.9 `any_financing` green_pct
      matches Step 3 `share_financed`
- [ ] T4.10 cohort n over `total_raised` sums to the financed-with-`total_raised` count
- [ ] T4.13 reports first_funding_lag and first_vc_lag separately, overall and by cohort
- [ ] T4.15 total deals equals the `deals_clean` row count
- [ ] T4.16 contains a Grant row
- [ ] every table ends with `n_green`, `n_others`, `n_startups`, and amount tables carry
      only financed firms (rule N1)

## 7. Decisions taken, with defaults

| Decision | Default | Where to change |
|---|---|---|
| VC stage groups | Angel/Seed, Early-stage VC, Later-stage VC | `VC_STAGE_GROUPS` in `config.py` |
| Snapshot year (censoring) | 2026 | `SNAPSHOT_YEAR` in `config.py` |
| Follow-on minimum window | 1 year | `FOLLOWON_MIN_WINDOW_YEARS` in `config.py` |
| F4.4 horizons | 0..10 years | `FINANCED_CURVE_HORIZONS` in `config.py` |
| Low-n flag threshold | 30 | `LOW_N_FLAG` in `config.py` |

## 8. Out of scope

- Within-industry repeat of headline funding (R3) — deferred; `primary_sector` is present.
- Investor, grant-sequencing, public/private, and geography tables (T4.18-T4.26) — Step 6.
- The full DealType->stage_group taxonomy appendix (AP3) — already emitted by Step 1
  as `deal_types_seen.csv`.
- Plotted PDF figures — this step writes figure *data* only.

## 9. How to run it

```bash
# build from the local Step 2 + Step 1 outputs
python -m empirical_analysis.step5_funding.run \
    --firm-table data/outputs/company_analysis.parquet \
    --clean-dir data/outputs/clean_tables \
    --output-dir data/outputs/chapter4

# on the target machine, the OneDrive paths resolve on their own
python -m empirical_analysis.step5_funding.run
```

Tests: `python -m pytest empirical_analysis/step5_funding/tests/ -q`
