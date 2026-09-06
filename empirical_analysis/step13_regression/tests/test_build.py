"""Tests for Step 13 (exploratory regression).

Synthetic frames exercise the estimator and the three families:
- OLS recovers a known green coefficient;
- adding a control correlated with green shrinks the green coefficient
  (the composition-adjustment demonstration);
- an LPM on a binary outcome returns coef / SE / p / CI / n / R2;
- the timing sample drops null-lag rows (observed-only);
- family-3 capital uses log1p and excludes (never zero-fills) missing amounts;
- rare / missing FE levels fold into "Other" and the sample is one row per firm;
- every table carries the RESULT_COLUMNS and the audit reconciles the trio.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from empirical_analysis.step13_regression import config
from empirical_analysis.step13_regression.build import (
    HAVE_STATSMODELS,
    acceptance_report,
    build_all,
    build_design,
    build_first5_capital_frame,
    fit_ols,
    regress_outcome,
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


def test_ols_recovers_known_green_coefficient():
    # y is exactly linear in green: intercept 1, slope 2.
    rows = [{"company_id": f"F{i}", "green": i % 2,
             "y": 1.0 + 2.0 * (i % 2)} for i in range(20)]
    frame = _frame(rows)
    X, _ = build_design(frame, [], config.INDUSTRY_COL_GROUP, 1)
    stats = fit_ols(frame["y"].to_numpy(float), X)
    assert stats["green_coef"] == pytest.approx(2.0, abs=1e-6)
    assert stats["r_squared"] == pytest.approx(1.0, abs=1e-9)
    assert stats["n"] == 20


def test_control_shrinks_green_coefficient():
    # Within each country green == other; green is concentrated in the
    # high-outcome country, so the raw (M0) gap is composition, not green.
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
    by_model = {r["model"]: r for r in result_rows}
    # M0: raw gap = mean(green) - mean(other) = 8 - 2 = 6
    assert by_model["M0"]["green_coef"] == pytest.approx(6.0, abs=1e-6)
    # M2: adding country FE collapses the gap to ~0
    assert abs(by_model["M2"]["green_coef"]) < 1e-6


def test_lpm_binary_outcome_returns_full_statistics():
    rows = [{"company_id": f"F{i}", "green": i % 2,
             "financed": (i + (i % 2)) % 2} for i in range(30)]
    frame = _frame(rows)
    X, _ = build_design(frame, [], config.INDUSTRY_COL_GROUP, 1)
    stats = fit_ols(frame["financed"].to_numpy(float), X)
    for key in ("green_coef", "green_se", "green_pvalue",
                "green_ci_low", "green_ci_high", "n", "r_squared"):
        assert key in stats
    assert np.isfinite(stats["green_coef"])
    assert stats["green_ci_low"] <= stats["green_coef"] <= stats["green_ci_high"]
    assert stats["n"] == 30


def test_timing_sample_is_observed_only():
    rows = [{"company_id": f"F{i}", "green": i % 2,
             "first_funding_lag": (float(i) if i % 3 else np.nan)}
            for i in range(30)]
    frame = _frame(rows)
    n_obs = int(frame["first_funding_lag"].notna().sum())
    result_rows, audits = regress_outcome(
        frame, "first_funding_lag", "first_funding_lag", "timing",
        "observed", config.INDUSTRY_COL_GROUP
    )
    assert all(r["n"] == n_obs for r in result_rows)
    assert all(a["n_missing_outcome"] == 30 - n_obs for a in audits)


def test_capital_uses_log1p_and_excludes_missing():
    firm = _frame([
        {"company_id": "F1", "green": 1, "year_founded": 2017},
        {"company_id": "F2", "green": 0, "year_founded": 2018},
        {"company_id": "F3", "green": 1, "year_founded": 2019},  # undisclosed only
    ])
    deals = pd.DataFrame([
        {"company_id": "F1", "deal_id": "d1", "deal_date": pd.Timestamp("2018-01-01"),
         "stage_group": "Early-stage VC", "deal_size": 10.0, "size_is_actual": 1},
        {"company_id": "F2", "deal_id": "d2", "deal_date": pd.Timestamp("2019-01-01"),
         "stage_group": "Early-stage VC", "deal_size": 20.0, "size_is_actual": 1},
        {"company_id": "F3", "deal_id": "d3", "deal_date": pd.Timestamp("2020-01-01"),
         "stage_group": "Early-stage VC", "deal_size": np.nan, "size_is_actual": 0},
    ])
    frame, diag = build_first5_capital_frame(firm, deals, config.INDUSTRY_COL_GROUP)
    # F3 (undisclosed) is excluded, never entered as zero
    assert set(frame["company_id"]) == {"F1", "F2"}
    assert diag["n_observed"] == 2
    f1 = frame.set_index("company_id").loc["F1"]
    assert f1[config.CAPITAL_OUTCOME_LABEL] == pytest.approx(np.log1p(10.0))
    assert (frame["first5_disclosed_capital"] > 0).all()


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


def _full_firm_frame() -> pd.DataFrame:
    rows = []
    for i in range(24):
        rows.append({
            "company_id": f"F{i}",
            "green": i % 2,
            "financed": 1 if i % 2 or i % 3 == 0 else 0,
            "any_vc": 1 if i % 3 == 0 else 0,
            "any_grant": 1 if i % 4 == 0 else 0,
            "any_accelerator": 1 if i % 5 == 0 else 0,
            "first_funding_lag": (float(i % 5) if i % 2 == 0 else np.nan),
            "first_vc_lag": (float(i % 4) if i % 3 == 0 else np.nan),
            "cohort": "2016-2018" if i % 2 == 0 else "2019-2021",
            "hq_country": "CountryA" if i % 2 == 0 else "CountryB",
            "primary_industry_group": "Ind1" if i % 3 else "Ind2",
            "primary_industry_code": "C1" if i % 3 else "C2",
            "year_founded": 2016 + (i % 5),
        })
    return pd.DataFrame(rows)


def _deals_for(firm: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i, cid in enumerate(firm["company_id"]):
        yf = int(firm.set_index("company_id").loc[cid, "year_founded"])
        rows.append({
            "company_id": cid, "deal_id": f"d{i}",
            "deal_date": pd.Timestamp(f"{yf + 1}-01-01"),
            "stage_group": "Early-stage VC",
            "deal_size": float(10 + i) if i % 2 == 0 else np.nan,
            "size_is_actual": 1 if i % 2 == 0 else 0,
        })
    return pd.DataFrame(rows)


def test_build_all_tables_and_acceptance(tmp_path):
    firm = _full_firm_frame()
    deals = _deals_for(firm)
    result = build_all(firm, deals, industry_col=config.INDUSTRY_COL_GROUP)

    for name in (config.OUT_ACCESS, config.OUT_TIMING, config.OUT_CAPITAL):
        df = result.tables[name]
        assert list(df.columns) == config.RESULT_COLUMNS, name
        for outcome, grp in df.groupby("outcome"):
            assert set(grp["model"]) == {"M0", "M1", "M2", "M3"}, outcome

    # access is estimated over the full synthetic population on every model
    acc = result.tables[config.OUT_ACCESS]
    assert (acc["n"] == len(firm)).all()

    # audit reconciles the trio and one-row-per-firm
    audit = result.audit
    assert (audit["n_green"] + audit["n_other"] == audit["n"]).all()
    assert (audit["n"] == audit["n_unique_firms"]).all()

    lines = acceptance_report(result)
    assert not any("FAIL" in ln for ln in lines), "\n".join(lines)

    from empirical_analysis.step13_regression.build import write_outputs
    write_outputs(result, tmp_path)
    assert (tmp_path / f"{config.OUT_ACCESS}.csv").exists()
    assert (tmp_path / f"{config.SAMPLE_AUDIT}.csv").exists()
    assert (tmp_path / f"{config.CAPTIONS_FILE}.csv").exists()
