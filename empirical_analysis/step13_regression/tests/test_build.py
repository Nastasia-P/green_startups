"""Tests for Step 13 (common-horizon regression).

Synthetic firm panels (mimicking `first5_analysis.parquet`) exercise the
estimator and the three regression families:
- OLS recovers a known green coefficient;
- adding a control correlated with green shrinks the green coefficient
  (the composition-adjustment demonstration);
- an LPM on a binary outcome returns coef / SE / p / CI / n / R2, plus
  percentage-point display columns (coef_pp/se_pp = coef/std_error * 100);
- significance stars are generated from the stored p-value via
  config.STAR_RULE, never hard-coded;
- the timing sample drops null-lag rows (observed-only, conditional on the
  in-window event);
- the capital family uses log1p on `disclosed_capital_5yr`, restricted to
  `has_disclosed_capital_5yr == 1` (never zero-fills missing amounts);
- rare / missing FE levels fold into "Other" and the sample is one row per
  firm;
- every table carries RESULT_COLUMNS, uses column labels (1)-(4) (never
  M0-M3), and the audit reconciles the trio;
- the capital coverage diagnostic reports eligible/disclosed counts and
  coverage rates by green/other.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from empirical_analysis.step13_regression import config
from empirical_analysis.step13_regression.build import (
    HAVE_STATSMODELS,
    acceptance_report,
    build_capital_coverage,
    build_design,
    fit_ols,
    regress_outcome,
    _p_display,
    _round_cols,
    _stars,
)

pytestmark = pytest.mark.skipif(
    not HAVE_STATSMODELS, reason="statsmodels not installed"
)


@pytest.fixture(autouse=True)
def _small_fe_threshold(monkeypatch):
    # Synthetic frames are tiny; keep every FE level so controls actually enter.
    monkeypatch.setattr(config, "MIN_FE_LEVEL_N", 1)


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    # ensure the control columns exist even when a test does not vary them
    for col, default in (
        (config.COHORT_COL, "2016-2018"),
        (config.COUNTRY_COL, "CountryA"),
        (config.INDUSTRY_COL_GROUP, "Ind1"),
        (config.INDUSTRY_COL_CODE, "C1"),
    ):
        if col not in df.columns:
            df[col] = default
    return df


# --------------------------------------------------------------------------
# Stars / p-value display / rounding helpers
# --------------------------------------------------------------------------
def test_stars_generated_from_p_value_thresholds():
    assert _stars(0.001) == "***"
    assert _stars(0.02) == "**"
    assert _stars(0.07) == "*"
    assert _stars(0.5) == ""
    assert _stars(float("nan")) == ""


def test_p_display_avoids_bare_zero_for_tiny_p():
    tiny = 10 ** (-(config.DECIMALS + 2))
    assert _p_display(tiny).startswith("<")
    assert _p_display(0.5) == f"{0.5:.{config.DECIMALS}f}"


def test_round_cols_applies_single_tunable_precision(monkeypatch):
    monkeypatch.setattr(config, "DECIMALS", 2)
    monkeypatch.setattr(config, "DECIMALS_PP", 1)
    df = pd.DataFrame([{
        "coef": 0.123456, "std_error": 0.012345, "ci_low": -0.01, "ci_high": 0.25,
        "r_squared": 0.333333, "p_value": 0.049999, "coef_pp": 12.3456, "se_pp": 1.2345,
    }])
    out = _round_cols(df)
    assert out["coef"].iloc[0] == 0.12
    assert out["p_value"].iloc[0] == 0.05
    assert out["coef_pp"].iloc[0] == 12.3
    assert out["se_pp"].iloc[0] == 1.2


# --------------------------------------------------------------------------
# Core estimator
# --------------------------------------------------------------------------
def test_ols_recovers_known_green_coefficient():
    # y is exactly linear in green: intercept 1, slope 2.
    rows = [{"company_id": f"F{i}", "green": i % 2,
             "y": 1.0 + 2.0 * (i % 2)} for i in range(20)]
    frame = _frame(rows)
    X, _ = build_design(frame, [], config.INDUSTRY_COL_GROUP, 1)
    stats = fit_ols(frame["y"].to_numpy(float), X)
    assert stats["coef"] == pytest.approx(2.0, abs=1e-6)
    assert stats["r_squared"] == pytest.approx(1.0, abs=1e-9)
    assert stats["n"] == 20


def test_control_shrinks_green_coefficient():
    # Within each country green == other; green is concentrated in the
    # high-outcome country, so the raw (1) gap is composition, not green.
    rows = []
    i = 0
    for _ in range(8):  # CountryA: outcome 10, mostly green
        rows.append({"company_id": f"A{i}", "green": 1, "hq_country": "CountryA", "y": 10.0}); i += 1
    for _ in range(2):
        rows.append({"company_id": f"A{i}", "green": 0, "hq_country": "CountryA", "y": 10.0}); i += 1
    for _ in range(2):  # CountryB: outcome 0, mostly other
        rows.append({"company_id": f"B{i}", "green": 1, "hq_country": "CountryB", "y": 0.0}); i += 1
    for _ in range(8):
        rows.append({"company_id": f"B{i}", "green": 0, "hq_country": "CountryB", "y": 0.0}); i += 1
    frame = _frame(rows)

    result_rows, _ = regress_outcome(
        frame, "y", "y", "test", "synthetic", config.INDUSTRY_COL_GROUP
    )
    by_spec = {r["spec"]: r for r in result_rows}
    # spec1 (column "(1)"): raw gap = mean(green) - mean(other) = 8 - 2 = 6
    assert by_spec["spec1"]["column"] == "(1)"
    assert by_spec["spec1"]["coef"] == pytest.approx(6.0, abs=1e-6)
    # spec3 (column "(3)"): adding country FE collapses the gap to ~0
    assert by_spec["spec3"]["column"] == "(3)"
    assert abs(by_spec["spec3"]["coef"]) < 1e-6


def test_lpm_binary_outcome_returns_full_statistics_and_pp_scaling():
    rows = [{"company_id": f"F{i}", "green": i % 2,
             "financed": (i + (i % 2)) % 2} for i in range(30)]
    frame = _frame(rows)
    result_rows, _ = regress_outcome(
        frame, "financed", "financed", "access", "synthetic",
        config.INDUSTRY_COL_GROUP, pp_scale=True,
    )
    for row in result_rows:
        for key in ("coef", "std_error", "p_value", "ci_low", "ci_high",
                    "n", "r_squared", "stars", "p_value_display"):
            assert key in row
        assert np.isfinite(row["coef"])
        assert row["ci_low"] <= row["coef"] <= row["ci_high"]
        assert row["n"] == 30
        # percentage-point display columns scale the raw 0-1 coefficient
        assert row["coef_pp"] == pytest.approx(row["coef"] * 100, abs=1e-6)
        assert row["se_pp"] == pytest.approx(row["std_error"] * 100, abs=1e-6)
        assert row["stars"] == _stars(row["p_value"])


def test_pp_scale_false_leaves_pp_columns_nan():
    rows = [{"company_id": f"F{i}", "green": i % 2, "y": float(i)} for i in range(20)]
    frame = _frame(rows)
    result_rows, _ = regress_outcome(
        frame, "y", "y", "timing", "synthetic", config.INDUSTRY_COL_GROUP,
        pp_scale=False,
    )
    for row in result_rows:
        assert np.isnan(row["coef_pp"])
        assert np.isnan(row["se_pp"])


def test_timing_sample_is_observed_only():
    rows = [{"company_id": f"F{i}", "green": i % 2,
             "first_financing_lag_5yr": (float(i) if i % 3 else np.nan)}
            for i in range(30)]
    frame = _frame(rows)
    n_obs = int(frame["first_financing_lag_5yr"].notna().sum())
    result_rows, audits = regress_outcome(
        frame, "first_financing_lag_5yr", "first_financing_lag", "timing",
        "observed", config.INDUSTRY_COL_GROUP
    )
    assert all(r["n"] == n_obs for r in result_rows)
    assert all(a["n_missing_outcome"] == 30 - n_obs for a in audits)


def test_rare_fe_levels_fold_into_other_and_one_row_per_firm():
    rows = [{"company_id": f"F{i}", "green": i % 2, "y": float(i),
             "hq_country": ("Rare" if i == 0 else "Common")} for i in range(20)]
    frame = _frame(rows)
    # With a high threshold, the singleton "Rare" country folds into "Other",
    # leaving two levels (Common, Other) -> one dropped as reference -> 1 dummy.
    X, meta = build_design(frame, ["country"], config.INDUSTRY_COL_GROUP, min_n=5)
    assert meta["n_fe_country"] == 2
    country_cols = [c for c in X.columns if c.startswith("country_")]
    assert len(country_cols) == 1
    _, audits = regress_outcome(
        frame, "y", "y", "test", "synthetic", config.INDUSTRY_COL_GROUP
    )
    assert all(a["n"] == a["n_unique_firms"] for a in audits)


# --------------------------------------------------------------------------
# Full build_all over a synthetic common-horizon panel
# --------------------------------------------------------------------------
def _full_panel() -> pd.DataFrame:
    rows = []
    for i in range(24):
        rows.append({
            "company_id": f"F{i}",
            "green": i % 2,
            "any_financing_5yr": 1 if i % 2 or i % 3 == 0 else 0,
            "any_vc_5yr": 1 if i % 3 == 0 else 0,
            "any_grant_5yr": 1 if i % 4 == 0 else 0,
            "any_accelerator_5yr": 1 if i % 5 == 0 else 0,
            "first_financing_lag_5yr": (float(i % 5) if i % 2 == 0 else np.nan),
            "first_vc_lag_5yr": (float(i % 4) if i % 3 == 0 else np.nan),
            "disclosed_capital_5yr": (float(10 + i) if i % 2 == 0 else np.nan),
            "has_disclosed_capital_5yr": 1 if i % 2 == 0 else 0,
            "cohort": "2016-2018" if i % 2 == 0 else "2019-2021",
            "hq_country": "CountryA" if i % 2 == 0 else "CountryB",
            "primary_industry_group": "Ind1" if i % 3 else "Ind2",
            "year_founded": 2016 + (i % 5),
        })
    return pd.DataFrame(rows)


def test_build_all_tables_and_acceptance(tmp_path):
    from empirical_analysis.step13_regression.build import build_all, write_outputs

    panel = _full_panel()
    result = build_all(panel, industry_col=config.INDUSTRY_COL_GROUP)

    for name in (config.OUT_ACCESS, config.OUT_TIMING, config.OUT_CAPITAL):
        df = result.tables[name]
        assert list(df.columns) == config.RESULT_COLUMNS, name
        for outcome, grp in df.groupby("outcome"):
            assert set(grp["spec"]) == {"spec1", "spec2", "spec3", "spec4"}, outcome
            assert set(grp["column"]) == {"(1)", "(2)", "(3)", "(4)"}, outcome
            # never leak internal M0-M3 naming into any output-facing column
            assert not grp["column"].astype(str).str.contains("M0|M1|M2|M3").any()

    # access is estimated over every row of the synthetic common-horizon panel
    acc = result.tables[config.OUT_ACCESS]
    assert (acc["n"] == len(panel)).all()

    # capital only uses the disclosed-amount subset (never zero-filled)
    cap = result.tables[config.OUT_CAPITAL]
    n_disclosed = int((panel["has_disclosed_capital_5yr"] == 1).sum())
    assert (cap["n"] == n_disclosed).all()

    # audit reconciles the trio and one-row-per-firm
    audit = result.audit
    assert (audit["n_green"] + audit["n_other"] == audit["n"]).all()
    assert (audit["n"] == audit["n_unique_firms"]).all()

    lines = acceptance_report(result)
    assert not any("FAIL" in ln for ln in lines), "\n".join(lines)

    write_outputs(result, tmp_path)
    assert (tmp_path / f"{config.OUT_ACCESS}.csv").exists()
    assert (tmp_path / f"{config.OUT_TIMING}.csv").exists()
    assert (tmp_path / f"{config.OUT_CAPITAL}.csv").exists()
    assert (tmp_path / f"{config.CAPITAL_COVERAGE}.csv").exists()
    assert (tmp_path / f"{config.SAMPLE_AUDIT}.csv").exists()
    assert (tmp_path / f"{config.CAPTIONS_FILE}.csv").exists()
    # no formatted/LaTeX table files are produced
    assert not list(tmp_path.glob("*.tex"))


def test_capital_coverage_diagnostic_reconciles_and_is_not_capital_access():
    panel = _full_panel()
    cov = build_capital_coverage(panel)
    row = cov.iloc[0]
    g = panel[panel["green"] == 1]
    o = panel[panel["green"] != 1]
    assert row["eligible_firms"] == len(panel)
    assert row["eligible_green"] == len(g)
    assert row["eligible_other"] == len(o)
    assert row["firms_with_disclosed_capital"] == int(
        (panel["has_disclosed_capital_5yr"] == 1).sum()
    )
    assert row["firms_with_disclosed_capital_green"] == int(
        (g["has_disclosed_capital_5yr"] == 1).sum()
    )
    assert row["n_excluded_no_disclosed_amount"] == (
        row["eligible_firms"] - row["firms_with_disclosed_capital"]
    )
    assert "not a capital-access measure" in row["note"]
    assert "intensive margin" in row["note"]


def test_acceptance_report_flags_would_be_M0_naming_as_fail(monkeypatch):
    # Sanity check that C2 actually verifies the column-label invariant: if a
    # spec's column label regresses to an M-name, acceptance must fail.
    from empirical_analysis.step13_regression.build import Step13Result

    bad_row = {c: None for c in config.RESULT_COLUMNS}
    bad_row.update({
        "outcome": "any_financing", "family": "access", "spec": "spec1",
        "column": "M0", "sample": "x", "n": 10, "coef": 0.1, "p_value": 0.01,
        "cohort_controls": 0, "country_fe": 0, "industry_fe": 0,
        "n_fe_country": 0, "n_fe_industry": 0,
    })
    result = Step13Result()
    result.tables[config.OUT_ACCESS] = pd.DataFrame([bad_row])
    result.tables[config.OUT_TIMING] = pd.DataFrame(columns=config.RESULT_COLUMNS)
    result.tables[config.OUT_CAPITAL] = pd.DataFrame(columns=config.RESULT_COLUMNS)
    result.audit = pd.DataFrame(columns=[
        "family", "outcome", "spec", "sample", "n", "n_green", "n_other",
        "n_unique_firms", "n_missing_outcome",
    ])
    result.diagnostics = {"n_eligible": 10, "timing_observed": {}, "capital_observed": 0}
    lines = acceptance_report(result)
    assert any("[C2]" in ln and "FAIL" in ln for ln in lines)
