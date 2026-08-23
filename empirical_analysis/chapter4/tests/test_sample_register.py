"""Tests for the Chapter 4 sample-size register."""

from __future__ import annotations

import pandas as pd

from empirical_analysis.chapter4.sample_register import build_sample_register


def _mini_firm() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"company_id": "F1", "green": 1, "financed": 1, "employees": 10,
             "employee_band": "1-10", "business_status": "Startup",
             "year_founded": 2020, "age_years": 6, "cohort": "2019-2021",
             "hq_country": "France", "total_raised": 5.0,
             "first_deal_size": 2.0, "first_funding_lag": 1.0, "first_vc_lag": 2.0,
             "n_investors_lifetime": 2, "share_investors_domestic": 0.5,
             "any_grant": 0, "any_vc": 1},
            {"company_id": "F2", "green": 0, "financed": 0, "employees": None,
             "employee_band": None, "business_status": None,
             "year_founded": 2022, "age_years": 4, "cohort": "2022-2024",
             "hq_country": "France", "total_raised": None,
             "first_deal_size": None, "first_funding_lag": None, "first_vc_lag": None,
             "n_investors_lifetime": 0, "share_investors_domestic": None,
             "any_grant": 0, "any_vc": 0},
        ]
    )


def test_register_has_required_columns():
    reg = build_sample_register(_mini_firm())
    for col in ("output_id", "population", "n_total", "sample_definition", "rationale"):
        assert col in reg.columns


def test_register_master_populations():
    reg = build_sample_register(_mini_firm()).set_index("statistic")
    assert reg.loc["full_population", "n_total"] == 2
    assert reg.loc["financed_subsample", "n_total"] == 1
    assert reg.loc["green_only", "n_green"] == 1


def test_register_step3_rows_present():
    reg = build_sample_register(_mini_firm())
    t41 = reg[(reg["output_id"] == "T4.1") & (reg["statistic"] == "n_firms")]
    assert len(t41) == 1
    assert t41.iloc[0]["population"] == "Full"


def test_register_employee_n_reflects_missing():
    reg = build_sample_register(_mini_firm())
    emp = reg[reg["statistic"] == "median_employees_and_bands"].iloc[0]
    assert emp["n_total"] == 1
    assert emp["n_green"] == 1
