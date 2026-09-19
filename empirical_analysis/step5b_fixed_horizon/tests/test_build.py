"""Tests for Step 5b (fixed five-year horizon).

Synthetic firm + deal frames exercise the window construction and the four
tables. They assert the plan's invariants:
- a deal at year_founded + 6 is truncated out of the window;
- a firm founded in 2021 is excluded from the headline eligible set;
- a deal dated before founding (deal_year < year_founded) is flagged and dropped;
- a firm with an undisclosed in-window deal_size adds to coverage but not to the
  amount median (amounts are never zero-filled);
- every table carries the n_green / n_others / n_startups trio;
- the acceptance report passes with no FAIL.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from empirical_analysis.step5b_fixed_horizon import config
from empirical_analysis.step5b_fixed_horizon.build import (
    acceptance_report,
    build_all,
    build_access,
    build_capital,
    build_first_channel,
    build_firm_audit,
    build_firm_panel,
    build_timing,
    prepare_window,
    write_outputs,
)


def _firm_frame() -> pd.DataFrame:
    return pd.DataFrame([
        # green, founded 2016: in-window Grant (2017); VC at 2022 is +6 -> dropped
        {"company_id": "G1", "green": 1, "year_founded": 2016,
         "green_signal_group": "Stage 1", "cohort": "2016-2018"},
        # green, founded 2018: single in-window VC (2018), size UNDISCLOSED
        {"company_id": "G2", "green": 1, "year_founded": 2018,
         "green_signal_group": "Stage 2+3", "cohort": "2016-2018"},
        # other, founded 2017: 2016 VC is impossible (dropped); 2019 VC in-window
        {"company_id": "O1", "green": 0, "year_founded": 2017,
         "green_signal_group": "none", "cohort": "2016-2018"},
        # other, founded 2020: no deals at all
        {"company_id": "O2", "green": 0, "year_founded": 2020,
         "green_signal_group": "none", "cohort": "2019-2021"},
        # green, founded 2021: INELIGIBLE (window incomplete) -> excluded
        {"company_id": "X1", "green": 1, "year_founded": 2021,
         "green_signal_group": "Stage 1", "cohort": "2019-2021"},
    ])


def _deals_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"company_id": "G1", "deal_id": "d1", "deal_date": pd.Timestamp("2017-06-01"),
         "stage_group": "Grant", "deal_size": 2.0, "size_is_actual": 1},
        {"company_id": "G1", "deal_id": "d2", "deal_date": pd.Timestamp("2022-01-01"),
         "stage_group": "Early-stage VC", "deal_size": 8.0, "size_is_actual": 1},
        {"company_id": "G2", "deal_id": "d3", "deal_date": pd.Timestamp("2018-03-01"),
         "stage_group": "Early-stage VC", "deal_size": np.nan, "size_is_actual": 0},
        {"company_id": "O1", "deal_id": "d4", "deal_date": pd.Timestamp("2016-01-01"),
         "stage_group": "Later-stage VC", "deal_size": 5.0, "size_is_actual": 1},
        {"company_id": "O1", "deal_id": "d5", "deal_date": pd.Timestamp("2019-01-01"),
         "stage_group": "Later-stage VC", "deal_size": 10.0, "size_is_actual": 1},
        {"company_id": "X1", "deal_id": "d6", "deal_date": pd.Timestamp("2021-05-01"),
         "stage_group": "Early-stage VC", "deal_size": 4.0, "size_is_actual": 1},
    ])


def _deal_investors_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"deal_id": "d1", "investor_id": "i_pub"},                 # G1 grant: public
        {"deal_id": "d3", "investor_id": "i_ivc"},                 # G2 VC: private
        {"deal_id": "d5", "investor_id": "i_pub"},                 # O1 VC: public...
        {"deal_id": "d5", "investor_id": "i_ivc"},                 # ...and private
    ])


def _investors_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"investor_id": "i_pub", "investor_type_grp": "Public/Government"},
        {"investor_id": "i_ivc", "investor_type_grp": "Independent VC"},
    ])


def test_eligibility_and_window():
    elig, iw, diag = prepare_window(_firm_frame(), _deals_frame())
    # 2021 firm excluded from headline
    assert set(elig["company_id"]) == {"G1", "G2", "O1", "O2"}
    assert diag["n_eligible"] == 4
    # deal at year_founded+6 (G1 2022) truncated out
    assert "d2" not in set(iw["deal_id"])
    assert diag["n_after_horizon_deals"] == 1
    # impossible deal (O1 2016 < founded 2017) flagged and dropped
    assert "d4" not in set(iw["deal_id"])
    assert diag["n_impossible_deals"] == 1
    assert diag["n_impossible_firms"] == 1
    # in-window deals are exactly d1, d3, d5
    assert set(iw["deal_id"]) == {"d1", "d3", "d5"}
    assert diag["max_rel_in_window"] <= config.WINDOW_YEARS


def test_access_denominator_is_eligible():
    elig, iw, _ = prepare_window(_firm_frame(), _deals_frame())
    acc = build_access(elig, iw).set_index("financing_type")
    # any_financing: green G1,G2 -> 1.0 ; other O1 (not O2) -> 0.5
    assert acc.loc["any_financing", "green_pct"] == 1.0
    assert acc.loc["any_financing", "other_pct"] == 0.5
    # any_grant only G1 (green)
    assert acc.loc["any_grant", "n_green"] == 1
    assert acc.loc["any_grant", "n_others"] == 0


def test_timing_over_firms_with_event():
    _, iw, _ = prepare_window(_firm_frame(), _deals_frame())
    tim = build_timing(iw).set_index("measure")
    # green first-financing rel: G1=1, G2=0 -> median 0.5 ; other O1=2
    assert tim.loc["years_to_first_financing", "green_median"] == 0.5
    assert tim.loc["years_to_first_financing", "other_median"] == 2.0
    # first grant exists only for green (G1)
    assert tim.loc["years_to_first_grant", "n_green"] == 1
    assert tim.loc["years_to_first_grant", "n_others"] == 0


def test_capital_never_zero_fills_undisclosed():
    elig, iw, _ = prepare_window(_firm_frame(), _deals_frame())
    cap = build_capital(elig, iw).set_index("group")
    green = cap.loc[config.GREEN_LABEL]
    # G1 (2.0 disclosed) + G2 (undisclosed) financed the window
    assert green["n_firms_financed_window"] == 2
    # only G1 has a disclosed amount -> observed = 1, median = 2.0 (never 0)
    assert green["n_firms_observed"] == 1
    assert green["sum_median"] == 2.0
    assert green["firm_coverage"] == 0.5
    other = cap.loc[config.OTHER_LABEL]
    assert other["sum_median"] == 10.0
    assert other["deal_coverage"] == 1.0


def test_first_channel_stage_and_backing():
    _, iw, _ = prepare_window(_firm_frame(), _deals_frame())
    fc = build_first_channel(iw, _deal_investors_frame(), _investors_frame())
    stage = fc[fc["metric"] == "first_stage"].set_index("category")
    # G1's first in-window deal is the Grant (2022 VC excluded)
    assert stage.loc["Grant", "n_green"] == 1
    backing = fc[fc["metric"] == "first_backing"].set_index("category")
    # G1 grant -> public_only ; G2 VC -> private_only ; O1 -> public_and_private
    assert backing.loc["public_only", "n_green"] == 1
    assert backing.loc["private_only", "n_green"] == 1
    assert backing.loc["public_and_private", "n_others"] == 1


def test_every_table_has_trio_and_acceptance_passes(tmp_path):
    result = build_all(
        _firm_frame(), _deals_frame(),
        _deal_investors_frame(), _investors_frame(),
    )
    for name, df in result.tables.items():
        assert {"n_green", "n_others", "n_startups"} <= set(df.columns), name
        assert (df["n_green"] + df["n_others"] == df["n_startups"]).all(), name

    lines = acceptance_report(result)
    assert not any("FAIL" in ln for ln in lines), "\n".join(lines)

    # write_outputs emits only first5-scoped files, never Step 5 names
    write_outputs(result, tmp_path)
    produced = {p.stem for p in tmp_path.glob("*.csv")} | {
        p.stem for p in tmp_path.glob("*.png")
    } | {p.stem for p in tmp_path.glob("*.parquet")}
    assert produced & config.STEP5_PROTECTED_NAMES == set()
    assert (tmp_path / f"{config.OUT_ACCESS}.csv").exists()
    assert (tmp_path / f"{config.CAPTIONS_FILE}.csv").exists()
    assert (tmp_path / f"{config.FIRM_PANEL}.parquet").exists()
    assert (tmp_path / f"{config.FIRM_AUDIT}.csv").exists()


# --------------------------------------------------------------------------
# first5_analysis: canonical one-row-per-eligible-firm dataset + audit
# --------------------------------------------------------------------------
def _firm_frame_with_controls() -> pd.DataFrame:
    firm = _firm_frame()
    countries = {"G1": "Germany", "G2": "France", "O1": "Spain",
                 "O2": "Italy", "X1": "Poland"}
    industries = {"G1": "Energy", "G2": "Energy", "O1": "IT",
                  "O2": "IT", "X1": "IT"}
    firm["hq_country"] = firm["company_id"].map(countries)
    firm["primary_industry_group"] = firm["company_id"].map(industries)
    return firm


def test_firm_panel_one_row_per_eligible_firm_with_controls():
    firm = _firm_frame_with_controls()
    elig, iw, _ = prepare_window(firm, _deals_frame())
    panel = build_firm_panel(elig, iw, firm)

    # exactly the four eligible firms (X1 founded 2021 is excluded)
    assert set(panel["company_id"]) == {"G1", "G2", "O1", "O2"}
    assert len(panel) == len(elig) == 4
    assert (panel["eligible_first5"] == 1).all()
    assert (panel["window_end"] == panel["window_start"] + config.WINDOW_YEARS).all()

    # controls carried through from the firm table (no fan-out / duplication)
    row = panel.set_index("company_id")
    assert row.loc["G1", "hq_country"] == "Germany"
    assert row.loc["G1", "primary_industry_group"] == "Energy"


def test_firm_panel_missing_lags_and_capital_are_nan_not_zero():
    firm = _firm_frame_with_controls()
    elig, iw, _ = prepare_window(firm, _deals_frame())
    panel = build_firm_panel(elig, iw, firm).set_index("company_id")

    # O2 has no deals at all: every _5yr flag/count is 0, but lags/capital are NaN
    assert panel.loc["O2", "any_financing_5yr"] == 0
    assert panel.loc["O2", "n_deals_5yr"] == 0
    assert pd.isna(panel.loc["O2", "first_financing_lag_5yr"])
    assert pd.isna(panel.loc["O2", "disclosed_capital_5yr"])
    assert panel.loc["O2", "has_disclosed_capital_5yr"] == 0

    # G2's only in-window deal is undisclosed: financed but capital stays NaN
    assert panel.loc["G2", "any_financing_5yr"] == 1
    assert panel.loc["G2", "has_disclosed_capital_5yr"] == 0
    assert pd.isna(panel.loc["G2", "disclosed_capital_5yr"])
    assert not pd.isna(panel.loc["G2", "first_financing_lag_5yr"])  # event observed

    # G1 has a disclosed grant of 2.0 in-window (the +6 VC deal is truncated out)
    assert panel.loc["G1", "disclosed_capital_5yr"] == 2.0
    assert panel.loc["G1", "has_disclosed_capital_5yr"] == 1
    assert panel.loc["G1", "first_grant_lag_5yr"] == 1.0
    assert pd.isna(panel.loc["G1", "first_vc_lag_5yr"])  # only VC deal is out-of-window


def test_firm_audit_reconciles_to_access_table_and_passes():
    firm = _firm_frame_with_controls()
    elig, iw, diag = prepare_window(firm, _deals_frame())
    panel = build_firm_panel(elig, iw, firm)
    access = build_access(elig, iw)
    audit = build_firm_audit(panel, diag, access)

    assert "pass" in audit.columns
    assert audit["pass"].all(), audit[~audit["pass"]]
    # every any_*_5yr flag has a green + other reconciliation row
    checks = set(audit["check"])
    assert any(c.startswith("reconcile_any_financing_5yr") for c in checks)
    assert any(c.startswith("reconcile_any_grant_5yr") for c in checks)


def test_build_all_populates_firm_panel_and_audit():
    result = build_all(
        _firm_frame_with_controls(), _deals_frame(),
        _deal_investors_frame(), _investors_frame(),
    )
    assert len(result.firm_panel) == int(result.diagnostics["n_eligible"])
    assert len(result.firm_audit) > 0
    assert result.firm_audit["pass"].all()
