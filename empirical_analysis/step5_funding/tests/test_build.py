"""Tests for Step 5 (funding).

A small synthetic firm table plus a deals table exercise the funding builders:
- N1: non-financed firms never enter amount medians.
- N2: access shares use the full population as the denominator.
- R4: a firm whose relevant first deal is too recent is excluded from the
  progression / interval measures.
- the Grant row is present in T4.16.
- every analytical table ends with the n_green / n_others / n_startups trio.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from empirical_analysis.step5_funding.build import (
    build_all,
    build_deal_size_by_stage,
    build_funding_access,
    build_funding_access_by_cohort,
    build_stage_composition,
    build_total_raised_by_cohort,
    build_trajectories,
    write_outputs,
)

_NF = dict(  # shared not-financed defaults
    financed=0, total_raised=np.nan, last_deal_size=np.nan, median_deal_size=np.nan,
    n_deals=0, n_deals_with_size=0, any_vc=0, any_grant=0, any_debt=0,
    any_accelerator=0, any_growth_pe=0, any_crowdfunding=0,
    first_deal_size=np.nan, first_funding_lag=np.nan, first_vc_lag=np.nan,
)


def _firm_frame() -> pd.DataFrame:
    rows = [
        # green, financed, grant + early VC (first deal is a Grant in 2017)
        {"company_id": "F1", "green": 1, "green_signal_group": "Stage 1",
         "cohort": "2016-2018", "age_years": 9, "financed": 1, "total_raised": 5.0,
         "last_deal_size": 6.0, "median_deal_size": 4.0, "n_deals": 2,
         "n_deals_with_size": 2, "any_vc": 1, "any_grant": 1, "any_debt": 0,
         "any_accelerator": 0, "any_growth_pe": 0, "any_crowdfunding": 0,
         "first_deal_size": 2.0, "first_funding_lag": 0, "first_vc_lag": 2},
        # green, NOT financed
        {"company_id": "F2", "green": 1, "green_signal_group": "Stage 2+3",
         "cohort": "2019-2021", "age_years": 6, **_NF},
        # other, financed, single early-VC deal
        {"company_id": "F3", "green": 0, "green_signal_group": "none",
         "cohort": "2016-2018", "age_years": 9, "financed": 1, "total_raised": 12.0,
         "last_deal_size": 12.0, "median_deal_size": 12.0, "n_deals": 1,
         "n_deals_with_size": 1, "any_vc": 1, "any_grant": 0, "any_debt": 0,
         "any_accelerator": 0, "any_growth_pe": 0, "any_crowdfunding": 0,
         "first_deal_size": 12.0, "first_funding_lag": 0, "first_vc_lag": 0},
        # other, NOT financed
        {"company_id": "F4", "green": 0, "green_signal_group": "none",
         "cohort": "2022-2024", "age_years": 3, **_NF},
        # other, financed, grant only, no recorded size
        {"company_id": "F5", "green": 0, "green_signal_group": "none",
         "cohort": "2019-2021", "age_years": 7, "financed": 1, "total_raised": 3.0,
         "last_deal_size": np.nan, "median_deal_size": np.nan, "n_deals": 1,
         "n_deals_with_size": 0, "any_vc": 0, "any_grant": 1, "any_debt": 0,
         "any_accelerator": 0, "any_growth_pe": 0, "any_crowdfunding": 0,
         "first_deal_size": np.nan, "first_funding_lag": 1, "first_vc_lag": np.nan},
        # green, financed, recent seed (2026) -> excluded from progression (R4)
        {"company_id": "F6", "green": 1, "green_signal_group": "Stage 1",
         "cohort": "2025-2026", "age_years": 0, "financed": 1, "total_raised": 1.0,
         "last_deal_size": 1.0, "median_deal_size": 1.0, "n_deals": 1,
         "n_deals_with_size": 1, "any_vc": 1, "any_grant": 0, "any_debt": 0,
         "any_accelerator": 0, "any_growth_pe": 0, "any_crowdfunding": 0,
         "first_deal_size": 1.0, "first_funding_lag": 0, "first_vc_lag": 0},
        # other, financed, seed 2018 -> early VC 2020 (progresses)
        {"company_id": "F7", "green": 0, "green_signal_group": "none",
         "cohort": "2016-2018", "age_years": 8, "financed": 1, "total_raised": 8.0,
         "last_deal_size": 7.0, "median_deal_size": 4.5, "n_deals": 2,
         "n_deals_with_size": 2, "any_vc": 1, "any_grant": 0, "any_debt": 0,
         "any_accelerator": 0, "any_growth_pe": 0, "any_crowdfunding": 0,
         "first_deal_size": 2.0, "first_funding_lag": 0, "first_vc_lag": 2},
    ]
    return pd.DataFrame(rows)


def _deals_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"company_id": "F1", "deal_date": "2017-06-01", "stage_group": "Grant",
             "deal_size": 2.0, "size_is_actual": 1, "post_valuation": np.nan,
             "is_first_deal": 1},
            {"company_id": "F1", "deal_date": "2019-06-01", "stage_group": "Early-stage VC",
             "deal_size": 6.0, "size_is_actual": 1, "post_valuation": 20.0,
             "is_first_deal": 0},
            {"company_id": "F3", "deal_date": "2017-01-01", "stage_group": "Early-stage VC",
             "deal_size": 12.0, "size_is_actual": 1, "post_valuation": 40.0,
             "is_first_deal": 1},
            {"company_id": "F5", "deal_date": "2020-01-01", "stage_group": "Grant",
             "deal_size": np.nan, "size_is_actual": 0, "post_valuation": np.nan,
             "is_first_deal": 1},
            {"company_id": "F6", "deal_date": "2026-01-01", "stage_group": "Angel/Seed",
             "deal_size": 1.0, "size_is_actual": 1, "post_valuation": np.nan,
             "is_first_deal": 1},
            {"company_id": "F7", "deal_date": "2018-01-01", "stage_group": "Angel/Seed",
             "deal_size": 2.0, "size_is_actual": 1, "post_valuation": np.nan,
             "is_first_deal": 1},
            {"company_id": "F7", "deal_date": "2020-01-01", "stage_group": "Early-stage VC",
             "deal_size": 7.0, "size_is_actual": 1, "post_valuation": 15.0,
             "is_first_deal": 0},
        ]
    )


def test_access_uses_full_population_denominator():
    # N2: 3 green firms (F1, F2, F6); 2 are financed (F1, F6) -> 2/3.
    t49 = build_funding_access(_firm_frame()).set_index("financing_type")
    assert t49.loc["any_financing", "green_pct"] == round(2 / 3, 4)
    assert t49.loc["any_financing", "n_green"] == 2
    # other: 4 firms (F3, F4, F5, F7); 3 financed -> 3/4.
    assert t49.loc["any_financing", "other_pct"] == 0.75


def test_access_by_cohort_reconciles_and_uses_cohort_denominator():
    t49b = build_funding_access_by_cohort(_firm_frame())
    # Four headline flags x four cohorts.
    assert set(t49b["financing_type"]) == {
        "any_financing", "any_vc", "any_grant", "any_accelerator"}
    fin = t49b[t49b["financing_type"] == "any_financing"].set_index("cohort")
    # 2016-2018: green F1 (financed) of 1 green -> 1.0; other F3,F7 financed of 2 -> 1.0.
    assert fin.loc["2016-2018", "green_pct"] == 1.0
    assert fin.loc["2016-2018", "green_n_cohort"] == 1
    assert fin.loc["2016-2018", "other_pct"] == 1.0
    assert fin.loc["2016-2018", "other_n_cohort"] == 2
    # 2019-2021: green F2 not financed of 1 -> 0.0; other F5 financed of 1 -> 1.0.
    assert fin.loc["2019-2021", "green_pct"] == 0.0
    assert fin.loc["2019-2021", "other_pct"] == 1.0
    # Cohort split reconciles with the overall T4.9 any_financing count (5 financed).
    t49 = build_funding_access(_firm_frame()).set_index("financing_type")
    assert int(fin["n_startups"].sum()) == int(t49.loc["any_financing", "n_startups"])
    # Thin cohorts (fewer than 30 green) are flagged.
    assert (t49b["low_n_flag"] == 1).all()


def test_amounts_exclude_non_financed():
    # N1: F2 is green but not financed -> never contributes a total_raised value.
    t10 = build_total_raised_by_cohort(_firm_frame())
    tr = t10[t10["amount_field"] == "total_raised"]
    # Only 5 financed firms carry total_raised (F1, F3, F5, F6, F7).
    assert int(tr["n_startups"].sum()) == 5
    g_2016 = tr[tr["cohort"] == "2016-2018"].iloc[0]
    assert g_2016["green_median"] == 5.0   # only F1
    assert g_2016["n_green"] == 1


def test_grant_row_present_in_deal_size():
    t16 = build_deal_size_by_stage(_firm_frame(), _deals_frame()).set_index("stage_group")
    assert "Grant" in t16.index
    # Only F1's grant carries a size (2.0); F5's grant has no size.
    assert t16.loc["Grant", "green_median"] == 2.0
    assert t16.loc["Grant", "n_startups"] == 1


def test_stage_composition_is_deal_grain():
    t15 = build_stage_composition(_firm_frame(), _deals_frame())
    # 7 deal rows in total.
    assert int(t15["n_startups"].sum()) == 7


def test_progression_censors_recent_firm():
    # R4: F6 (seed in 2026) is excluded from seed->early; F7 (seed 2018) progresses.
    t17 = build_trajectories(_firm_frame(), _deals_frame()).set_index("measure")
    row = t17.loc["share_seed_to_early_vc"]
    assert row["n_green"] == 0          # F6 excluded by the window
    assert row["n_others"] == 1         # F7 only
    assert row["other_stat"] == 1.0     # F7 progressed to Early-stage VC


def test_build_all_has_trio_everywhere(tmp_path):
    result = build_all(_firm_frame(), _deals_frame())
    trio = {"n_green", "n_others", "n_startups"}
    for name, df in result.tables.items():
        assert trio.issubset(df.columns), f"{name} missing the sample-size trio"
    out = write_outputs(result, tmp_path)
    assert (out / "T4_09_funding_access.csv").exists()
    assert (tmp_path / "captions_step5.csv").exists()
