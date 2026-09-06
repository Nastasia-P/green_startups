# Step 13 — Exploratory regression analysis (supplementary, read-only)

Checks whether the core financing differences between green and other European
start-ups **remain associated with green status after adjusting for observable
composition** — the supervisor's concern that raw green-vs-other gaps may be driven
by green firms differing in founding cohort, country and industry. It runs a small,
deliberately simple set of sequential OLS regressions and reports how the green
coefficient moves as controls are added.

**This is not causal.** Every reported green coefficient is a *conditional
association* between green status and the outcome, holding the model's controls
fixed. It is descriptive, exploratory, and optional; it reclassifies nothing and
rewrites no existing Step 1–11 output.

## What is regressed

Three small model families, each estimated as four nested specifications:

```
M0: outcome ~ green
M1: + founding cohort
M2: + country fixed effects
M3: + primary industry fixed effects
```

Reading the green coefficient across M0→M3 answers the intuitive question: *does the
green/non-green difference shrink once we account for the fact that green firms are
older, located differently, and concentrated in different industries?*

| Family | Outcomes | Estimator | Sample |
|---|---|---|---|
| 1 — access | `any_financing` (=`financed`), `any_vc`, `any_grant`, `any_accelerator` | Linear probability model (OLS) | full population (116,005) |
| 2 — timing | `first_funding_lag`, `first_vc_lag` | OLS | firms with the lag observed (non-null) |
| 3 — capital | `log(1 + disclosed capital raised in the first five post-founding years)` | OLS | step5b-eligible firms with a disclosed in-window amount |

Standard errors are **HC1 heteroskedasticity-robust** throughout (a linear
probability model is heteroskedastic by construction). The 95% confidence interval,
p-value, n and R² are reported for every model.

### Methodological flag — binary outcomes (LPM vs logistic)

Family 1's outcomes are binary. This module uses a **linear probability model
(OLS)**, which is the simplest version consistent with the brief's "simple linear
regression" and keeps the green coefficient directly readable as a
probability-point difference. A **logistic regression** is statistically more
conventional for a binary outcome and is a legitimate alternative — but it is a
methodological decision to be made deliberately, not silently, so it is **not run
here**. If it is added later, report average marginal effects (comparable to the LPM
coefficient) rather than raw odds ratios.

### Controls and the industry representation

Controls are exactly the composition factors the supervisor named: founding cohort,
country, and sector/industry. No further variables are added — the point is a simple
composition-adjusted check, not a full econometric model.

Industry membership is **multi-valued** in PitchBook (a firm carries several industry
tags), so it must never be joined in as duplicated firm×industry rows. This module
uses a single stable firm-level tag, `primary_industry_group` by default
(`--industry code` switches to `primary_industry_code`). An acceptance check confirms
the regression sample has exactly one row per firm.

Country and industry enter as fixed effects (dummies, reference level dropped). To
keep the design matrix full-rank and free of singleton dummies, FE levels with fewer
than `MIN_FE_LEVEL_N` (=50) firms — and missing values — are folded into an `Other`
level. This also fixes the sample to be identical across M0–M3, so the green
coefficient path is a clean composition-adjustment comparison rather than a moving
sample.

## Inputs (all existing, unchanged)

- Firm table [`../../data/outputs/company_analysis.parquet`](../../data/outputs/company_analysis.parquet): `green`, `financed`, `any_vc`, `any_grant`, `any_accelerator`, `first_funding_lag`, `first_vc_lag`, `cohort`, `hq_country`, `primary_industry_group` / `primary_industry_code`.
- Family 3 reuses [`step5b_fixed_horizon`](../step5b_fixed_horizon/) `prepare_window()` plus the Step 1 `deals_clean` parquet for the per-firm disclosed in-window `deal_size` sum.

## Run

Needs `statsmodels` (in [`../requirements.txt`](../requirements.txt)).

```bash
# build from the local Step 2 + Step 1 outputs
python -m empirical_analysis.step13_regression.run \
    --firm-table data/outputs/company_analysis.parquet \
    --clean-dir data/outputs/clean_tables \
    --output-dir data/outputs/chapter4 \
    --industry group

# paths resolve automatically if omitted
python -m empirical_analysis.step13_regression.run
```

Paths resolve automatically; override if needed:

- firm table: `--firm-table` > `STEP13_FIRM_TABLE` / `STEP5_FIRM_TABLE` > `data/outputs/company_analysis.parquet`
- clean tables: `--clean-dir` > `STEP2_CLEAN_DIR` > `data/outputs/clean_tables`
- output dir: `--output-dir` > `STEP13_OUTPUT_DIR` / `STEP5_OUTPUT_DIR` > `data/outputs/chapter4`

## Outputs (in `data/outputs/chapter4/`)

Each regression row: `outcome, family, model, sample, estimator, green_coef,
green_se, green_pvalue, green_ci_low, green_ci_high, n, r_squared, controls,
n_fe_country, n_fe_industry, cov_type`.

| File | Contents |
|---|---|
| `T_regression_financing_access.csv` | family 1: LPM M0–M3 for the four access outcomes |
| `T_regression_timing.csv` | family 2: OLS M0–M3 for years to first financing / first VC |
| `T_regression_first5_capital.csv` | family 3: OLS M0–M3 for log(1 + first-five-year disclosed capital) |
| `step13_regression_sample_audit.csv` | per model: n, n_green, n_other, unique firms, rows dropped for missing outcome, FE level counts, transformation, cov_type |
| `captions_step13.csv` | fixed captions: estimator choice, the LPM/logistic flag, sample definitions, and the interpretation boundary |

The run prints the green-coefficient path M0→M3 for every outcome and an acceptance
report (five checks): access sample equals the full population and `n_green +
n_other == n` on every model; all four nested models estimated with a finite green
coefficient; timing/capital use observed-only samples with n matching the non-null /
observed-amount counts (capital never zero-filled); the sample has one row per firm
(no industry-join duplication); and the module writes only its own `T_regression_*` /
`step13_*` / `captions_step13` files, disjoint from the Step 5 / step5b names.

## Conclusions (from the current run)

Reading the green coefficient across M0 to M3 (LPM coefficients are probability
points; timing is in years; capital is on a log scale):

- **Composition explains a large share of the raw access gap, but a sizeable green
  premium survives.** Most of the drop happens at M1 (adding founding cohort — green
  firms are older), with country and industry adding little beyond that. After all
  three controls (M3), green firms are still markedly more likely to have financing:
  any financing +24.2pp (raw +50.5pp), any accelerator +24.2pp (raw +34.0pp), any VC
  +15.3pp (raw +30.0pp), any grant +9.5pp (raw +13.0pp). All are highly significant
  (p < 1e-100), so the green access advantage is not merely a cohort/country/industry
  artefact.
- **Timing is close to parity, with a small VC lag.** Conditional on being financed,
  green firms reach first financing marginally *faster* (M3 -0.12 years, about six
  weeks) but reach first VC modestly *slower* (M3 +0.20 years). Both magnitudes are
  small.
- **The first-five-year capital gap is essentially composition.** Green firms raise
  slightly more disclosed capital in their first five years (M0 +0.12 log points), but
  the coefficient falls to +0.05 and loses significance once industry is added
  (M3 p = 0.11) — the raw amount edge is largely explained by which industries green
  firms are in.
- **Magnitude, not significance, is the takeaway.** With n up to 116,005 almost every
  coefficient is significant; the access premium matters because it is *large* (double
  digits in probability points), whereas the timing and capital effects, though often
  significant, are small.

These are conditional associations within the 2026 baseline sample, not causal
effects; the access sample is the full population, while timing and capital condition
on observed subsamples (47,576 / 29,951 firms for the two lags; 18,064 of 31,257
step5b-eligible firms for capital).

## Interpretation boundary

- **Association, not causation.** The green coefficient is a conditional correlation
  within the 2026 baseline sample, adjusting only for observable composition.
- **Significance ≠ importance.** With up to 116,005 observations, even tiny
  differences are statistically significant. Read the coefficient **magnitude** and
  its confidence interval, not just the p-value.
- **Selection.** The timing and capital families condition on having been financed /
  on having a disclosed amount, so they are within-subsample associations, not
  population statements. They do not address survivor-selection (see Step 10).
