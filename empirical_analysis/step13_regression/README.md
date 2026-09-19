# Step 13 — Common-horizon regression analysis (supplementary, read-only)

Checks whether the core financing differences between green and other European
start-ups **remain associated with green status after adjusting for observable
composition** — the supervisor's concern that raw green-vs-other gaps may be driven
by green firms differing in founding cohort, country and industry.

Every primary regression here is estimated on the **Step 5b common-horizon
dataset**, [`first5_analysis.parquet`](../step5b_fixed_horizon/) (see that module's
README): the 31,257 firms founded 2016–2020 whose complete five-year
`[year_founded, year_founded+5]` window is observable. This replaces the earlier
full-population / lifetime-observation financing and timing regressions, so
every association reported here refers to the same five-year observation
framework used in Section 4.3 (`T_first5_*`).

**This is not causal.** Every reported green coefficient is a *conditional
association* between green status and the outcome, holding the spec's controls
fixed. It is descriptive, exploratory, and optional; it reclassifies nothing and
rewrites no existing Step 1–11 output.

**No formatted or LaTeX tables are generated.** This module writes only
machine-readable CSVs. Each result row already carries everything needed to
typeset a thesis table by hand: the column label, coefficient, robust SE,
p-value, auto-generated significance stars, CI, n, R² and FE indicators.

## What is regressed

Three model families, each estimated as four nested specifications:

```
(1) outcome ~ green
(2) + founding cohort
(3) + country fixed effects
(4) + primary industry fixed effects
```

Internally these are `spec1`–`spec4` (see `config.SPECS`); every output-facing
column uses the plain label `(1)`–`(4)` — nothing here is named `M0`–`M3`.
Reading the green coefficient across (1)→(4) answers the intuitive question:
*does the green/non-green difference shrink once we account for the fact that
green firms are older, located differently, and concentrated in different
industries?*

| Family | Outcomes | Estimator | Sample |
|---|---|---|---|
| 1 — access | `any_financing_5yr`, `any_vc_5yr`, `any_grant_5yr`, `any_accelerator_5yr` | Linear probability model (OLS) | every common-horizon eligible firm (31,257) |
| 2 — timing (supplementary) | `first_financing_lag_5yr`, `first_vc_lag_5yr` | OLS | eligible firms that experience the event **within** their five-year window (non-null) |
| 3 — capital (intensive margin) | `log(1 + disclosed_capital_5yr)` | OLS | eligible firms with a **disclosed** in-window amount only (18,064 of 31,257) |

Standard errors are **HC1 heteroskedasticity-robust** throughout (a linear
probability model is heteroskedastic by construction). The 95% confidence
interval, p-value, n and R² are reported for every spec.

### Methodological flag — binary outcomes (LPM vs logistic)

Family 1's outcomes are binary. This module uses a **linear probability model
(OLS)**, which keeps the green coefficient directly readable as a
probability-point difference. A **logistic regression** is statistically more
conventional for a binary outcome and is a legitimate alternative — but it is a
methodological decision to be made deliberately, not silently, so it is **not run
here**.

### Percentage-point display for binary outcomes

For the three binary access outcomes the raw coefficient/SE are stored on the
model's native 0–1 scale (`coef`, `std_error`) **and** duplicated as
percentage-point display columns (`coef_pp = coef*100`, `se_pp = std_error*100`),
so a coefficient of `0.043` also appears as `4.3` pp with the SE scaled the same
way. Timing and capital outcomes are not binary; their `coef_pp`/`se_pp` are `NaN`.

### Significance stars

`stars` is generated column-by-column from the stored `p_value` via one rule
(`config.STAR_RULE`): `* p<.10, ** p<.05, *** p<.01`. Stars are never
hard-coded — change the rule in `config.py` and every table regenerates
consistently. `p_value_display` renders tiny p-values as `<0.0001`-style
instead of a misleading bare `0.0`.

### Consistent, tunable decimal precision

Two module-level constants in `config.py` are the single source of truth for
every rounded number this module writes:

- `DECIMALS` (default `4`) — governs `coef`, `std_error`, `ci_low`, `ci_high`,
  `r_squared`, `p_value`.
- `DECIMALS_PP` (default `2`) — governs `coef_pp`, `se_pp`.

Change either constant in one place to change every table's precision; no
other code hard-codes a decimal count.

### Controls and the industry representation

Controls are exactly the composition factors named in the supervisor
feedback: founding cohort, country, and industry. Industry membership is
**multi-valued** in PitchBook (a firm carries several industry tags), so it is
never joined in as duplicated firm×industry rows. This module uses the single
stable firm-level tag carried by `first5_analysis.parquet`,
`primary_industry_group` (`--industry code` switches to
`primary_industry_code` if that column has also been added upstream).

Country and industry enter as fixed effects (dummies, reference level
dropped). To keep the design matrix full-rank and free of singleton dummies,
FE levels with fewer than `MIN_FE_LEVEL_N` (=50) firms — and missing values —
are folded into an `Other` level. This also fixes the sample to be identical
across (1)–(4), so the green coefficient path is a clean composition-adjustment
comparison rather than a moving sample.

## The capital family is an intensive-margin analysis (selection made explicit)

The capital regression only ever sees eligible firms with **at least one
disclosed** in-window deal amount (18,064 of 31,257 eligible; 2,707 green,
15,357 other). It therefore estimates the **intensive margin** — how much
observed recipients raise — never the **extensive margin** (how many firms
raise anything at all; that is the access family above). Missing amounts are
excluded, never zero-filled, and never used to construct an artificial
extensive-margin capital measure.

`capital_coverage_diagnostic.csv` makes this selection explicit: it reports
`eligible_firms`, `firms_with_disclosed_capital` (overall and by green/other),
`coverage_green`/`coverage_other`, and `n_excluded_no_disclosed_amount`. This
is a **disclosure/coverage diagnostic**, not a capital-access measure — it
documents who enters the regression above, it does not replace the access
family's `any_financing_5yr` result.

## Inputs

- [`first5_analysis.parquet`](../step5b_fixed_horizon/) (Step 5b output): one row
  per common-horizon eligible firm, carrying `green`, `cohort`, `hq_country`,
  `primary_industry_group`, the four `any_*_5yr` flags, the three
  `first_*_lag_5yr` timing lags, `disclosed_capital_5yr` and
  `has_disclosed_capital_5yr`. Run `step5b_fixed_horizon` first if this file is
  missing.

## Run

This step needs `statsmodels` beyond the base pipeline; it is pinned in
[`../requirements.txt`](../requirements.txt):

```bash
# install everything (base + step 13)
pip install -r empirical_analysis/requirements.txt

# or just the regression dep
pip install "statsmodels>=0.14"
```

```bash
# Step 5b must run first to produce first5_analysis.parquet
python -m empirical_analysis.step5b_fixed_horizon.run

# then build the common-horizon regressions
python -m empirical_analysis.step13_regression.run \
    --firm-panel data/outputs/chapter4/first5_analysis.parquet \
    --output-dir data/outputs/chapter4 \
    --industry group

# paths resolve automatically if omitted
python -m empirical_analysis.step13_regression.run
```

Paths resolve automatically; override if needed:

- firm panel: `--firm-panel` > `STEP13_FIRM_PANEL` / `STEP5B_FIRM_PANEL` > `data/outputs/chapter4/first5_analysis.parquet`
- output dir: `--output-dir` > `STEP13_OUTPUT_DIR` / `STEP5_OUTPUT_DIR` > `data/outputs/chapter4`

## Outputs (in `data/outputs/chapter4/`)

Each regression row: `outcome, family, spec, column, controls, sample,
estimator, coef, std_error, p_value, p_value_display, stars, ci_low, ci_high,
coef_pp, se_pp, n, r_squared, cohort_controls, country_fe, industry_fe,
n_fe_country, n_fe_industry, cov_type`.

| File | Contents |
|---|---|
| `T_regression_access_5yr.csv` | family 1: LPM (1)–(4) for the four common-horizon access outcomes (n=31,257 on every spec) |
| `T_regression_timing_5yr.csv` | family 2 (supplementary): OLS (1)–(4) for years to first financing / first VC, conditional on the in-window event |
| `T_regression_capital_5yr.csv` | family 3 (intensive margin): OLS (1)–(4) for log(1 + disclosed in-window capital), firms with a disclosed amount only |
| `capital_coverage_diagnostic.csv` | disclosure/coverage diagnostic: eligible firms, firms with a disclosed amount (overall + green/other), coverage rates, n excluded |
| `step13_regression_sample_audit.csv` | per spec: n, n_green, n_other, unique firms, dropped-for-missing, FE level counts, transformation, cov_type |
| `captions_step13.csv` | estimator choice, sample definitions, the star rule, the decimal-precision policy, and the interpretation boundary |

Industry is a single firm-level tag (`primary_industry_group` by default; the
multi-valued industry membership is never joined in). An acceptance report (seven
checks) confirms: the access sample is every common-horizon eligible firm on
every spec; all four specs are estimated with finite coefficients and
`(1)`–`(4)` column labels only (no `M0`–`M3`); timing/capital use observed-only
samples with matching n (capital never zero-filled); one row per firm (no
industry-join duplication); output names are self-scoped and disjoint from
Step 5/step5b; percentage-point display columns scale the raw access
coefficient by 100 and are `NaN` for timing/capital; and significance stars
match `config.STAR_RULE` applied to the stored p-value on every table.

## Conclusions (from the current run)

Reading the green coefficient across (1) to (4) (LPM coefficients are
probability points via `coef_pp`; timing is in years; capital is on a log
scale), all on the 31,257-firm common horizon:

- **A green access premium survives composition adjustment, but it is far
  smaller than the (now-retired) lifetime full-population estimate.** After all
  three controls (4): any financing +6.9pp, any accelerator +14.9pp, any grant
  +10.2pp, any VC +6.8pp (all p<.001). Any VC is essentially zero at specs
  (1)–(3) and only emerges once industry is added — the raw VC gap in this
  cohort is composition, industry composition specifically.
- **Timing is close to parity through spec (3), and the financing-lag premium
  disappears once industry is added.** Green firms reach first financing
  slightly *later* at (1)–(3) (~0.09 years, about a month) but the effect is
  not distinguishable from zero at (4) (p=0.80). First VC is consistently
  slower for green firms (+0.28 years at (4), significant).
- **The intensive-margin capital gap is largely composition.** Green firms
  that disclose an amount raise moderately more (spec 1: +0.12 log points),
  but the coefficient falls to +0.047 and loses significance once industry is
  added (spec 4, p=0.11) — consistent with the access-family finding that
  industry composition, not green status per se, drives much of the raw gap.
- **The capital result is intensive-margin only.** Only 18,064 of 31,257
  eligible firms (57.8%) disclose any in-window amount (coverage: green
  62.5%, other 57.0%); see `capital_coverage_diagnostic.csv`. The regression
  says nothing about the 42.2% of eligible firms with no disclosed amount —
  that is the access family's job.

These are conditional associations within the common-horizon sample, not
causal effects.

## Interpretation boundary

- **Association, not causation.** The green coefficient is a conditional
  correlation within the common-horizon sample, adjusting only for observable
  composition.
- **Same observation framework throughout.** Access, timing and capital all use
  the Step 5b five-year window over the same 31,257 eligible firms (timing and
  capital further condition on the event/disclosure occurring, as documented
  per family above) — there is no remaining lifetime-vs-five-year
  inconsistency between this module and Section 4.3.
- **Capital is intensive-margin only.** It estimates *how much* among firms with
  a disclosed amount, not whether firms raise anything (*how many* — the
  extensive margin is the access family). See `capital_coverage_diagnostic.csv`
  for the disclosure selection this implies.
- **Selection.** The timing family conditions on the event occurring in-window,
  so it is a within-subsample association, not a population statement. None of
  this addresses survivor-selection (see Step 10).
