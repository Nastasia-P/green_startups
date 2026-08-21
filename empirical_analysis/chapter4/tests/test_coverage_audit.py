"""Smoke test for the T4.0 coverage audit on the preview_summary.csv fixture.

Validates that the pipeline runs and the output conforms to the design §3.3
schema. It does NOT assert the §3.8 coverage anchors: those require the full
43-table extract (spec §3.11 / decision D-T4.0-8).
"""

from __future__ import annotations

import pandas as pd

from empirical_analysis.chapter4 import config
from empirical_analysis.chapter4.coverage_audit import (
    SCHEMA,
    build_coverage_audit,
    write_outputs,
)


def test_audit_runs_and_matches_schema():
    main, full = build_coverage_audit(mode="fixture")

    # Schema and row counts (design §3.3, §3.4, §3.5).
    assert list(main.columns) == SCHEMA
    assert len(main) == 17
    assert len(full) == 21  # 17 rows + 4 P4 anchors

    # One row per audited field, no duplicates.
    assert main["field"].is_unique


def test_percentages_and_ratio_guard():
    main, _ = build_coverage_audit(mode="fixture")

    # Percentages are within [0, 100].
    for col in ("green_pct", "other_pct"):
        vals = main[col].dropna()
        assert ((vals >= 0) & (vals <= 100)).all()

    # Ratio is NaN when other_pct is 0 (D-T4.0-7), never +inf.
    zero_other = main[main["other_pct"] == 0]
    assert zero_other["ratio"].isna().all()


def test_company_fields_have_real_coverage():
    # Company-level rows are computed against the real merged population, so at
    # least one core field must show non-zero coverage in both groups.
    main, _ = build_coverage_audit(mode="fixture")
    yf = main[main["field"] == "year_founded"].iloc[0]
    assert yf["green_n_nonnull"] > 0
    assert yf["other_n_nonnull"] > 0


def test_outputs_written_with_n10_labels(tmp_path):
    main, full = build_coverage_audit(mode="fixture")
    main_path, full_path = write_outputs(main, full, output_dir=tmp_path)

    assert main_path.exists() and full_path.exists()
    header = pd.read_csv(main_path, nrows=0).columns.tolist()
    assert f"{config.GROUP_GREEN}: %" in header
    assert f"{config.GROUP_OTHER}: %" in header
    # Rule N10: never "non-green".
    assert not any("non-green" in c.lower() for c in header)
