"""Tests for Step 7 (geography x finance).

A small synthetic firm + deals + relation set spanning countries of different sizes
(including a one-firm country) exercises:
- Block A: T4.26 firm share on the full population, funding share on recorded amounts
  only with coverage < 1, both capital measures; T4.28 origin shares sum to 1 within
  group and exclude unknown-country; T4.29 country x stage green/other amount split;
  no country floor (every country appears) and tiny countries carry low_n_flag.
- Block B: each `*_by_country` table has a leading country column and one row per
  country; a headline value equals the Step 5/6 helper run on that country's slice;
  low_n_flag set when green < 30; the trio is present everywhere.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from empirical_analysis.step5_funding import build as s5
from empirical_analysis.step6_investors import build as s6
from empirical_analysis.step7_geo_finance.build import (
    build_all,
    build_country_funding_by_type,
    build_green_share_firms_vs_capital,
    build_investor_origin_by_country,
    write_outputs,
)
from empirical_analysis.step7_geo_finance.by_country import (
    build_by_country,
    qualifying_countries,
)


def _firm_frame() -> pd.DataFrame:
    # Germany 4 (green F1,F2), France 3 (green F5), Italy 1 (green F8).
    rows = [
        {"company_id": "F1", "green": 1, "green_signal_group": "Stage 1",
         "hq_country": "Germany", "total_raised": 100.0, "financed": 1, "any_vc": 1,
         "cohort": "2019-2021", "age_years": 6, "first_funding_lag": 1,
         "first_vc_lag": 2, "n_deals": 2, "n_investors_lifetime": 3,
         "any_ivc_investor": 1, "public_private_lifetime": 1},
        {"company_id": "F2", "green": 1, "green_signal_group": "Stage 2+3",
         "hq_country": "Germany", "total_raised": 50.0, "financed": 1, "any_vc": 0,
         "cohort": "2019-2021", "age_years": 6, "first_funding_lag": 2,
         "first_vc_lag": np.nan, "n_deals": 1, "n_investors_lifetime": 1,
         "any_ivc_investor": 0, "public_private_lifetime": 0},
        {"company_id": "F3", "green": 0, "green_signal_group": "none",
         "hq_country": "Germany", "total_raised": 10.0, "financed": 1, "any_vc": 1,
         "cohort": "2016-2018", "age_years": 8, "first_funding_lag": 1,
         "first_vc_lag": 1, "n_deals": 3, "n_investors_lifetime": 2,
         "any_ivc_investor": 1, "public_private_lifetime": 0},
        {"company_id": "F4", "green": 0, "green_signal_group": "none",
         "hq_country": "Germany", "total_raised": np.nan, "financed": 0, "any_vc": 0,
         "cohort": "2022-2024", "age_years": 3, "first_funding_lag": np.nan,
         "first_vc_lag": np.nan, "n_deals": 0, "n_investors_lifetime": 0,
         "any_ivc_investor": 0, "public_private_lifetime": 0},
        {"company_id": "F5", "green": 1, "green_signal_group": "Stage 1",
         "hq_country": "France", "total_raised": 80.0, "financed": 1, "any_vc": 1,
         "cohort": "2019-2021", "age_years": 7, "first_funding_lag": 1,
         "first_vc_lag": 1, "n_deals": 2, "n_investors_lifetime": 2,
         "any_ivc_investor": 1, "public_private_lifetime": 1},
        {"company_id": "F6", "green": 0, "green_signal_group": "none",
         "hq_country": "France", "total_raised": 20.0, "financed": 1, "any_vc": 0,
         "cohort": "2019-2021", "age_years": 7, "first_funding_lag": 2,
         "first_vc_lag": np.nan, "n_deals": 1, "n_investors_lifetime": 1,
         "any_ivc_investor": 0, "public_private_lifetime": 0},
        {"company_id": "F7", "green": 0, "green_signal_group": "none",
         "hq_country": "France", "total_raised": np.nan, "financed": 0, "any_vc": 0,
         "cohort": "2022-2024", "age_years": 2, "first_funding_lag": np.nan,
         "first_vc_lag": np.nan, "n_deals": 0, "n_investors_lifetime": 0,
         "any_ivc_investor": 0, "public_private_lifetime": 0},
        {"company_id": "F8", "green": 1, "green_signal_group": "Stage 1",
         "hq_country": "Italy", "total_raised": 5.0, "financed": 1, "any_vc": 0,
         "cohort": "2019-2021", "age_years": 6, "first_funding_lag": 1,
         "first_vc_lag": np.nan, "n_deals": 1, "n_investors_lifetime": 1,
         "any_ivc_investor": 0, "public_private_lifetime": 0},
    ]
    return pd.DataFrame(rows)


def _deals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"company_id": "F1", "deal_id": "D1", "deal_date": "2018-01-01",
             "stage_group": "Grant", "deal_size": 1.0, "n_investors": 1,
             "n_new_investors": 1, "is_first_deal": 1, "post_valuation": np.nan},
            {"company_id": "F1", "deal_id": "D2", "deal_date": "2020-01-01",
             "stage_group": "Early-stage VC", "deal_size": 10.0, "n_investors": 3,
             "n_new_investors": 2, "is_first_deal": 0, "post_valuation": 40.0},
            {"company_id": "F2", "deal_id": "D3", "deal_date": "2020-06-01",
             "stage_group": "Angel/Seed", "deal_size": 2.0, "n_investors": 1,
             "n_new_investors": 1, "is_first_deal": 1, "post_valuation": np.nan},
            {"company_id": "F3", "deal_id": "D4", "deal_date": "2017-01-01",
             "stage_group": "Early-stage VC", "deal_size": 5.0, "n_investors": 2,
             "n_new_investors": 2, "is_first_deal": 1, "post_valuation": 20.0},
            {"company_id": "F5", "deal_id": "D5", "deal_date": "2019-01-01",
             "stage_group": "Early-stage VC", "deal_size": 8.0, "n_investors": 2,
             "n_new_investors": 2, "is_first_deal": 1, "post_valuation": np.nan},
            {"company_id": "F6", "deal_id": "D6", "deal_date": "2020-01-01",
             "stage_group": "Grant", "deal_size": np.nan, "n_investors": 1,
             "n_new_investors": 1, "is_first_deal": 1, "post_valuation": np.nan},
            {"company_id": "F8", "deal_id": "D7", "deal_date": "2020-01-01",
             "stage_group": "Angel/Seed", "deal_size": 3.0, "n_investors": 1,
             "n_new_investors": 1, "is_first_deal": 1, "post_valuation": np.nan},
        ]
    )


def _company_investors() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"company_id": "F1", "investor_id": "I1"},  # Germany domestic
            {"company_id": "F1", "investor_id": "I2"},  # US non-european
            {"company_id": "F3", "investor_id": "I3"},  # France cross-border
            {"company_id": "F5", "investor_id": "I4"},  # France domestic
            {"company_id": "F8", "investor_id": "I5"},  # unknown country
        ]
    )


def _investors() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"investor_id": "I1", "investor_type_grp": "Independent VC",
             "investor_country": "Germany"},
            {"investor_id": "I2", "investor_type_grp": "Independent VC",
             "investor_country": "United States"},
            {"investor_id": "I3", "investor_type_grp": "Public/Government",
             "investor_country": "France"},
            {"investor_id": "I4", "investor_type_grp": "Independent VC",
             "investor_country": "France"},
            {"investor_id": "I5", "investor_type_grp": "Corporate",
             "investor_country": np.nan},
        ]
    )


# --------------------------------------------------------------------------
# Block A
# --------------------------------------------------------------------------
def test_t426_firm_share_and_capital_measures():
    t426 = build_green_share_firms_vs_capital(_firm_frame(), _deals()).set_index("country")
    # Germany: 4 firms, 2 green -> firm share 0.5.
    assert t426.loc["Germany", "green_firm_share"] == 0.5
    assert t426.loc["Germany", "n_startups"] == 4
    # total_raised: green 100+50=150, all 100+50+10=160 -> 0.9375.
    assert t426.loc["Germany", "green_funding_share_total_raised"] == round(150 / 160, 4)
    # coverage_total_raised: 3 of 4 firms have total_raised -> 0.75.
    assert t426.loc["Germany", "coverage_total_raised"] == 0.75
    # deal_size funding share: green D1+D2+D3 = 1+10+2 = 13; all += D4(5) = 18.
    assert t426.loc["Germany", "green_funding_share_dealsize"] == round(13 / 18, 4)
    # ratio > 1 (green over-represented in capital).
    assert t426.loc["Germany", "ratio_tr"] > 1


def test_t426_no_country_floor_and_low_n_flag():
    t426 = build_green_share_firms_vs_capital(_firm_frame(), _deals())
    # Every country appears, including one-firm Italy.
    assert set(t426["country"]) == {"Germany", "France", "Italy"}
    it = t426.set_index("country").loc["Italy"]
    assert it["low_n_flag"] == 1  # 1 green < 30
    # A high floor would drop small countries.
    gated = build_green_share_firms_vs_capital(_firm_frame(), _deals(), min_country_n=4)
    assert set(gated["country"]) == {"Germany"}


def test_t428_origin_shares_sum_to_one_and_exclude_unknown():
    t428 = build_investor_origin_by_country(
        _firm_frame(), _company_investors(), _investors()).set_index("country")
    # Germany known relations: I1 (domestic), I2 (non-european) -> both green (F1).
    de = t428.loc["Germany"]
    assert abs(de["green_domestic"] + de["green_eu_cross_border"]
               + de["green_non_european"] - 1.0) < 1e-6
    assert de["green_domestic"] == 0.5
    assert de["green_non_european"] == 0.5
    # Italy's only relation (I5) has unknown country -> Italy has no origin row.
    assert "Italy" not in t428.index


def test_t429_country_stage_amount_split():
    t429 = build_country_funding_by_type(_firm_frame(), _deals())
    de_vc = t429[(t429["country"] == "Germany")
                 & (t429["stage_group"] == "Early-stage VC")].iloc[0]
    # Green D2=10, other D4=5.
    assert de_vc["green_amount"] == 10.0
    assert de_vc["other_amount"] == 5.0
    assert de_vc["green_amount_share"] == round(10 / 15, 4)


# --------------------------------------------------------------------------
# Block B
# --------------------------------------------------------------------------
def test_qualifying_countries_no_floor():
    assert set(qualifying_countries(_firm_frame())) == {"Germany", "France", "Italy"}


def test_by_country_one_row_and_leading_country_and_trio():
    tables = build_by_country(
        _firm_frame(), _deals(), _company_investors(), _investors())
    trio = {"n_green", "n_others", "n_startups"}
    for name, df in tables.items():
        assert df.columns[0] == "country", f"{name} country not first"
        assert len(df) == 3, f"{name} should have one row per country"
        assert trio.issubset(df.columns), f"{name} missing the trio"
        assert "low_n_flag" in df.columns


def test_by_country_headline_matches_step5_helper():
    tables = build_by_country(_firm_frame(), _deals())
    # T4.10 median total_raised over financed green firms in Germany.
    firm = _firm_frame()
    de = firm[firm["hq_country"] == "Germany"]
    fin = s5._financed(de)
    g, _ = s5._split(fin)
    expect = s5._median(g["total_raised"])
    got = tables["T4_10_total_raised_by_cohort_by_country"].set_index("country").loc[
        "Germany", "green_median_total_raised"]
    assert got == expect


def test_by_country_headline_matches_step6_helper():
    tables = build_by_country(
        _firm_frame(), _deals(), _company_investors(), _investors())
    firm = _firm_frame()
    de = firm[firm["hq_country"] == "Germany"]
    invested = s6._invested(de)
    g, _ = s6._split(invested)
    expect = s6._median(g["n_investors_lifetime"])
    got = tables["T4_19_investor_flags_by_country"].set_index("country").loc[
        "Germany", "green_median_n_investors"]
    assert got == expect


def test_build_all_and_write(tmp_path):
    result = build_all(_firm_frame(), _deals(), _company_investors(), _investors())
    for key in ("T4_26_green_share_firms_vs_capital",
                "T4_28_investor_origin_by_country",
                "T4_29_country_funding_by_type",
                "F4_26_green_share_scatter"):
        assert key in result.tables
    # attach block B and write.
    for name, df in build_by_country(
            _firm_frame(), _deals(), _company_investors(), _investors()).items():
        result.tables[name] = df
    out = write_outputs(result, tmp_path)
    assert (out / "T4_26_green_share_firms_vs_capital.csv").exists()
    assert (out / "T4_23_investor_origin_by_country.csv").exists()
    assert (tmp_path / "captions_step7.csv").exists()
