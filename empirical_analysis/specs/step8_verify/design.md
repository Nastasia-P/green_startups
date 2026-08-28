# Step 8 — Verification

Self-contained specification. Everything needed to understand, run, or rebuild this
step is in this document; no other file needs to be open.

**Implements:** spec Phase 5 (verification) — cross-table reconciliation
**Implemented by:** `empirical_analysis/step8_verify/`
**Run with:** `python -m empirical_analysis.step8_verify.run`

---

## 1. Purpose

Verification is distinct from robustness. Robustness (R1-R4) asks whether a finding
survives a different sample; **verification asks whether the reported number is
correct**. Step 8 reconciles counts and shares across every Chapter 4 output so that
no two tables contradict each other and no headline rests on an unflagged tiny cell.

It adds **no new analytical numbers**. It re-runs the earlier steps, checks internal
consistency, and records the result.

**Approach (two decisions taken):**

- **Source of truth = re-run.** Step 8 loads the Step 2 firm table and the Step 1
  clean tables, then calls each reporting step's `build_all` in-memory
  (`step3_firm_characteristics`, `step4_geography`, `step5_funding`,
  `step6_investors`, `step7_geo_finance` including its by-country block). All checks
  run over those freshly built tables, so the step is self-contained and always
  runnable without depending on files left by a previous run.
- **Stale-file guard.** For each output CSV that exists in the output directory, Step 8
  reads it and compares it to the corresponding re-run table. A divergence is reported
  as `STALE` (a warning): the on-disk file predates the current code or data. It is not
  a `FAIL`, because a stale artifact is a rebuild issue, not a contradiction in the
  numbers.

**Scope = structural only.** Counts and totals reconcile, shares sum to 1 where they
should, medians lie inside their quartiles, low-n rows are flagged, deal/relation
totals match their sources, and no investor-level join inflated a company- or
deal-level count. The two heavier Phase 5 items are **deferred** (see §8): the
end-to-end trace of ~10 firms (5.3) and the Stage 2+3 re-run of headline results (5.6,
which R1 columns on the Step 3-7 tables already carry).

---

## 2. Inputs

| Input | Grain | Used for |
|---|---|---|
| `company_analysis.parquet` (Step 2) | 1 per firm | population / subsample anchors; the re-run input |
| `deals_clean.parquet` (Step 1) | 1 per deal | deal-total reconciliation; re-run input |
| `company_investors_clean.parquet` (Step 1) | 1 per firm x investor | relation-total and double-counting checks; re-run input |
| `investors_clean.parquet` (Step 1) | 1 per investor | re-run input (T4.18/T4.23/T4.28) |
| `deal_investors_clean.parquet` (Step 1) | 1 per deal x investor | re-run input (T4.25) |
| `industries_clean.parquet`, `verticals_clean.parquet` (Step 1) | relation | re-run input (Step 3) |
| `worldbank_population.csv` | 1 per country | re-run input (Step 4 T4.7); avoids false STALE on T4.07 |
| output CSVs in the output dir | — | the stale-file comparison |

Path resolution copies Step 7; `--firm-table` overrides and accepts either the Parquet
file or the Step 2 output directory:

1. environment variable `STEP8_FIRM_TABLE`
2. the target machine's OneDrive `...\09_Python_Empirical Analysis\company_analysis.parquet`
3. `<repo>/data/outputs/company_analysis.parquet`

Clean tables: `--clean-dir` > `STEP2_CLEAN_DIR` > OneDrive `clean_tables` >
`<repo>/data/outputs/clean_tables` > `<repo>/data/interim`. Output: `--output-dir` >
`STEP8_OUTPUT_DIR` > OneDrive `chapter4_outputs` > `<repo>/data/outputs/chapter4`.

---

## 3. Checks

Every check produces one row in the reconciliation table with a `status` of `PASS`,
`WARN`, or `FAIL`. Anchors and tolerances live in `config.py`
(`SHARE_TOL = 1e-2` because shares are rounded to 4dp over up to ~11 rows;
`REL_TOL = 1e-6` for value equality; count checks are exact).

| Category | Check | Phase 5 | Pass rule |
|---|---|---|---|
| population | firm rows / green / other | 5.1 | rows = 116,005; green = 8,306; other = 107,699 |
| population | green by `green_stage` | 5.1 | the three stage counts sum to 8,306 (= 6,636 / 834 / 836 when `green_stage` present; WARN if the column is absent) |
| population | financed / INVESTED / grant-and-VC | 5.1 | `financed==1` = 47,714; `n_investors_lifetime>=1` = 50,815; `any_grant & any_vc` = 3,960 |
| trio_identity | `n_green + n_others == n_startups` | 5.1 | holds on every re-run table carrying the trio |
| shares_sum | T4.14 / T4.15 stage shares | 5.2 | `green_pct` (and `other_pct` where present) sum to 1 within `SHARE_TOL` |
| shares_sum | T4.18 relation shares; T4.23 origin shares | 5.2 | each group's shares sum to 1 |
| shares_sum | T4.28 origin per country; T4.29 amounts | 5.2 | per-country group shares sum to 1; `green_amount + other_amount == total_amount`; `green_amount_share` in [0,1] |
| median_in_iqr | T4.10 / T4.11 / T4.13 | 5.2 | `q25 <= median <= q75` (green and other) wherever all three are non-NA |
| low_n_flag | flag integrity | 5.5 | on every table with `low_n_flag` and `n_green`, `(n_green < 30) == (low_n_flag == 1)`; the country/headline tables carry a `low_n_flag` column |
| source_totals | T4.15 vs `deals_clean` | 5.1/5.4 | `n_startups` sum = 116,505 |
| source_totals | T4.18 vs `company_investors_clean` | 5.1 | relation total = links on INVESTED firms |
| source_totals | T4.29 vs disclosed `deal_size` | 5.1 | `total_amount` sum = summed disclosed `deal_size` |
| source_totals | T4.6 / T4.26 population | 5.1 | `n_startups` sum = 116,005; T4.6 `n_green` sum = 8,306; T4.26 `green_firm_share == round(n_green/n_startups, 4)` per row |
| double_counting | INVESTED base | 5.7 / A3 | INVESTED firm count = distinct `company_id` with a link in `company_investors_clean` (firm grain, not relation grain) |
| double_counting | T4.26 capital grain | 5.7 / A3 | T4.26 green `total_raised` share matches the firm-level green `total_raised` sum / all (no deal multiplication) |
| stale_files | on-disk CSV vs re-run | — | each present CSV equals its re-run table within tolerance; otherwise `STALE` (WARN) |

---

## 4. Output

`step8_reconciliation.csv`, one row per check:

| Column | Meaning |
|---|---|
| `check_id` | stable identifier (e.g. `population.firm_rows`, `shares_sum.t4_23`) |
| `category` | population / trio_identity / shares_sum / median_in_iqr / low_n_flag / source_totals / double_counting / stale_files |
| `description` | human-readable statement of what was checked |
| `expected` | the anchor or invariant |
| `observed` | what the re-run produced |
| `status` | PASS / WARN / FAIL |
| `detail` | extra context (the offending table/row/column when not PASS) |

The run prints a summary (counts of PASS / WARN / FAIL and each non-PASS line). No
other file is written; verification produces the reconciliation table only.

---

## 5. Rules

- **No new numbers.** Step 8 imports the other steps' `build` modules and re-runs them;
  it computes no new per-firm variable (spec Phase 5).
- **Re-run is authoritative.** Checks run over the in-memory re-run, so they always
  have a value to test even on a clean checkout.
- **Stale is a warning.** A mismatch between an on-disk CSV and the re-run means the
  file should be regenerated; a contradiction *among* the re-run tables is a `FAIL`.
- **Anchors are green=8,306.** The committed `population_key` and the thesis anchor are
  8,306, not the local strong-terms ledger's 8,698 (ROADMAP open item 1).

---

## 6. Acceptance checks

The run prints these at the end. Step 8 is done when they pass.

- [ ] population, subsample, trio-identity, shares-sum, median-in-IQR, low-n-flag,
      source-total and double-counting checks all `PASS` on the current firm table
- [ ] the reconciliation CSV is written with one row per check and a PASS/WARN/FAIL
      status
- [ ] `--strict` returns a non-zero exit code if any check is `FAIL`
- [ ] stale on-disk outputs (if any) are surfaced as `STALE`, not silently ignored

## 7. Decisions taken, with defaults

| Decision | Default | Where to change |
|---|---|---|
| Source of numbers | re-run Steps 3-7 in-memory | `build.py` |
| On-disk verification | compare present CSVs, WARN on mismatch | `checks.py` (`stale_files`) |
| Scope | structural only | this spec / `checks.py` |
| Share tolerance | 1e-2 | `SHARE_TOL` in `config.py` |
| Value tolerance | 1e-6 | `REL_TOL` in `config.py` |
| Strict exit | off (returns 0) | `--strict` on `run.py` |

## 8. Out of scope (deferred)

- **5.3 end-to-end trace of ~10 firms** (raw table -> final statistic) — a manual/audit
  task; not automated here.
- **5.6 Stage 2+3 re-run of headline results** — the R1 stage-split columns already on
  the Step 3-7 tables cover this; Step 8 does not recompute them.
- Plotted figures and any new analytical output.

## 9. How to run it

```bash
# self-contained: re-runs Steps 3-7 and reconciles
python -m empirical_analysis.step8_verify.run \
    --firm-table data/outputs/company_analysis.parquet \
    --clean-dir data/outputs/clean_tables \
    --output-dir data/outputs/chapter4

# fail the process if any check FAILs (for CI)
python -m empirical_analysis.step8_verify.run --strict
```

Tests: `python -m pytest empirical_analysis/step8_verify/tests/ -q`
