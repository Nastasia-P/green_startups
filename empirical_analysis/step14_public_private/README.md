# Step 14 — Public/private investor participation (supplementary, read-only)

Addresses the supervisor's public/private request: define exactly which
investor categories count as public vs private, measure public/private
participation and co-investment within the common horizon, adjust for
composition, describe public/private (and grant->VC) sequencing, and — only if
the data permit — compare public/private capital. Everything is estimated on
the **Step 5b common-horizon dataset** (`first5_analysis.parquet`, the 31,257
firms founded 2016-2020 with a complete five-year window), restricted to each
firm's first-five-year window, and joined to the Step 1 investor tables.

**This is not causal.** Every association is conditional; sequencing is
descriptive ordering, not crowding-in; and (see below) the data contain no
investor-level capital amount, so we never fabricate per-investor "public" or
"private" capital.

## 1. Investor classification (define public vs private explicitly)

The classification is the single source of truth in
[`config.py`](config.py) (`ANALYTICAL_GROUP`) and is **not decided silently in
code**. It covers 100% of the observed `investor_type_grp` values;
[`investor_type_mapping.csv`](../../data/outputs/chapter4/investor_type_mapping.csv)
reproduces it with counts. An acceptance check fails if any observed type is
unmapped.

| investor_type_grp | analytical group | n_investors | n_relationships | n_firms |
|---|---|---:|---:|---:|
| Public/Government | **public** | 1,350 | 8,931 | 6,633 |
| Independent VC | **private** | 9,633 | 57,127 | 22,091 |
| Corporate | **private** | 9,370 | 16,762 | 10,145 |
| Angel | **private** | 16,913 | 27,025 | 9,125 |
| PE/Growth | **private** | 2,970 | 9,556 | 7,781 |
| Family Office | **private** | 968 | 2,700 | 2,399 |
| Impact Investing | exclude | 551 | 2,551 | 2,082 |
| Accelerator/Incubator | exclude | 3,975 | 40,196 | 23,766 |
| Lender/Debt | exclude | 272 | 1,122 | 1,022 |
| Other/Unclassified | exclude | 1,777 | 4,667 | 3,909 |

`public` = government/state-backed capital; `private` = market/commercial equity
capital; `exclude` = categories that are not a clean public-vs-private equity
signal. Excluded types still count toward `has_investor_record_5yr` /
`n_investors_5yr` but never toward public or private. (n_investors from
`investors_clean`; n_relationships from `deal_investors_clean`; n_firms =
distinct companies reached, lifetime — this is a data-dictionary audit of the
classification, not the common-horizon sample.)

## 2. Common-horizon participation variables (firm level)

`prepare_window()` (Step 5b) gives each eligible firm's in-window deals; these
are joined `deals -> deal_investors_clean -> investors_clean`, classified, and
aggregated to one row per eligible firm in
[`pubpriv_analysis_5yr.parquet`](../../data/outputs/chapter4/pubpriv_analysis_5yr.parquet):
`has_investor_record_5yr`, `any_public_5yr`, `any_private_5yr`,
`both_public_private_5yr`, `same_deal_public_private_5yr`, `n_investors_5yr`.

`same_deal_public_private_5yr` (a single in-window deal carrying both a public
and a private investor) is logically a **subset** of `both_public_private_5yr`
(ever both within the window); an acceptance check enforces this.

### Two denominators

[`T14_pubpriv_participation.csv`](../../data/outputs/chapter4/T14_pubpriv_participation.csv)
reports green vs other under two denominators, so investor-record coverage is
transparent rather than treating "no recorded investor" as substantive
non-participation:

- **primary** = firms with >=1 in-window investor relationship
  (`has_investor_record_5yr==1`, matching Step 6's INVESTED logic);
- **sensitivity** = all 31,257 eligible firms.

## 3. Adjusted public/private regressions

[`T14_pubpriv_regression.csv`](../../data/outputs/chapter4/T14_pubpriv_regression.csv):
linear probability models (HC1 SE) for four outcomes — `any_public`,
`any_private`, `both_public_private`, `same_deal_public_private` — on the
primary investor-record sample. Columns:

```
(1) green   (2) +cohort   (3) +country FE   (4) +industry FE      [MAIN]
(5) + deal count  (adds log(1 + n_deals_5yr))                     [SENSITIVITY]
```

Deal count is **not** the baseline: the number of deals is part of a firm's
financing history and may sit downstream of green status, so it is the
supervisor's requested sensitivity (column (5)), not a main specification.
Coefficients are stored raw (0-1) and as percentage points (`coef_pp`/`se_pp`);
significance stars are generated from the stored p-value (`* p<.10, ** p<.05,
*** p<.01`), never hard-coded. Machine-readable CSV only — no LaTeX/formatted
tables. Decimal precision is the tunable `config.DECIMALS`/`config.DECIMALS_PP`.

## 4. Sequencing (descriptive, common horizon)

- [`T14_grant_vc_sequencing_5yr.csv`](../../data/outputs/chapter4/T14_grant_vc_sequencing_5yr.csv):
  among eligible firms with both an in-window grant and in-window VC event —
  grant first / VC first / same date, and median months grant-to-VC.
- [`T14_pubpriv_sequencing_5yr.csv`](../../data/outputs/chapter4/T14_pubpriv_sequencing_5yr.csv):
  among eligible firms with both an in-window public and in-window private
  investor — public first / private first / same date / same deal, and median
  months public-to-private.
- [`T14_pubpriv_ordering_regression.csv`](../../data/outputs/chapter4/T14_pubpriv_ordering_regression.csv)
  (**supplementary**): adjusted LPM for `public_precedes_private` among firms
  that have both types in-window. This sample is selected on receiving both
  types of capital, so it is a conditional, not a population, statement.

All sequencing is descriptive ordering — it is not evidence that public capital
caused later private capital (no crowding-in claim).

## 5. Capital by investor composition (amounts audit + fallback)

[`investor_amount_audit.csv`](../../data/outputs/chapter4/investor_amount_audit.csv)
records that `deal_investors_clean` carries only
`deal_id, investor_id, investor_name, investor_status, is_lead` — there is **no
investor-level contributed amount**. We therefore do not split or duplicate a
deal amount across investors.

Instead,
[`T14_deal_size_by_investor_composition_5yr.csv`](../../data/outputs/chapter4/T14_deal_size_by_investor_composition_5yr.csv)
classifies disclosed in-window deals as public-only / private-only / mixed
public-private / other-or-neither (by the investor types present on the deal)
and compares their disclosed deal sizes (median, sum, n_deals, n_firms), green
vs other. Only disclosed deals enter; missing sizes are never zero-filled. The
output is deal size by investor composition, **not** "public/private capital
amount".

## Inputs

- [`first5_analysis.parquet`](../../data/outputs/chapter4/first5_analysis.parquet) (Step 5b): eligible firms, controls, `n_deals_5yr`.
- [`company_analysis.parquet`](../../data/outputs/company_analysis.parquet) (Step 2): for `prepare_window()`.
- Step 1 clean tables: `deals_clean`, `deal_investors_clean`, `investors_clean`.

## Run

This step needs `statsmodels`, which is **not** part of the base pipeline and
must be installed before running (it is pinned in
[`../requirements.txt`](../requirements.txt)). Without it the run exits early
with `ERROR: statsmodels is not installed`.

```bash
# install everything (base + regression deps)
pip install -r empirical_analysis/requirements.txt

# or just the missing regression dependency
pip install "statsmodels>=0.14"
```

```bash
# Step 5b must run first to produce first5_analysis.parquet
python -m empirical_analysis.step5b_fixed_horizon.run

python -m empirical_analysis.step14_public_private.run \
    --firm-panel data/outputs/chapter4/first5_analysis.parquet \
    --firm-table data/outputs/company_analysis.parquet \
    --clean-dir data/outputs/clean_tables \
    --output-dir data/outputs/chapter4 \
    --industry group

# paths resolve automatically if omitted
python -m empirical_analysis.step14_public_private.run
```

## Outputs (in `data/outputs/chapter4/`)

| File | Contents |
|---|---|
| `investor_type_mapping.csv` | the public/private/exclude classification + n_investors / n_relationships / n_firms per type (100% coverage) |
| `investor_amount_audit.csv` | evidence that no investor-level amount exists; documents the deal-level fallback |
| `pubpriv_analysis_5yr.parquet` | one row per eligible firm with the in-window participation flags |
| `T14_pubpriv_participation.csv` | green vs other participation under two denominators (invested, eligible) |
| `T_first5_investor_type_participation.csv` | per investor type x group: share of INVESTED firms with >=1 such investor in-window (non-exclusive); Figure 5 source |
| `T_first5_public_private.csv` | four public/private outcomes green vs other on the INVESTED denominator; Figure S1 source |
| `T14_pubpriv_regression.csv` | LPM (1)-(4) main + (5) "+ deal count" sensitivity for the four outcomes |
| `T14_grant_vc_sequencing_5yr.csv` | in-window grant->VC ordering, green vs other |
| `T14_pubpriv_sequencing_5yr.csv` | in-window public/private ordering, green vs other |
| `T14_pubpriv_ordering_regression.csv` | supplementary LPM for public_precedes_private (selected sample) |
| `T14_deal_size_by_investor_composition_5yr.csv` | disclosed deal size by investor composition |
| `step14_sample_audit.csv` | per-spec regression audit (n, n_green, n_other, unique firms, FE counts) |
| `captions_step14.csv` | captions: classification, denominators, sensitivity framing, and the capital caveat |

The run prints the classification, coefficient paths and an acceptance report
(eight checks): classification covers 100% of observed types; `same_deal` is a
subset of `both`; two denominators reported with invested <= eligible;
regressions have specs (1)-(5) with `(n)` labels only, n == invested sample, one
row per firm; the deal-count control is present only in column (5); pp columns
scale the coefficient and stars match the stored p-value; deal-size-by-
composition uses disclosed deals only; and output names are disjoint from Steps
5/5b/6/13.

## Interpretation boundary

- **Association, not causation**, throughout.
- **Coverage.** Participation depends on investor-record coverage; the primary
  results are among firms with an in-window investor record, with the
  all-eligible figures reported as a sensitivity.
- **Capital.** No investor-level amount exists; deal-size-by-composition is a
  deal-level descriptor, not per-investor capital.
- **Selection.** The ordering regression conditions on receiving both public and
  private capital. None of this addresses survivor-selection (Step 10).
