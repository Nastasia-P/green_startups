# Step 6 — Investors and Grants

Self-contained specification. Everything needed to understand, run, or rebuild this
step is in this document; no other file needs to be open.

**Implements:** thesis outputs T4.18, T4.19, T4.21, T4.22, T4.23, T4.25 and figure data F4.5
**Implemented by:** `empirical_analysis/step6_investors/`
**Run with:** `python -m empirical_analysis.step6_investors.run`

---

## 1. Purpose

Step 5 asked *how much* green start-ups raise. Step 6 asks **by whom** they are
financed: which investor types back them, whether public and private capital
combine, whether grants precede venture capital, and where the money comes from
geographically. It follows the sequence **who -> flags -> public/private ->
sequence -> geography -> syndication**:

- **Who** (T4.18): the distribution of investor types across relations and firms,
  using PitchBook's own `investor_type_grp` classification rather than a hand-built
  matcher.
- **Flags** (T4.19): company-level presence of each investor type and the median
  number of distinct investors.
- **Public/private** (T4.21): lifetime combination of public and private capital
  versus genuine same-deal co-investment, reported separately (they are routinely
  conflated).
- **Sequence** (T4.22): the grant -> VC pattern (Islam et al. 2018), examined
  descriptively using deal dates. Sequence is not causality.
- **Geography** (T4.23): domestic vs European cross-border vs non-European origin,
  connecting the chapter to the Draghi framing on European capital fragmentation.
- **Syndication** (T4.25): investors per round and multi-investor share, within
  stage group.

Step 6 is **descriptive only**. Most of the heavy lifting is already done by Step 2,
which carries the company-level investor flags, distinct-investor count,
public/private indicators, and investor-origin shares. Step 6 groups, joins, and
summarises; it computes no new per-firm variables.

**The central design constraint** is the same coverage asymmetry as Step 5: green
firms are 2-2.5x better documented. So the master population here is the **INVESTED
subsample** — firms with at least one recorded investor (`n_investors_lifetime >= 1`)
— rather than the full 116,005. Access to *investors* is analogous to access to
*finance*; within INVESTED the composition questions ("by whom", "from where") are
comparable across groups.

---

## 2. Inputs

| Input | Grain | Used for |
|---|---|---|
| `company_analysis.parquet` (Step 2) | 1 per firm | INVESTED population, T4.19, T4.21, T4.22 (VC-backed base), T4.23 firm shares |
| `deals_clean.parquet` (Step 1) | 1 per deal | T4.22 grant/VC dates, T4.25 stage_group / round investor counts |
| `company_investors_clean.parquet` (Step 1) | 1 per firm x investor | T4.18 and T4.23 relation grain |
| `investors_clean.parquet` (Step 1) | 1 per investor | investor `investor_type_grp` and `investor_country` |
| `deal_investors_clean.parquet` (Step 1) | 1 per deal x investor | T4.25 identified-lead flag per round |

Firm columns consumed: `company_id`, `green`, `green_signal_group`, `hq_country`,
`n_investors_lifetime`, `any_public_investor`, `any_corporate_investor`,
`any_ivc_investor`, `any_accelerator_investor`, `any_lender_investor`,
`public_private_lifetime`, `public_private_same_deal`, `any_grant`, `any_vc`.

Deal columns consumed: `company_id`, `deal_id`, `deal_date`, `stage_group`,
`vc_round`, `n_investors`, `n_new_investors`.

Relation columns consumed: `company_id`, `investor_id` (from
`company_investors_clean`); `investor_id`, `investor_type_grp`, `investor_country`
(from `investors_clean`); `deal_id`, `investor_id`, `is_lead` (from
`deal_investors_clean`).

Path resolution copies Step 5; `--firm-table` overrides and accepts either the
Parquet file or the Step 2 output directory that contains it:

1. environment variable `STEP6_FIRM_TABLE`
2. the target machine's OneDrive `...\09_Python_Empirical Analysis\company_analysis.parquet`
3. `<repo>/data/outputs/company_analysis.parquet`

The clean tables resolve as `--clean-dir` > `STEP2_CLEAN_DIR` > OneDrive
`clean_tables` > `<repo>/data/outputs/clean_tables` > `<repo>/data/interim`. Output
resolves as `--output-dir` > `STEP6_OUTPUT_DIR` > OneDrive `chapter4_outputs` >
`<repo>/data/outputs/chapter4`.

---

## 3. Conventions for every output

- Group labels are always **"Green start-ups"** and **"Other European start-ups"**
  (rule N10). Never "non-green".
- **INVESTED population.** Firm-grain composition tables (T4.18 firm-with-≥1, T4.19,
  T4.21, T4.23 firm-with-≥1) report over firms with `n_investors_lifetime >= 1`.
  A firm with no recorded investor is *unobserved*, not "has no public investor".
- **Relation grain (T4.18, T4.23).** One row per firm x investor link
  (`company_investors_clean` joined to `investors_clean`). Green is attributed by the
  firm join. The relation trio counts links, not firms; the caption states the grain.
- **Deal grain (T4.25).** One row per round (`deals_clean`), green attributed by the
  firm join; the identified-lead flag comes from `deal_investors_clean`. The deal
  trio counts rounds, not firms.
- **N6 — medians primary.** Where a distribution is summarised (median investors per
  round, median distinct investors) the median leads.
- **N8 — accelerator is its own category.** Accelerator/Incubator is never folded
  into VC, in either the investor-type distribution or the flags.
- **R1 — green stage split.** On the headline firm-grain tables (T4.18 firm-with-≥1,
  T4.21, T4.23 firm-with-≥1) green firms are split into Stage 1 (vertical) and
  Stage 2+3 (text) via `green_signal_group`, added as extra columns.
- **T4.22 is descriptive sequencing only.** The caption and text must state that a
  grant preceding VC is a *sequence*, not evidence of causation.
- **T4.23 uses known-country relations only.** Investor country is populated for
  ~77% of investors; the origin shares are computed over relations with a known
  investor country, and the coverage share is reported on the table.
- **Every table reports its own n**, and ends with the uniform sample-size trio
  `n_green`, `n_others`, `n_startups` (same convention as Steps 3-5).

**European classification.** A country counts as European if it appears as an
`hq_country` in the firm table (the population is European start-ups by
construction). Domestic = investor country equals the firm's `hq_country`; European
cross-border = a different but European country; non-European = a known,
non-European country.

**Deferred (like Step 5's R3):**
- **T4.20** (investor composition by green subsegment) — needs the vertical crosswalk;
  `green_signal_group` and vertical tags are present, so it can be added later.
- **T4.24** (non-European participation by stage) — needs the deal x investor country
  join at stage grain; deferred with T4.20.
- **T4.26** (green share of firms vs green share of capital by country) — the
  geography x finance bridge (decision D6); belongs with the Step 4 geography outputs.
- **F4.6 selection (decision D7)** — the main-text choice between the public/private
  sequence figure and the geography figure is a pre-registered editorial decision,
  not a build step.
- **Debt lender-type breakdown** — requires `DealDebtLenderRelation.csv`, a Step 1
  amendment; out of scope until that input is added.

---

## 4. Outputs

All tables are CSV. F4.5 is written as figure *data*; the plotted PDF is a later,
cosmetic step (as with F4.1-F4.4).

### 4.1 `T4_18_investor_type_distribution.csv` — investor type distribution (T4.18)

**Relation grain over INVESTED**, one row per `investor_type_grp`. Two views: the
share of investor *relations* of that type, and the share of *firms* with at least
one investor of that type.

| Column | Meaning |
|---|---|
| `investor_type_grp` | Independent VC, Public/Government, Corporate, PE/Growth, Accelerator/Incubator, Angel, Lender/Debt, Family Office, Impact Investing, Other/Unclassified |
| `green_n_relations` | number of green firms' relations of this type |
| `green_pct_relations` | share of green firms' relations of this type |
| `green_pct_firms` | share of green INVESTED firms with ≥1 investor of this type |
| `other_n_relations`, `other_pct_relations`, `other_pct_firms` | same for other |
| `pp_difference` | `(green_pct_firms - other_pct_firms) * 100` |
| `green_pct_firms_stage1`, `green_pct_firms_stage2plus3` | R1 firm-with-≥1 shares |
| `n_green`, `n_others`, `n_startups` | **relations** of this type (green / other / total) |

The Other/Unclassified relation share is printed in the acceptance report; above
~10% the mapping (spec §V4) should be revisited before drawing conclusions.

### 4.2 `T4_19_investor_flags.csv` — company-level investor flags (T4.19)

**Firm grain over INVESTED.** One row per flag, plus a median-distinct-investors row.

| Column | Meaning |
|---|---|
| `flag` | any_public_investor, any_corporate_investor, any_ivc_investor, any_accelerator_investor, any_lender_investor, median_n_investors |
| `green_stat` | share of green INVESTED firms with the flag (or median count) |
| `other_stat` | same for other |
| `difference` | for share rows `(green - other) * 100` pp; for the median row `green - other` |
| `n_green`, `n_others`, `n_startups` | INVESTED firms (green / other / total) |

### 4.3 `T4_21_public_private.csv` — public and private capital (T4.21)

**Firm grain over INVESTED.** Distinguishes lifetime combination from same-deal
co-investment: a government investment in 2018 and a VC round in 2021 is *not*
co-financing.

| Column | Meaning |
|---|---|
| `measure` | lifetime_combination (`public_private_lifetime`), same_deal_coinvestment (`public_private_same_deal`), ratio_same_deal_to_lifetime |
| `green_pct`, `other_pct` | share of INVESTED firms (ratio row: unitless ratio) |
| `pp_difference` | `(green_pct - other_pct) * 100` (blank on the ratio row) |
| `green_pct_stage1`, `green_pct_stage2plus3` | R1 shares (share rows only) |
| `n_green`, `n_others`, `n_startups` | INVESTED firms with the measure true (ratio row: firm base) |

### 4.4 `T4_22_grant_to_vc.csv` — grant -> VC sequencing (T4.22)

Population: firms with **both** a Grant deal and a VC round. Uses deal dates to
examine order. **Descriptive only.**

| Column | Meaning |
|---|---|
| `measure` | n_firms_grant_and_vc; pct_grant_preceded_vc; median_months_grant_to_vc; pct_vc_backed_with_prior_grant |
| `green_stat`, `other_stat` | value per group |
| `difference` | green - other |
| `n_green`, `n_others`, `n_startups` | firms with both a grant and a VC round (for the last row: VC-backed firms) |

`pct_grant_preceded_vc` = share of grant-and-VC firms whose earliest grant `deal_date`
is strictly before their earliest VC `deal_date`. `median_months_grant_to_vc` is over
those firms where the grant preceded the VC. `pct_vc_backed_with_prior_grant` uses the
firm-level `any_vc` base and asks what share also had a grant that preceded first VC.

### 4.5 `T4_23_investor_origin.csv` — investor origin (T4.23)

**Relation grain over INVESTED, known-country only.** One row per origin category.

| Column | Meaning |
|---|---|
| `origin` | domestic, european_cross_border, non_european |
| `green_pct_relations` | share of green firms' known-country relations in this origin |
| `green_pct_firms` | share of green INVESTED firms with ≥1 such relation |
| `other_pct_relations`, `other_pct_firms` | same for other |
| `pp_difference` | `(green_pct_relations - other_pct_relations) * 100` |
| `green_pct_firms_stage1`, `green_pct_firms_stage2plus3` | R1 firm-with-≥1 shares |
| `country_coverage` | share of relations with a known investor country (same on every row) |
| `n_green`, `n_others`, `n_startups` | **known-country relations** in this origin |

### 4.6 `T4_25_syndication.csv` — syndication (T4.25)

**Deal grain by stage group.** Later rounds naturally carry more investors, so the
comparison is *within* stage group. One block per stage, rows green / other.

| Column | Meaning |
|---|---|
| `stage_group` | deal stage |
| `group` | Green start-ups / Other European start-ups |
| `median_investors` | median `n_investors` per round |
| `pct_multi_investor` | share of rounds with `n_investors >= 2` |
| `median_new_investors` | median `n_new_investors` per round |
| `pct_with_lead` | share of rounds with ≥1 `is_lead == "Yes"` in `deal_investors_clean` |
| `n_green`, `n_others`, `n_startups` | **rounds** at this stage (green / other / total; the row's own group count is on `n_green`/`n_others`) |

### 4.7 `F4_05_investor_participation.csv` — investor participation figure (F4.5)

Figure data for a grouped bar chart: share of firms with ≥1 investor of each type,
green vs other, taken from T4.18.

| Column | Meaning |
|---|---|
| `investor_type_grp` | investor type |
| `green_pct_firms`, `other_pct_firms` | share of INVESTED firms with ≥1 |
| `pp_difference` | `(green - other) * 100` |
| `n_green`, `n_others`, `n_startups` | INVESTED firms (green / other / total) |

---

## 5. Rules that apply throughout

- **INVESTED is the base.** Firm-grain composition is reported over firms with a
  recorded investor; absence of a record is unknown, not "no such investor".
- **Grain is stated.** Relation-grain and deal-grain tables keep the trio names for
  uniformity but the caption says whether n counts relations, rounds, or firms.
- **Public/private is two things.** Lifetime combination and same-deal
  co-investment are never merged into one number.
- **Sequence is not causality (T4.22).** The caption says so explicitly.
- **Known-country only (T4.23).** Origin shares exclude relations with a missing
  investor country; the coverage share is reported.

---

## 6. Acceptance checks

The run prints these at the end. Step 6 is done when they pass.

- [ ] INVESTED subsample = 50,815 (green + other), matching `n_investors_lifetime >= 1`
- [ ] T4.19 flag shares reconcile with the firm-column means over INVESTED
- [ ] T4.18 relation total ≈ `company_investors_clean` links on INVESTED; the
      Other/Unclassified relation share is printed (⚠ if > 10%)
- [ ] T4.22 grant-and-VC firm count = 3,960; every `median_months_grant_to_vc` ≥ 0
- [ ] T4.23 origin shares sum to 1 within each group over known-country relations;
      the coverage share is reported
- [ ] T4.25 is deal grain, reported within stage group
- [ ] every table ends with `n_green`, `n_others`, `n_startups`

## 7. Decisions taken, with defaults

| Decision | Default | Where to change |
|---|---|---|
| INVESTED threshold | `n_investors_lifetime >= 1` | `INVESTED_MIN` in `config.py` |
| Investor type order | Independent VC ... Other/Unclassified | `INVESTOR_TYPE_ORDER` in `config.py` |
| VC stage groups (T4.22) | Angel/Seed, Early-stage VC, Later-stage VC, Growth/PE | `VC_STAGE_GROUPS` in `config.py` |
| Grant stage group | Grant | `GRANT_STAGE_GROUP` in `config.py` |
| European set | firm `hq_country` domain | derived at runtime in `build.py` |
| Multi-investor threshold | `n_investors >= 2` | `MULTI_INVESTOR_MIN` in `config.py` |
| Low-n flag threshold | 30 | `LOW_N_FLAG` in `config.py` |

## 8. Out of scope

- T4.20 (green subsegment x investor type), T4.24 (non-European by stage),
  T4.26 (green share of capital by country) — deferred; see §3.
- F4.6 main-text figure selection (decision D7) — editorial, pre-registered.
- Debt lender-type breakdown — needs `DealDebtLenderRelation.csv` (Step 1 amendment).
- Plotted PDF figures — this step writes figure *data* only.

## 9. How to run it

```bash
# build from the local Step 2 + Step 1 outputs
python -m empirical_analysis.step6_investors.run \
    --firm-table data/outputs/company_analysis.parquet \
    --clean-dir data/outputs/clean_tables \
    --output-dir data/outputs/chapter4

# on the target machine, the OneDrive paths resolve on their own
python -m empirical_analysis.step6_investors.run
```

Tests: `python -m pytest empirical_analysis/step6_investors/tests/ -q`
