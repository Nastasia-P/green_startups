"""Tests for Step 6 (investors and grants).

Small synthetic firm + relation + deal frames exercise the investor builders:
- INVESTED denominator: firms without a recorded investor are excluded.
- T4.19 flag shares equal the firm-column means over INVESTED.
- T4.22 sequencing counts only grant-before-VC firms; months are non-negative.
- T4.23 origin shares sum to 1 within group over known-country relations.
- T4.25 is deal grain, reported within stage group.
- every analytical table ends with the n_green / n_others / n_startups trio.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from empirical_analysis.step6_investors.build import (
    build_all,
    build_grant_to_vc,
    build_investor_flags,
    build_investor_origin,
    build_investor_type_distribution,
    build_syndication,
    write_outputs,
)


def _firm_frame() -> pd.DataFrame:
    rows = [
        # green, invested, UK, public+ivc, lifetime+same-deal, grant+vc
        {"company_id": "F1", "green": 1, "green_signal_group": "Stage 1",
         "hq_country": "United Kingdom", "n_investors_lifetime": 3,
         "any_public_investor": 1, "any_corporate_investor": 0, "any_ivc_investor": 1,
         "any_accelerator_investor": 0, "any_lender_investor": 0,
         "public_private_lifetime": 1, "public_private_same_deal": 1,
         "any_grant": 1, "any_vc": 1},
        # green, NOT invested -> excluded from every firm-grain table
        {"company_id": "F2", "green": 1, "green_signal_group": "Stage 2+3",
         "hq_country": "Germany", "n_investors_lifetime": 0,
         "any_public_investor": 0, "any_corporate_investor": 0, "any_ivc_investor": 0,
         "any_accelerator_investor": 0, "any_lender_investor": 0,
         "public_private_lifetime": 0, "public_private_same_deal": 0,
         "any_grant": 0, "any_vc": 0},
        # other, invested, France, corporate only, lifetime but not same-deal, grant+vc
        {"company_id": "F3", "green": 0, "green_signal_group": "none",
         "hq_country": "France", "n_investors_lifetime": 2,
         "any_public_investor": 1, "any_corporate_investor": 1, "any_ivc_investor": 0,
         "any_accelerator_investor": 0, "any_lender_investor": 0,
         "public_private_lifetime": 1, "public_private_same_deal": 0,
         "any_grant": 1, "any_vc": 1},
        # other, invested, Germany, ivc only, vc but no grant
        {"company_id": "F4", "green": 0, "green_signal_group": "none",
         "hq_country": "Germany", "n_investors_lifetime": 1,
         "any_public_investor": 0, "any_corporate_investor": 0, "any_ivc_investor": 1,
         "any_accelerator_investor": 0, "any_lender_investor": 0,
         "public_private_lifetime": 0, "public_private_same_deal": 0,
         "any_grant": 0, "any_vc": 1},
    ]
    return pd.DataFrame(rows)


def _company_investors() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"company_id": "F1", "investor_id": "I1"},   # public, UK (domestic)
            {"company_id": "F1", "investor_id": "I2"},   # ivc, US (non-european)
            {"company_id": "F1", "investor_id": "I3"},   # ivc, Germany (cross-border)
            {"company_id": "F3", "investor_id": "I4"},   # public, France (domestic)
            {"company_id": "F3", "investor_id": "I5"},   # corporate, unknown country
            {"company_id": "F4", "investor_id": "I6"},   # ivc, Germany (domestic)
            {"company_id": "F2", "investor_id": "I2"},   # F2 not invested -> dropped
        ]
    )


def _investors() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"investor_id": "I1", "investor_type_grp": "Public/Government",
             "investor_country": "United Kingdom"},
            {"investor_id": "I2", "investor_type_grp": "Independent VC",
             "investor_country": "United States"},
            {"investor_id": "I3", "investor_type_grp": "Independent VC",
             "investor_country": "Germany"},
            {"investor_id": "I4", "investor_type_grp": "Public/Government",
             "investor_country": "France"},
            {"investor_id": "I5", "investor_type_grp": "Corporate",
             "investor_country": np.nan},
            {"investor_id": "I6", "investor_type_grp": "Independent VC",
             "investor_country": "Germany"},
        ]
    )


def _deals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # F1: grant 2018 -> VC 2020 (grant precedes)
            {"company_id": "F1", "deal_id": "D1", "deal_date": "2018-01-01",
             "stage_group": "Grant", "n_investors": 1, "n_new_investors": 1},
            {"company_id": "F1", "deal_id": "D2", "deal_date": "2020-01-01",
             "stage_group": "Early-stage VC", "n_investors": 3, "n_new_investors": 2},
            # F3: VC 2019 -> grant 2021 (grant does NOT precede)
            {"company_id": "F3", "deal_id": "D3", "deal_date": "2019-01-01",
             "stage_group": "Early-stage VC", "n_investors": 2, "n_new_investors": 2},
            {"company_id": "F3", "deal_id": "D4", "deal_date": "2021-01-01",
             "stage_group": "Grant", "n_investors": 1, "n_new_investors": 1},
            # F4: VC only, no grant
            {"company_id": "F4", "deal_id": "D5", "deal_date": "2022-01-01",
             "stage_group": "Angel/Seed", "n_investors": 1, "n_new_investors": 1},
        ]
    )


def _deal_investors() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"deal_id": "D1", "investor_id": "I1", "is_lead": "No"},
            {"deal_id": "D2", "investor_id": "I2", "is_lead": "Yes"},
            {"deal_id": "D2", "investor_id": "I3", "is_lead": "No"},
            {"deal_id": "D3", "investor_id": "I4", "is_lead": "Yes"},
            {"deal_id": "D5", "investor_id": "I6", "is_lead": "No"},
        ]
    )


def test_type_distribution_uses_invested_relations():
    t18 = build_investor_type_distribution(
        _firm_frame(), _company_investors(), _investors()
    ).set_index("investor_type_grp")
    # F2 is not invested, so its relation is dropped: total relations = 6.
    assert int(t18["n_startups"].sum()) == 6
    # Independent VC: green relations I2, I3 (F1) -> 2; firm F1 has >=1 -> 1/1 green.
    assert t18.loc["Independent VC", "green_n_relations"] == 2
    assert t18.loc["Independent VC", "green_pct_firms"] == 1.0


def test_flags_match_firm_column_means():
    t19 = build_investor_flags(_firm_frame()).set_index("flag")
    # INVESTED green = F1 only -> any_public_investor share = 1.0.
    assert t19.loc["any_public_investor", "green_stat"] == 1.0
    # INVESTED other = F3, F4 -> any_ivc_investor share = 1/2 = 0.5.
    assert t19.loc["any_ivc_investor", "other_stat"] == 0.5
    # median distinct investors: green F1=3; other F3=2,F4=1 -> 1.5.
    assert t19.loc["median_n_investors", "green_stat"] == 3.0
    assert t19.loc["median_n_investors", "other_stat"] == 1.5


def test_grant_to_vc_sequencing():
    t22 = build_grant_to_vc(_firm_frame(), _deals()).set_index("measure")
    # Both a grant and a VC round: F1 (green) and F3 (other) -> 1 each.
    assert t22.loc["n_firms_grant_and_vc", "n_green"] == 1
    assert t22.loc["n_firms_grant_and_vc", "n_others"] == 1
    # F1 grant precedes VC -> green 1.0; F3 grant after VC -> other 0.0.
    assert t22.loc["pct_grant_preceded_vc", "green_stat"] == 1.0
    assert t22.loc["pct_grant_preceded_vc", "other_stat"] == 0.0
    # Months grant->VC for F1: ~24 months, non-negative.
    assert t22.loc["median_months_grant_to_vc", "green_stat"] >= 0


def test_origin_shares_sum_to_one_within_group():
    t23 = build_investor_origin(_firm_frame(), _company_investors(), _investors())
    # I5 has unknown country -> excluded; coverage = 5/6.
    assert abs(t23["country_coverage"].iloc[0] - round(5 / 6, 4)) < 1e-6
    # Shares are rounded to 4dp, so allow a small rounding tolerance.
    assert abs(t23["green_pct_relations"].sum() - 1.0) < 1e-3
    assert abs(t23["other_pct_relations"].sum() - 1.0) < 1e-3
    dom = t23.set_index("origin").loc["domestic"]
    # Green domestic relations: F1's I1 (UK) -> 1 of 3 green known relations.
    assert dom["n_green"] == 1


def test_syndication_is_deal_grain_within_stage():
    t25 = build_syndication(_firm_frame(), _deals(), _deal_investors())
    # Two rows (green/other) per stage present.
    assert set(t25["group"]) == {"Green start-ups", "Other European start-ups"}
    esvc = t25[t25["stage_group"] == "Early-stage VC"].set_index("group")
    # D2 (green) has a lead -> pct_with_lead 1.0; D2 has 3 investors -> multi.
    assert esvc.loc["Green start-ups", "pct_with_lead"] == 1.0
    assert esvc.loc["Green start-ups", "pct_multi_investor"] == 1.0


def test_build_all_has_trio_everywhere(tmp_path):
    result = build_all(
        _firm_frame(), _deals(), _company_investors(), _investors(), _deal_investors()
    )
    trio = {"n_green", "n_others", "n_startups"}
    for name, df in result.tables.items():
        assert trio.issubset(df.columns), f"{name} missing the sample-size trio"
    out = write_outputs(result, tmp_path)
    assert (out / "T4_18_investor_type_distribution.csv").exists()
    assert (tmp_path / "captions_step6.csv").exists()
