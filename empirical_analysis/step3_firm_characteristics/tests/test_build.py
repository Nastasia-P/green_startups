"""Tests for Step 3 (firm characteristics).

A small synthetic firm table exercises the descriptive builders: the green/other
split and per-cell n, the cohort green share, industry composition that must keep
multi-tagged firms (percentages sum above 100%), green-only subsegments drawn from
verticals, and employee-band shares computed within each cohort.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from empirical_analysis.step3_firm_characteristics import config
from empirical_analysis.step3_firm_characteristics.build import (
    build_all,
    build_business_status,
    build_employment_by_cohort,
    build_green_share_by_cohort,
    build_green_subsegments,
    build_industry_tables,
    build_master_descriptive,
    write_outputs,
)


def _firm_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"company_id": "F1", "green": 1, "year_founded": 2017, "age_years": 9,
             "cohort": "2016-2018", "employees": 8, "employee_band": "1-10",
             "business_status": "Generating Revenue", "primary_sector": "Energy",
             "financed": 1, "total_raised": 5.0},
            {"company_id": "F2", "green": 1, "year_founded": 2020, "age_years": 6,
             "cohort": "2019-2021", "employees": 40, "employee_band": "11-50",
             "business_status": "Startup", "primary_sector": "Energy",
             "financed": 0, "total_raised": np.nan},
            {"company_id": "F3", "green": 0, "year_founded": 2017, "age_years": 9,
             "cohort": "2016-2018", "employees": 300, "employee_band": "200+",
             "business_status": "Generating Revenue", "primary_sector": "Software",
             "financed": 1, "total_raised": 12.0},
            {"company_id": "F4", "green": 0, "year_founded": 2023, "age_years": 3,
             "cohort": "2022-2024", "employees": np.nan, "employee_band": None,
             "business_status": None, "primary_sector": "Software",
             "financed": 0, "total_raised": np.nan},
            {"company_id": "F5", "green": 0, "year_founded": 2020, "age_years": 6,
             "cohort": "2019-2021", "employees": 15, "employee_band": "11-50",
             "business_status": "Startup", "primary_sector": "Software",
             "financed": 1, "total_raised": 3.0},
        ]
    )


def _industries_frame() -> pd.DataFrame:
    # F1 carries two sector tags -> multi-tag; totals per firm exceed firm count.
    return pd.DataFrame(
        [
            {"company_id": "F1", "industry_sector": "Energy", "industry_group": "Clean Energy",
             "industry_code": "E1", "is_primary": True},
            {"company_id": "F1", "industry_sector": "Software", "industry_group": "SaaS",
             "industry_code": "S1", "is_primary": False},
            {"company_id": "F2", "industry_sector": "Energy", "industry_group": "Clean Energy",
             "industry_code": "E1", "is_primary": True},
            {"company_id": "F3", "industry_sector": "Software", "industry_group": "SaaS",
             "industry_code": "S1", "is_primary": True},
        ]
    )


def _verticals_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"company_id": "F1", "vertical": "CleanTech"},
            {"company_id": "F2", "vertical": "CleanTech"},
            {"company_id": "F3", "vertical": "SaaS"},  # non-green -> must be excluded
        ]
    )


def test_master_descriptive_split_and_n():
    t41 = build_master_descriptive(_firm_frame()).set_index("characteristic")
    assert t41.loc["n_firms", "n_green"] == 2
    assert t41.loc["n_firms", "n_others"] == 3
    assert t41.loc["n_firms", "n_startups"] == 5
    # median employees: green {8,40}=24, other {300,15}=157.5 (F4 missing dropped)
    assert t41.loc["median_employees", "green_stat"] == 24.0
    assert t41.loc["median_employees", "n_green"] == 2
    assert t41.loc["median_employees", "n_others"] == 2
    assert t41.loc["median_employees", "n_startups"] == 4


def test_master_descriptive_band_shares_use_known_denominator():
    t41 = build_master_descriptive(_firm_frame()).set_index("characteristic")
    # Other group: bands known for F3 (200+) and F5 (11-50); F4 unknown -> denom 2.
    assert t41.loc["share_emp_11-50", "other_stat"] == 0.5
    assert t41.loc["share_emp_200+", "other_stat"] == 0.5


def test_green_share_by_cohort():
    f41 = build_green_share_by_cohort(_firm_frame()).set_index("cohort")
    assert f41.loc["2016-2018", "n_green"] == 1
    assert f41.loc["2016-2018", "n_others"] == 1
    assert f41.loc["2016-2018", "n_startups"] == 2
    assert f41.loc["2016-2018", "green_share"] == 0.5
    assert f41.loc["2019-2021", "green_share"] == 0.5
    assert (f41["overall_benchmark"] == config.GREEN_BENCHMARK).all()


def test_business_status_within_group_denominator():
    t42 = build_business_status(_firm_frame()).set_index("business_status")
    # Green: F1 revenue, F2 startup -> 50/50 of 2 known.
    assert t42.loc["Generating Revenue", "green_pct"] == 0.5
    # Other known statuses: F3 revenue, F5 startup (F4 None excluded) -> 50/50 of 2.
    assert t42.loc["Startup", "other_pct"] == 0.5


def test_industry_keeps_multitag_firms():
    firm = _firm_frame()
    tables = build_industry_tables(firm, _industries_frame())
    sec = tables["T4_03_industry_composition"].set_index("industry_sector")
    # Energy carries both green firms (F1, F2); Software carries F1 via its 2nd tag.
    assert sec.loc["Energy", "n_green"] == 2
    assert sec.loc["Software", "n_green"] == 1
    # Green firms tagged = 2 (F1, F2); shares over green sum > 1 due to F1 double tag.
    assert round(sec["green_pct_of_green"].sum(), 3) > 1.0


def test_green_subsegments_are_green_only():
    sub = build_green_subsegments(_firm_frame(), _verticals_frame()).set_index("vertical")
    assert "SaaS" not in sub.index  # F3 is not green
    assert sub.loc["CleanTech", "n_firms"] == 2
    assert sub.loc["CleanTech", "n_with_funding"] == 1  # only F1 financed


def test_employment_bands_within_cohort():
    emp = build_employment_by_cohort(_firm_frame()).set_index("cohort")
    # 2019-2021: green F2 (11-50), other F5 (11-50).
    assert emp.loc["2019-2021", "green_share_11-50"] == 1.0
    assert emp.loc["2019-2021", "other_share_11-50"] == 1.0
    assert emp.loc["2019-2021", "green_median_employees"] == 40.0


def test_build_all_and_write(tmp_path):
    result = build_all(_firm_frame(), _industries_frame(), _verticals_frame())
    for key in ("T4_01_master_descriptive", "F4_01_green_share_by_cohort",
                "T4_02_business_status", "T4_03_industry_composition",
                "T4_04_green_subsegments", "T4_05_employment_by_cohort"):
        assert key in result.tables
    out = write_outputs(result, tmp_path)
    reread = pd.read_csv(out / "T4_01_master_descriptive.csv")
    assert not reread.empty
    assert (tmp_path / "captions.csv").exists()
