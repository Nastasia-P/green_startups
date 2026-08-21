# T4.0 · Implementation Tracker

## Status: in progress (fixture mode working; full extract pending)

Code lives in `empirical_analysis/chapter4/` (`config.py`, `data_sources.py`,
`coverage_audit.py`, `run.py`, `tests/`). Run with the `python/3.12.13-aocl5.3`
module: `python -m empirical_analysis.chapter4.run --mode fixture`.

### Checklist

- [x] Company spine available (`startups_stages_filtered.csv`, 116,005 firms)
- [x] `population_key` built from strong_terms ledger (green / green_stage)
- [x] `coverage_audit.py` implemented per `design.md`
- [x] Smoke test on `preview_summary.csv` passes (runs + schema) (design.md §3.11) - 4/4 pytest
- [x] `T4_00_field_completeness.csv` exported (17 rows)
- [x] `T4_00_field_completeness_full.csv` exported (17 rows + §P4 validation anchors)
- [ ] Full 43-table extract wired (`--mode full --extract-dir ...`) for deal/investor rows
- [ ] Acceptance gates (§3.8) run on full extract (separate from smoke test)
- [ ] Condensed main-text extract drafted
- [ ] Financed-subsample size recorded (overall / by group / by stage)

### Blockers

- Full 43-table PitchBook extract not committed (HANDOVER §2.3); deal- and
  investor-side rows (9-15) are 0 in fixture mode until the extract dir is set.

### Session notes

- Company-level rows already reproduce the spec §P4 anchors within ~1pp on the
  strong_terms grouping (green=8,698): total_raised 59.3/24.1, FirstFinancingDealType
  97.0/42.4, Verticals 91.1/36.3, employees 82.1/49.7, FirstFinancingDate 70.7/32.4,
  ActiveInvestors 89.8/38.8.
- Ledger is strong_terms (green=8,698), not the spec's 8,306; acceptance report
  warns on the mismatch rather than failing (decision per user).
