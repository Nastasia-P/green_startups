# Chapter 4: Output Register

Companion to `Empirical_Analysis_Specification.md` and `HANDOVER.md`.
Version 1.0, 20 August 2026

Every table and figure Chapter 4 requires. For each: what it shows, its grain, its columns and rows, the source variables (spec §V IDs), the population it runs on, and which robustness rules apply.

**Conventions applying to every output:**
- Group labels are always **"Green start-ups"** and **"Other European start-ups"** (rule N10)
- Every table reports its own **n** per cell or per column
- File naming: `T4_09_funding_access.csv`, `F4_03_lq_by_country.pdf`
- Population column: **Full** = all 116,005 · **Financed** = financed subsample only (rule N1)
- Robustness column: **R1** = split by `green_stage` · **R2** = within founding cohort · **R3** = within industry · **R4** = censoring applies

---

## Summary

| Section | Tables | Figures | Priority |
|---|---|---|---|
| 4.0 Coverage audit | T4.0 | | **Blocking**: validates everything else |
| 4.1 Firm characteristics | T4.1-T4.5 | F4.1 | High |
| 4.1.x Classification validation | T4.5b | | **High, no pipeline dependency** |
| 4.2 Geography | T4.6-T4.8 | F4.2-F4.3 | High |
| 4.3 Funding and investors | T4.9-T4.26 | F4.4-F4.6 | **Highest: the core contribution** |
| Appendix | AP1-AP5 | | As time allows, **except AP5** (see below) |

**Totals:** 29 tables (T4.0-T4.26 numbered, plus T4.5b and the stretch T4.27), 6 figures, 5 appendix items. Not all reach the main text; see §Placement.

⚠️ **Appendix IDs use the `AP` prefix** to avoid collision with the specification's §II.A1-A4 architecture sections. Citations to those architecture sections are always written in full as "spec §II.Ax".

---

## 4.0: Coverage audit

### T4.0 · Field completeness by group
**Purpose:** Establish differential PitchBook coverage before any comparison. Justifies the financed-subsample design (N1). This table is *presented*, not hidden.
**Grain:** one row per field · **Population:** Full · **Robustness:** none

| Column | Content |
|---|---|
| Field | Variable name |
| Green: n non-null | count |
| Green: % | percentage |
| Other: n non-null | count |
| Other: % | percentage |
| Ratio | green % ÷ other % |

**Rows:** year_founded · hq_country · hq_city · employees · employee_history · business_status · primary_sector · total_raised · ≥1 deal record · deal_size · deal_size actual · first_deal_date · investor relation present · investor type matched · investor country matched · revenue · EBITDA

**Known values to reproduce as a correctness check:** TotalRaised 59.3% / 24.2% · FirstFinancingDealType 97.0% / 42.6% · Verticals 91.0% / 36.5% · Employees 82.0% / 49.9%

**Companion:** `T4_00_sample_register.csv` (written by Step 3) documents the population rule, effective n, and rationale for every Chapter 4 statistic.

**Placement:** condensed in main text with the financed-subsample argument; full table in appendix.

---

## 4.1: Firm characteristics

### T4.00 · Sample size register ★
**Purpose:** Documents, for every Chapter 4 statistic, which population was used, the effective n (total / green / other), the inclusion rule, and the rationale (rules N1, N2, R2, etc.). Written on every Step 3 run; covers Step 3 outputs and planned Step 4–6 tables with computed n's from the current firm table.
**Grain:** one row per statistic · **Population:** n/a (meta-table) · **Robustness:** none

| Column | Content |
|---|---|
| section · output_id · output_file · statistic · population · n_total · n_green · n_other · sample_definition · rationale · rule_refs · step · status |

**Placement:** appendix alongside T4.0; cite when interpreting any table whose denominator is not the full 116,005.

### T4.1 · Master descriptive table
**Purpose:** Establish comparability before interpreting geography or finance.
**Grain:** one row per characteristic · **Population:** Full · **Robustness:** R1

| Column | Content |
|---|---|
| Characteristic | row label |
| Green: statistic | median / % / count |
| Green: n | non-null count |
| Other: statistic | |
| Other: n | |
| Difference | pp or ratio |

**Rows:** N firms · median founding year · median age (V1.6) · age Q25/Q75 · cohort shares ×4 (V1.7) · median employees (V1.10) · employee bands ×4 (V1.11) · business status shares (V1.13) · top-5 primary sectors (V1.14) · financing status shares

### T4.2 · Business status distribution
**Purpose:** Tests the long-development-horizon argument from lit review §2.4. If a larger share of green firms remains in development status at comparable age, that helps interpret the financing patterns in §4.3.
**Grain:** one row per status · **Population:** Full · **Robustness:** R1, R2

Columns: Status · Green n · Green % · Other n · Other % · pp difference
Rows: from the actual frequency table: **inspect before grouping** (decision D2). Observed so far: Generating Revenue, Startup, Product Development, Stealth, Profitable, Product In Beta Test, clinical-trial stages.

### T4.3 · Industry composition
**Purpose:** Shows green firms cut across conventional sectors rather than mapping to one industry. Feeds the R3 robustness stratifier.
**Grain:** one row per industry sector · **Source:** `CompanyIndustryRelation` (long format, firms hold multiple tags) · **Population:** Full

Columns: Industry sector · Green n · Green % of green · Other n · Other % of other · LQ within sector
**Note:** percentages sum above 100 because firms carry multiple tags. State this in the caption.

### T4.4 · Green subsegment decomposition
**Purpose:** Decomposes the green population into meaningful subsegments (energy, mobility, circular, food/agri). Makes the capital-intensity heterogeneity argument (Gaddy et al.) testable in T4.20.
**Grain:** one row per vertical · **Source:** `CompanyVerticalRelation` · **Population:** Green only

Columns: Vertical · n firms · % of green population · median age · median total raised · n with funding
**Constraint:** use existing PitchBook verticals. **Do not invent a new subsector taxonomy** (spec §VI).

### T4.5 · Employment by cohort *(optional/secondary)*
**Grain:** cohort × group · **Population:** Full · **Robustness:** R2
Columns: Cohort · Green median employees · Green n · Other median · Other n
**Note:** employment growth from `CompanyEmployeeHistoryRelation` only if coverage proves adequate. Moves toward performance analysis, so keep secondary.

### T4.5b · Classification validation ★
**Purpose:** The only measure of classification *accuracy*. Robustness by `green_stage` tests stability; this tests correctness. Addresses the open note on draft p.22.
**Grain:** one row per stratum · **Population:** hand-coded samples · **No pipeline dependency: can start immediately**

| Column | Content |
|---|---|
| Stratum | Stage 1 vertical / Stage 2 token / Stage 3 phrase / Not identified |
| n sampled | 100 green stratified + 100 not-identified |
| n correct | hand-coded |
| Precision / est. false-negative rate | % |
| 95% CI | binomial |

**Method:** random draw, fixed seed, hand-coded from company descriptions against the Chapter 2 activity-based definition. Document the coding rule in the appendix.

### F4.1 · Green share by founding cohort
**Type:** bar chart, green share per cohort with the 7.2% overall benchmark marked
**Caption must read "cohort composition", not a time trend.** A 2026 snapshot of currently eligible firms is not a historically reconstructed annual population.

---

## 4.2: Geographic distribution

**Denominator rule (N9):** the 116,005 start-up population, never the 6.45m universe.

### T4.6 · Country-level distribution and specialisation ★
**Purpose:** The core geographic result. Separates *size* from *specialisation*.
**Grain:** one row per country · **Population:** Full · **Robustness:** R1 · **Minimum:** none — every country reported (decision D4's ≥500 floor dropped per request; thin cells carry `low_n_flag`)

| Column | Formula |
|---|---|
| Country | |
| Green n | `N_green,c` |
| Total start-ups | `N_startup,c` |
| Share of European green | `N_green,c / N_green,EU` |
| Green intensity | `N_green,c / N_startup,c` |
| Location quotient | `(N_green,c/N_startup,c) / (N_green,EU/N_startup,EU)` |
| LQ, Stage 1 only | R1 split |
| LQ, Stage 2+3 only | R1 split |

**Preliminary values to reproduce:** Finland 2.45 · Spain 2.12 · Switzerland 2.11 · France 1.74 · Poland 1.53 · Austria 1.44 · Germany 1.43 · Ireland 1.39 · UK 1.22 · Denmark 0.90 · Netherlands 0.67 · Belgium 0.56 · Sweden 0.54 · Italy 0.46 · Norway 0.35

This inverts the raw-count ranking: Italy is second on absolute start-up count but among the least green-intensive countries.

### T4.7 · Per-capita cross-check ★ **REQUIRED**
**Purpose:** Not a nicety. Tests whether the T4.6 denominator is contaminated by uneven PitchBook coverage.
**Grain:** one row per country (all 46; **40 matched** to Eurostat, six unmatched shown with NA) · **External input:** Eurostat `demo_pjan`, each country's most recent published vintage

| Column | Formula |
|---|---|
| Country · Population (m) · Start-ups per million · Green per million · Green intensity (from T4.6) · LQ (from T4.6) |

**Why required.** Among the 19 large countries (former ≥500 floor) start-up density spans **29.5 per million (Poland) to 1,904 (Norway)**, a ~65× range no economic story explains, and Spearman(density, green intensity) = **−0.67**: densely covered countries show systematically *lower* green shares, consistent with dense coverage sweeping in small firms never tagged green and diluting the denominator. Across all **40 matched countries** the correlation weakens to **−0.25** (n=40) as thin candidate countries with low density and volatile green intensity enter — so the coverage-dilution signal is strongest exactly where coverage is deepest. Six countries Eurostat does not publish (Russia, Belarus, Bosnia and Herzegovina, Andorra, San Marino, Gibraltar) are retained with NA population.

**Consequence:** the bottom of T4.6 (Norway 0.35, Italy 0.46, Sweden 0.54) cannot be read as low green specialisation without this table. Where LQ and green-per-million disagree, say so explicitly.

### T4.8 · Geographic concentration
**Purpose:** Are green start-ups more spatially concentrated than start-ups generally?
Columns: Measure · Green · Other · Difference
Rows: top-5 country share · top-10 country share · top-5 city share · HHI (optional)

### F4.2 · Green start-up count by country
Bar chart, absolute scale. Shows size.

### F4.3 · Location quotient by country ★
Choropleth or ranked bar with LQ = 1 marked. Shows specialisation. **The headline geographic figure.**

---

## 4.3: Funding and investor patterns

Structure: **Access → Amount → Timing/Stage → Source of capital**. The chapter's largest and most important section.

### 4.3A: Access

### T4.9 · Access to finance ★
**Purpose:** The extensive margin. Directly comparable to Dechezleprêtre & Kelly (2025), who find green firms more likely to receive VC and grants but less likely at seed.
**Grain:** one row per financing type · **Population:** Full · **Robustness:** R1, R2, **R3**

| Column | Content |
|---|---|
| Financing type · Green % · Green n · Other % · Other n · pp difference · Stage 1 % · Stage 2+3 % |

**Rows:** any financing (V1.20) · any VC (V1.21) · any grant (V1.22) · any debt (V1.23) · any accelerator (V1.24) · any growth/PE (V1.25) · any crowdfunding (V1.26)

⚠️ **Rule N2:** `financed` = ≥1 completed qualifying deal, never `total_raised > 0`.
⚠️ **Rule N8:** accelerator reported separately, never folded into VC or seed.

### 4.3B: Amount

### T4.10 · Total raised by cohort ★
**Purpose:** The amount comparison, correctly adjusted. A 2017 firm has had eight years to raise; a 2025 firm one.
**Grain:** cohort × group · **Population:** Financed · **Robustness:** R1, R2 (mandatory), **R3**

Columns: Cohort · Green n · Green median · Green Q25 · Green Q75 · Green mean · Green P90 · then the same six for Other · median ratio

### T4.11 · First financing size by stage
**Grain:** stage_group × group · **Population:** Financed
Columns: Stage group · Green n · Green median · Green IQR · Other n · Other median · Other IQR
**Also report:** share of sizes marked Estimated rather than Actual (spec §V2.7).

### T4.12 · Post-money valuation *(coverage permitting)*
**Population:** Financed with valuation. Report n prominently: coverage is low.

### 4.3C: Timing

### T4.13 · Time to first financing ★
**Purpose:** Likely the chapter's most publishable single result. Literature suggests green firms may be *more* likely to obtain some capital but *slower* to obtain VC. The two measures must be reported separately.
**Grain:** measure × group · **Population:** Financed · **Robustness:** R1, R2, **R3**, R4

Columns: Measure · Green n · Green median years · Green Q25/Q75 · Other n · Other median · Other Q25/Q75 · difference
Rows: years to first financing (V1.31) · years to first VC (V1.32) · by cohort for each

⚠️ Year-only precision (`YearFounded` has no month). Negative lags flagged and excluded.

### F4.4 · Cumulative share financed by years since founding
Two curves, green and other, with censoring per R4. Consider a third and fourth curve for first-VC.

### 4.3D: Stage and trajectory

### T4.14 · First financing type composition
Grain: deal type × group · Population: Financed · Robustness: R1
Columns: Stage group · Green n · Green % · Other n · Other % · pp difference

### T4.15 · Deal stage composition (all rounds)
Grain: stage_group × group · Population: `deal_analysis`
⚠️ Deal-level grain. Do not join investors before aggregating (spec §II.A3).

### T4.16 · Median deal size by stage
Grain: stage_group × group · Population: deals with recorded size
Columns: Stage group · Green n deals · Green median · Other n deals · Other median · ratio

### T4.17 · Financing trajectories
Grain: measure × group · Population: Financed · Robustness: R2, R4
Rows: median rounds per firm · % with ≥2 rounds · median months between round 1 and 2 · % progressing seed→early VC · % progressing early→later VC
⚠️ Censoring: only firms whose first round is old enough to have permitted a follow-on.

### 4.3E: Investor composition

### T4.18 · Investor type distribution ★
**Purpose:** Answers the "by whom" half of the research question, using PitchBook's own classification rather than a hand-built matcher.
**Grain:** investor_type_grp × group · **Population:** firms with investor records · **Robustness:** R1

Columns: Investor type group · Green: n investors · Green: % of investor relations · Green: % of firms with ≥1 · Other: same three · pp difference
Rows: Independent VC · Public/Government · Corporate · PE/Growth · Accelerator/Incubator · Angel · Lender/Debt · Other/Unclassified

⚠️ **Report the unclassified share.** Above ~10%, revisit the §V4 mapping before drawing conclusions.

### T4.19 · Company-level investor flags
Grain: flag × group · Population: firms with investor records
Rows: any public investor (V1.34) · any corporate (V1.35) · any independent VC (V1.36) · any accelerator (V1.37) · any lender/debt provider (V1.37b) · median distinct investors (V1.33)

### T4.20 · Investor composition by green subsegment
Grain: vertical × investor_type_grp · Population: Green only
Links to T4.4. Tests whether capital-intensive green segments attract different investor types.

### 4.3F: Public-private interaction

### T4.21 · Public and private capital ★
**Purpose:** Distinguishes two things routinely conflated. A government investment in 2018 and a VC round in 2021 is *not* co-financing.
**Grain:** measure × group · **Population:** firms with investor records

Rows: **lifetime combination**: ever received both public and private (V1.38) · **same-deal co-investment**: ≥1 DealID containing both (V1.39) · ratio of the two
Columns: Green % · Green n · Other % · Other n · pp difference

### T4.22 · Grant → VC sequencing ★
**Purpose:** Tests the Islam et al. (2018) public-signalling pattern on European data. Prior work notes the correlation; deal-level dates let you examine the *sequence*.
**Grain:** measure × group · **Population:** firms with both a grant and a VC round

Rows: n firms with both · % where grant preceded VC · median months grant→VC · % of VC-backed firms with a prior grant
Columns: Green · Other · difference

⚠️ **Descriptive sequencing only.** Caption and text must state that sequence is not causality.

### 4.3G: Investor geography

### T4.23 · Investor origin ★
**Purpose:** Connects Chapter 4 to the Draghi framing in the introduction on European fragmentation and capital failing to scale across borders.
**Grain:** origin category × group · **Population:** firms with investor records with known country

Rows: domestic (investor country = company country) · European cross-border · non-European
Columns: Green % of relations · Green % of firms with ≥1 · Other % of relations · Other % of firms with ≥1 · pp difference

**Note:** if this becomes interpretive rather than purely descriptive, add peer-reviewed cross-border VC literature to Chapter 2 rather than inventing theoretical claims.

### T4.24 · Non-European participation by stage
Grain: stage_group × group · Rows by stage, columns show % of rounds with ≥1 non-European (and specifically US) investor.

### F4.5 · Investor type participation
Grouped bar, green vs other, by investor_type_grp.

### F4.6 · Public/private sequence or investor geography
One only in the main text. **Select on coverage adequacy, pre-specified before results are inspected (decision D7).** Do not select on which produces the stronger finding: that conflicts with §P1 and §P5.

### 4.3H: Syndication *(secondary)*

### T4.25 · Syndication
Grain: stage_group × group · Population: `deal_analysis`
Rows: median investors per round · % multi-investor rounds · median new investors · % rounds with an identified lead
⚠️ **Within stage group.** Later rounds naturally carry more investors; if green firms skew later-stage, an unconditional comparison misleads.

### 4.3I: Geography × finance bridge

### T4.26 · Green share of firms vs green share of capital
**Purpose:** Bridges 4.2 and 4.3. A country with 10% green firms receiving 25% of recorded capital tells a very different story from the reverse.
**Grain:** one row per country · **Population:** Financed · **Minimum:** adequate n and funding coverage (decision D6)

Columns: Country · green % of start-ups · green % of recorded capital · ratio · n green financed · funding coverage %
⚠️ Caveat in caption: a 2026 snapshot, not a complete historical investment-flow series.

---

## Appendix outputs

| ID | Content |
|---|---|
| **AP1** | Full coverage audit (extended T4.0) |
| **AP2** | City-level ranking: count, share of European green, intensity. Minimum 100 start-ups |
| **AP3** | Full financing stage taxonomy: every `DealType` mapped to its `stage_group`, with counts |
| **AP4** | Full investor type mapping: every `PrimaryInvestorType` mapped to its `investor_type_grp`, with counts |
| **AP5** | Classification validation coding rules and the sampled firms. **High priority: inherits T4.5b's status, since it is that table's documentation** |
| **T4.27** | *(stretch, decision D5)* NUTS-2 regional distribution: only with reliable city-to-NUTS mapping |

---

## Placement

**Main text (target ~15-17 exhibits):**
4.0: **T4.0 (condensed)**: required in main text per spec §P4/M3, not the appendix
4.1: T4.1, T4.2, T4.5b, F4.1
4.2: T4.6, T4.7, F4.3
4.3: T4.9, T4.10, T4.13, T4.18, T4.21, T4.22, T4.23, F4.4, F4.5 or F4.6 (per decision D7)

**Appendix:** everything else, plus AP1-AP5.

★ marks the outputs carrying the chapter's argument. If time compresses, these are the last to be cut.

---

## Build order

Broadly follows spec §IX, with two deliberate deviations noted below.

| Order | Outputs | Depends on |
|---|---|---|
| 1 | T4.0 | Phase 1 |
| 2 | T4.1, T4.2, F4.1 | Phase 1 |
| 3 | T4.6, T4.7, F4.2, F4.3 | Phase 1 + Eurostat |
| 4 | T4.9 | Phase 0 deals |
| 5 | T4.10, T4.11, **T4.12** | Phase 0 deals |
| 6 | T4.13, T4.14, F4.4 | Phase 0 deals |
| 7 | T4.18, T4.19, F4.5 | Phase 0 investors |
| 8 | T4.21, T4.22 | Phase 0 deals + investors |
| 9 | T4.23, T4.24, F4.6 | Phase 0 investors |
| 10 | T4.3, T4.4, T4.8, T4.15-T4.17, T4.20 | various |
| 11 | T4.5, T4.25, T4.26 | various |
| 12 | AP1-AP4, T4.27 (stretch) | all |

**Deviations from spec §IX:** stage-composition tables T4.15-T4.17 are deferred to order 10 (spec §IX bundles stage with timing at item 6), and public/private interaction is split across orders 7-8 (spec §IX bundles it with investor composition at item 7). Both are sequencing conveniences and change no result.

**T4.5b and AP5 run in parallel throughout**: they need no pipeline output.
