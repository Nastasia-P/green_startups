# Step 1 — Clean the raw data

Self-contained specification. Everything needed to understand, run, or rebuild this
step is in this document; no other file needs to be open.

**Implemented by:** `empirical_analysis/step1_clean_raw_data/`
**Run with:** `python -m empirical_analysis.step1_clean_raw_data.run --mode full`

---

## 1. Purpose

The raw PitchBook extract is 43 CSV files covering the whole world, tens of millions of
rows, and every kind of transaction — including ones that are not financing at all.
None of it can be analysed directly.

Step 1 reads those files once and writes a small set of clean tables that contain only:

1. the **116,005 start-ups** in the study population, and
2. **genuine financing events** (completed, correctly dated, actually new capital).

Doing this once, and saving the result, is what makes every later step fast, consistent
and reproducible. Later steps never touch the raw files again.

**Step 1 does not aggregate to firm level.** Turning "many deals" into "one row per firm"
is Step 2. Keeping that separation is what prevents the most damaging bug available in
this dataset (see §7).

---

## 2. Inputs

### 2.1 The raw extract

A directory of raw PitchBook CSVs (on the target machine: `...\02_Data\esade_20260707`).
Of the 43 files, Step 1 reads seven:

| File | What it holds | Grain |
|---|---|---|
| `Deal.csv` | every financing transaction | 1 row per deal |
| `DealInvestorRelation.csv` | who participated in each deal | 1 row per deal x investor |
| `CompanyInvestorRelation.csv` | firm-investor relationships over time | 1 row per firm x investor |
| `Investor.csv` | investor identity, type, country | 1 row per investor |
| `CompanyIndustryRelation.csv` | industry tags | 1 row per firm x industry |
| `CompanyVerticalRelation.csv` | vertical tags (green subsegments) | 1 row per firm x vertical |
| `CompanyEmployeeHistoryRelation.csv` | headcount over time | 1 row per firm x date |

The directory is found in this order (first match wins), and `--extract-dir` overrides all:

1. environment variable `PITCHBOOK_EXTRACT_DIR`
2. the target machine's OneDrive `...\02_Data\esade_20260707`
3. `<repo>/data/raw`

### 2.2 The population

The 116,005 start-ups with their green flag, taken from the Chapter 3 outputs:

- `startups_stages_filtered.csv` — the merged company spine
- the green classification ledger — supplies `Green` and `GreenStage`

The population is fixed upstream. Step 1 never re-derives it; it only reads it and uses
it as a filter. Override the ledger with `--ledger`.

---

## 3. The four filters

These are the only filters Step 1 applies. Each is logged with rows in and rows out.

| # | Filter | Rule | Why |
|---|---|---|---|
| 1 | **Population** | `CompanyID` must be one of the 116,005 study firms | The raw tables are global; everything else is out of scope |
| 2 | **Completed** | `DealStatus == "Completed"` | Drops *Announced / In Progress* and *Failed / Cancelled*. Announced deals may never close |
| 3 | **Valid date** | `DealDate` must parse and fall on or before **2026-07-07** (the extract date) | Removes missing and forward-dated errors |
| 4 | **Real financing** | `DealType` must NOT be one of: `IPO`, `Merger/Acquisition`, `Share Repurchase`, `Out of Business`; and must NOT start with `Secondary Transaction` or `Bankruptcy` | These are not new capital going into the firm |

**Prefix matching note.** PitchBook writes suffixed variants such as
`Secondary Transaction - Open Market` and `Bankruptcy: Admin/Reorg`. Matching those two
families on exact strings alone lets the variants through as if they were financing, which
inflates deal counts and every funding total downstream. They are matched by prefix.

**Date parsing note.** Dates are tried as `MM/DD/YYYY` first, then re-tried with automatic
format detection for anything that failed. Without that fallback, a differently formatted
`Deal.csv` silently loses every row at filter 3 and all downstream counts read zero.

---

## 4. Outputs

All tables are written as **Parquet** (requires `pyarrow`). Reference lists and the audit
are written as CSV so they can be opened in Excel.

Destination, in order (first match wins); `--output-dir` overrides all:

1. environment variable `STEP1_OUTPUT_DIR`
2. the target machine's OneDrive `...\09_Python_Empirical Analysis\clean_tables`
3. `<repo>/data/interim`

### 4.1 `population_key.parquet` — 1 row per firm

| Column | Meaning |
|---|---|
| `company_id` | firm key |
| `green` | 1 if identified green, else 0 |
| `green_stage` | `vertical` / `token` / `phrase` / `none` |
| `green_signal_group` | `Stage 1` (vertical) / `Stage 2+3` (token or phrase) / `none` |

### 4.2 `deals_clean.parquet` — 1 row per deal

All four filters applied.

| Column | Meaning |
|---|---|
| `company_id`, `deal_id` | keys |
| `deal_date` | parsed date |
| `deal_type`, `deal_type_2`, `deal_class` | PitchBook's own classification |
| `stage_group` | derived grouping (see §5.1) |
| `deal_size` | round size, USD millions (may be missing) |
| `size_is_actual` | 1 if the size is Actual, 0 if Estimated |
| `deal_no`, `vc_round` | round sequence |
| `post_valuation` | post-money valuation (low coverage) |
| `n_investors`, `n_new_investors` | participant counts as recorded on the deal |
| `is_first_deal` | 1 if this is the firm's earliest qualifying deal |

### 4.3 `deal_investors_clean.parquet` — 1 row per deal x investor

Limited to deals that survived the filters, and to financing roles only:
`InvestorStatus` in {`New Investor`, `Shareholder`}.

Columns: `deal_id`, `investor_id`, `investor_name`, `investor_status`, `is_lead`.

### 4.4 `company_investors_clean.parquet` — 1 row per firm x investor

Limited to the population. All historical investors are kept **except** the
non-financing roles `Acquirer` and `Add-on Sponsor`.

Columns: `company_id`, `investor_id`, `investor_name`, `investor_status`, `holding`,
`investor_since`.

### 4.5 `investors_clean.parquet` — 1 row per investor

Only investors actually referenced by the two tables above (a two-pass read: collect the
investor IDs first, then read only those rows out of the global investor file).

Columns: `investor_id`, `investor_name`, `primary_investor_type`, `other_investor_types`,
`investor_type_grp` (see §5.2), `investor_country`.

### 4.6 Relational tables — filtered to the population, long format

| File | Columns |
|---|---|
| `industries_clean.parquet` | `company_id`, `is_primary`, `industry_sector`, `industry_group`, `industry_code` |
| `verticals_clean.parquet` | `company_id`, `vertical` |
| `employee_history_clean.parquet` | `company_id`, `employee_count`, `date` |

---

## 5. The two groupings, written out in full

Both are applied in Step 1 so every later step uses identical definitions.

### 5.1 Deal type to stage group

| `stage_group` | `DealType` values |
|---|---|
| Grant | Grant |
| Accelerator/Incubator | Accelerator/Incubator |
| Angel/Seed | Seed Round; Angel (individual); Restart - Angel |
| Early-stage VC | Early Stage VC; Restart - Early VC |
| Later-stage VC | Later Stage VC; Restart - Later VC |
| Growth/PE | PE Growth/Expansion; Buyout/LBO; Mezzanine; GP Stakes; Leveraged Recap(italization); Dividend Recap(italization) |
| Debt | Debt - General; Debt - Acquisition; Debt - Spinoff; Debt - PPP; Debt - Merger; Debt Refinancing; Debt Repayment; Convertible Debt; Vendor Loan; Bridge; Sale-Lease back (facility) |
| Crowdfunding | Equity Crowdfunding; Product Crowdfunding (plus anything containing "Crowdfunding") |
| Spin-out/Corporate | University Spin-Out; Spin-Off; Corporate; Joint Venture; Platform Creation; Corporate Asset Purchase |
| Other | Project Financing; Capitalization; Capital Spending; Working Capital; General Corporate Purpose; Continuation Fund (Transaction); PIPE; Reverse Merger; Merger of Equals; Debt Conversion; Investor Buyout by Mgmt/Management |
| *(removed by filter 4)* | IPO; Merger/Acquisition; Share Repurchase; Out of Business; anything starting with Secondary Transaction or Bankruptcy |

`Bridge` is grouped with **Debt**: in this extract it denotes a bridge loan rather than an
equity bridge round.

Anything not on this list is labelled `Unmapped` and reported, never silently absorbed
into "Other".

**Accelerator/Incubator is kept as its own group.** It is the single largest deal type and
frequently involves no capital at all, so folding it into VC or seed would distort every
funding comparison.

### 5.2 Investor type to investor group

| `investor_type_grp` | `PrimaryInvestorType` values |
|---|---|
| Independent VC | Venture Capital |
| Public/Government | Government; Not-For-Profit Venture Capital; University; Sovereign Wealth Fund; SBIC |
| Corporate | Corporation; Corporate Venture Capital; PE-Backed Company; VC-Backed Company; Holding Company; Corporate Development |
| PE/Growth | PE/Buyout; Growth/Expansion; Infrastructure; Mezzanine; Other Private Equity; Fundless Sponsor; Merchant Banking Firm; Secondary Buyer; Real Estate |
| Accelerator/Incubator | Accelerator/Incubator |
| Angel | Individual; Angel Group; Angel (individual) |
| Family Office | Family Office |
| Impact Investing | Impact Investing |
| Lender/Debt | Lender/Debt Provider; Commercial Bank; Investment Bank; Business Development Company; Leasing |
| Other/Unclassified | Asset Manager; Hedge Fund; Mutual Fund; Fund of Funds; Limited Partner; SPAC; Other; and anything unlisted |

**Family Office and Impact Investing are their own groups.** Family offices deploy at a
different scale from individual angels, and impact investors are directly relevant to the
green question, so both would lose their meaning if absorbed into a broader bucket.

**`SBIC` is placed under Public/Government** because the government-backed leverage is its
defining feature here, though the funds are privately managed. Reclassify in `config.py` if
you prefer to treat it as a private lender.

---

## 6. Reference lists and the integrity audit

Both groupings above were drafted from indicative data. Step 1 checks them against what
is actually in the extract and reports the result.

### 6.1 `deal_types_seen.csv`
Every `DealType` present, with: `n_rows`, the `stage_group` it mapped to, `is_mapped`,
`excluded_by_filter`, and `n_kept` (how many survived the filters). Any row with
`is_mapped = False` must be classified deliberately before moving on.

### 6.2 `investor_types_seen.csv`
Every `PrimaryInvestorType` present, with `n_investors`, the group it mapped to, and
`is_mapped`. The run also prints the **unclassified share**; above 10% the mapping needs
revisiting before any investor result is trusted.

### 6.3 `cleaning_audit.csv`
One row per table: `rows_in` (before filtering), `rows_out`, `distinct_companies`,
`match_rate` (distinct firms as a share of 116,005), and a `note`. Any table matching
under **30%** of the population is flagged. This is the safety net that catches a join
quietly failing — for example a key-format mismatch that drops every row.

---

## 7. Rules that apply throughout

- **Missing is "unknown", never "zero".** A firm with no deal record has *unobserved*
  funding, not zero funding. Nothing is filled in with 0.
- **Every table stays at its own grain; nothing is merged into one wide table.** A
  20 million round with six investors, merged before aggregation, becomes 120 million.
  All aggregation happens in Step 2, after each table has been reduced to firm level.
- **Cumulative fields are never summed.** `RaisedToDate` and `TotalInvestedCapital` are
  cumulative-to-date; they are point-in-time values only.
- **Big files are read in chunks** (400,000 rows) with only the needed columns, so memory
  stays bounded regardless of file size.

---

## 8. Acceptance checks

The run prints these at the end. Step 1 is done when they pass.

- [ ] `population_key` has **116,005** rows; `green` sums to **8,306**; green stages are
      **6,636 / 834 / 836**
- [ ] The deal filter funnel is printed and no single filter removes an implausible share
- [ ] Firms with at least one qualifying deal is within ~10% of the count of non-null
      `FirstFinancingDealID` in the company file (confirms nothing was silently dropped)
- [ ] No table matches under ~30% of the population without a written explanation
- [ ] `deal_types_seen.csv` and `investor_types_seen.csv` exist, and every value is either
      mapped or explicitly flagged
- [ ] Unclassified investor share is below 10%

Note: on a machine whose ledger is not the final Chapter 3 population, the green count
warning will fire. That is a data-selection difference, not a code fault — check which
ledger is being read before acting on it.

---

## 9. Decisions taken, with defaults

These are choices, not facts. They are recorded here so they can be changed deliberately
and written up in the thesis.

| Decision | Default | Where to change |
|---|---|---|
| Which investors count as a firm's lifetime investors | all historical, excluding `Acquirer` and `Add-on Sponsor` | `COMPANY_INVESTOR_STATUS_DROP` in `config.py` |
| Which deal participants count | `New Investor` and `Shareholder` only | `DEAL_INVESTOR_STATUS_KEEP` in `config.py` |
| Extract cut-off date | 2026-07-07 | `EXTRACT_DATE` in `config.py` |
| Low-match warning threshold | 30% | `MIN_MATCH_RATE` in `config.py` |

---

## 10. Out of scope

- Firm-level aggregation (`total_raised`, `n_deals`, `financed`, investor flags) — Step 2.
- Any thesis table or figure — Steps 3 onward.
- Re-deriving the population or the green classification — fixed by Chapter 3.

---

## 11. How to run it

```bash
pip install -r empirical_analysis/requirements.txt

# smoke test, no raw extract needed
python -m empirical_analysis.step1_clean_raw_data.run --mode fixture

# the real run on the target machine
python -m empirical_analysis.step1_clean_raw_data.run --mode full

# explicit paths if the defaults do not resolve
python -m empirical_analysis.step1_clean_raw_data.run --mode full \
    --extract-dir "D:\path\to\esade_20260707" \
    --output-dir  "D:\path\to\clean_tables"
```

Full mode prints the resolved extract directory, confirms all seven required files are
present, and logs per-table row counts before and after filtering.

Tests: `python -m pytest empirical_analysis/step1_clean_raw_data/tests/ -q`
