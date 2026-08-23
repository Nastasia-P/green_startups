"""Tests for Step 2.

A small synthetic set of firms exercises the firm-level collapse: the access flag
must come from deal records rather than TotalRaised, same-deal co-investment must
require both investor kinds in one deal, negative funding lags must be dropped, and
missing spine scalars must not crash the build.
"""

from __future__ import annotations

import pandas as pd
import pytest

from empirical_analysis.step2_firm_table import config
from empirical_analysis.step2_firm_table.build import build_firm_table, write_outputs


def _spine_frame() -> pd.DataFrame:
    """population_key columns plus the spine scalars, one row per firm."""
    return pd.DataFrame(
        [
            # F1: green, financed, public+private in one deal, three investors.
            {"company_id": "F1", "green": 1, "green_stage": "vertical",
             "green_signal_group": "Stage 1", "year_founded": "2018",
             "hq_country": "France", "hq_city": "Paris", "employees": "30",
             "business_status": "Generating Revenue", "primary_sector": "Energy",
             "primary_industry_group": "Energy Services", "primary_industry_code": "E1",
             "total_raised": ""},
            # F2: founded 2016, NO deals, but a non-null total_raised (must stay unfinanced).
            {"company_id": "F2", "green": 0, "green_stage": "none",
             "green_signal_group": "none", "year_founded": "2016",
             "hq_country": "Germany", "hq_city": "Berlin", "employees": "5",
             "business_status": "Startup", "primary_sector": "Software",
             "primary_industry_group": "SaaS", "primary_industry_code": "S1",
             "total_raised": "5.0"},
            # F3: first deal predates founding -> negative lag.
            {"company_id": "F3", "green": 0, "green_stage": "none",
             "green_signal_group": "none", "year_founded": "2022",
             "hq_country": "Spain", "hq_city": "Madrid", "employees": "12",
             "business_status": "Startup", "primary_sector": "Software",
             "primary_industry_group": "SaaS", "primary_industry_code": "S1",
             "total_raised": ""},
            # F4: employees missing (null spine scalar).
            {"company_id": "F4", "green": 1, "green_stage": "token",
             "green_signal_group": "Stage 2+3", "year_founded": "2019",
             "hq_country": "Italy", "hq_city": "Milan", "employees": "",
             "business_status": "Product Development", "primary_sector": "Energy",
             "primary_industry_group": "Energy Services", "primary_industry_code": "E1",
             "total_raised": ""},
        ]
    )


def _clean_tables() -> dict[str, pd.DataFrame]:
    deals = pd.DataFrame(
        [
            {"company_id": "F1", "deal_id": "D1", "deal_date": "2019-05-01",
             "deal_type": "Grant", "deal_class": "Other", "stage_group": "Grant",
             "deal_size": None},
            {"company_id": "F1", "deal_id": "D2", "deal_date": "2020-06-01",
             "deal_type": "Early Stage VC", "deal_class": "VC",
             "stage_group": "Early-stage VC", "deal_size": "10"},
            {"company_id": "F3", "deal_id": "D3", "deal_date": "2019-01-01",
             "deal_type": "Early Stage VC", "deal_class": "VC",
             "stage_group": "Early-stage VC", "deal_size": "5"},
            {"company_id": "F4", "deal_id": "D4", "deal_date": "2021-01-01",
             "deal_type": "Grant", "deal_class": "Other", "stage_group": "Grant",
             "deal_size": "2"},
        ]
    )
    deal_investors = pd.DataFrame(
        [
            # D2 carries both a public and a private investor -> same-deal co-investment.
            {"deal_id": "D2", "investor_id": "I_pub", "investor_status": "New Investor", "is_lead": "Yes"},
            {"deal_id": "D2", "investor_id": "I_vc", "investor_status": "New Investor", "is_lead": "No"},
            # D4 has only a private investor -> not co-investment.
            {"deal_id": "D4", "investor_id": "I_vc", "investor_status": "New Investor", "is_lead": "Yes"},
        ]
    )
    company_investors = pd.DataFrame(
        [
            {"company_id": "F1", "investor_id": "I_pub", "investor_status": "Active"},
            {"company_id": "F1", "investor_id": "I_vc", "investor_status": "Active"},
            {"company_id": "F1", "investor_id": "I_corp", "investor_status": "Active"},
            {"company_id": "F4", "investor_id": "I_vc", "investor_status": "Active"},
        ]
    )
    investors = pd.DataFrame(
        [
            {"investor_id": "I_pub", "investor_type_grp": "Public/Government", "investor_country": "France"},
            {"investor_id": "I_vc", "investor_type_grp": "Independent VC", "investor_country": "United Kingdom"},
            {"investor_id": "I_corp", "investor_type_grp": "Corporate", "investor_country": "United States"},
        ]
    )
    return {
        "deals_clean": deals,
        "deal_investors_clean": deal_investors,
        "company_investors_clean": company_investors,
        "investors_clean": investors,
    }


@pytest.fixture()
def firm():
    result = build_firm_table(_clean_tables(), _spine_frame())
    return result.company_analysis.set_index("company_id")


def test_one_row_per_firm(firm):
    assert len(firm) == 4
    assert firm.index.is_unique


def test_financed_comes_from_deal_records_not_total_raised(firm):
    # F2 has a non-null total_raised but no qualifying deal: it is NOT financed.
    assert firm.loc["F2", "financed"] == 0
    assert firm.loc["F2", "n_deals"] == 0
    assert pd.notna(firm.loc["F2", "total_raised"])
    # F1 is financed via deal records.
    assert firm.loc["F1", "financed"] == 1
    assert firm.loc["F1", "n_deals"] == 2


def test_derived_scalars(firm):
    assert firm.loc["F1", "age_years"] == config.REFERENCE_YEAR - 2018
    assert firm.loc["F1", "cohort"] == "2016-2018"
    assert firm.loc["F1", "employee_band"] == "11-50"
    # F4 has no employees: band is missing, not a crash.
    assert pd.isna(firm.loc["F4", "employee_band"])


def test_deal_flags_and_first_last(firm):
    f1 = firm.loc["F1"]
    assert f1["any_grant"] == 1 and f1["any_vc"] == 1
    assert f1["n_rounds_vc"] == 1
    # First deal is the 2019 Grant with no size; the null size must be preserved.
    assert f1["first_deal_type"] == "Grant"
    assert pd.isna(f1["first_deal_size"])
    # Last deal is the 2020 VC round with a size of 10.
    assert f1["last_deal_type"] == "Early Stage VC"
    assert float(f1["last_deal_size"]) == 10.0
    assert float(f1["median_deal_size"]) == 10.0
    assert f1["n_deals_with_size"] == 1


def test_first_vc_and_funding_lags(firm):
    assert firm.loc["F1", "first_funding_lag"] == 1  # 2019 - 2018
    assert firm.loc["F1", "first_vc_lag"] == 2       # 2020 - 2018


def test_negative_lag_is_dropped(firm):
    # F3's only deal (2019) predates its founding (2022): the lag is NA, not -3.
    assert firm.loc["F3", "financed"] == 1
    assert pd.isna(firm.loc["F3", "first_funding_lag"])
    assert pd.isna(firm.loc["F3", "first_vc_lag"])


def test_same_deal_coinvestment(firm):
    # F1's D2 has both a public and a private investor -> same-deal co-investment.
    assert firm.loc["F1", "public_private_same_deal"] == 1
    assert firm.loc["F1", "public_private_lifetime"] == 1
    # F4 only ever has a private investor -> neither measure fires.
    assert firm.loc["F4", "public_private_same_deal"] == 0
    assert firm.loc["F4", "public_private_lifetime"] == 0


def test_investor_geo_shares(firm):
    # F1 has three located investors: France (domestic), UK (EU cross-border), US (non-EU).
    assert firm.loc["F1", "n_investors_lifetime"] == 3
    assert firm.loc["F1", "share_investors_domestic"] == pytest.approx(1 / 3)
    assert firm.loc["F1", "share_investors_eu_cross_border"] == pytest.approx(1 / 3)
    assert firm.loc["F1", "share_investors_non_european"] == pytest.approx(1 / 3)


def test_coverage_report_splits_green_and_other():
    result = build_firm_table(_clean_tables(), _spine_frame())
    cov = result.coverage.set_index("column")
    assert {"pct_all", "pct_green", "pct_other"} <= set(cov.columns)
    # total_raised is present for F2 (other) but no green firm here.
    assert cov.loc["total_raised", "pct_green"] == 0.0


def test_outputs_written_and_reloadable(tmp_path):
    result = build_firm_table(_clean_tables(), _spine_frame())
    out = write_outputs(result, output_dir=tmp_path)
    assert (out / config.OUTPUT_TABLE).exists()
    assert (out / "step2_coverage.csv").exists()
    assert (out / "step2_audit.csv").exists()
    reloaded = pd.read_parquet(out / config.OUTPUT_TABLE)
    assert len(reloaded) == 4
