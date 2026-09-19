"""Tests for Step 14 (public/private investor participation).

Synthetic frames exercise the classification audit, the in-window participation
flags, the two-denominator participation table, the (1)-(5) regressions, the
grant->VC and public/private sequencing, and the deal-size-by-composition
fallback. They assert the plan's invariants:
- the classification covers 100% of observed investor_type_grp and flags any
  unmapped type;
- no investor-level amount exists, so the amount audit falls back to deal-level
  composition;
- same_deal co-investment is a subset of ever-both;
- firms with no in-window investor relationship get 0 flags / n_investors=0;
- the regressions have columns (1)-(5) with the deal-count control only in (5);
- deal-size-by-composition uses disclosed deals only, never zero-filled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from empirical_analysis.step14_public_private import config
from empirical_analysis.step14_public_private.build import (
    HAVE_STATSMODELS,
    acceptance_report,
    build_all,
    build_amount_audit,
    build_capital_composition,
    build_firm_panel,
    build_grant_vc_sequencing,
    build_investor_mapping,
    build_participation,
    build_pubpriv_sequencing,
    build_regressions,
    build_relations,
    classify_investors,
    write_outputs,
    _round_cols,
    _stars,
)

pytestmark = pytest.mark.skipif(
    not HAVE_STATSMODELS, reason="statsmodels not installed"
)


@pytest.fixture(autouse=True)
def _small_fe_threshold(monkeypatch):
    monkeypatch.setattr(config, "MIN_FE_LEVEL_N", 1)


# --------------------------------------------------------------------------
# Fixtures: a small explicit investor scenario
# --------------------------------------------------------------------------
def _investors() -> pd.DataFrame:
    return pd.DataFrame([
        {"investor_id": "P", "investor_type_grp": "Public/Government"},
        {"investor_id": "V", "investor_type_grp": "Independent VC"},
        {"investor_id": "X", "investor_type_grp": "Accelerator/Incubator"},
    ])


def _in_window() -> pd.DataFrame:
    # G1: grant(d1, public, 2018) + VC(d2, private, 2019) -> both, not same-deal
    # O1: VC(d3) carrying BOTH public and private -> same-deal (subset of both)
    # O2: accelerator(d4) investor only -> has record, no public/private
    # O3: VC(d5) with NO investor rows -> no record
    return pd.DataFrame([
        {"company_id": "G1", "deal_id": "d1", "deal_date": pd.Timestamp("2018-01-01"),
         "rel": 1, "green": 1, "deal_size": 0.5, "stage_group": "Grant"},
        {"company_id": "G1", "deal_id": "d2", "deal_date": pd.Timestamp("2019-01-01"),
         "rel": 2, "green": 1, "deal_size": 2.0, "stage_group": "Early-stage VC"},
        {"company_id": "O1", "deal_id": "d3", "deal_date": pd.Timestamp("2019-01-01"),
         "rel": 2, "green": 0, "deal_size": 3.0, "stage_group": "Early-stage VC"},
        {"company_id": "O2", "deal_id": "d4", "deal_date": pd.Timestamp("2019-01-01"),
         "rel": 1, "green": 0, "deal_size": 1.0, "stage_group": "Accelerator/Incubator"},
        {"company_id": "O3", "deal_id": "d5", "deal_date": pd.Timestamp("2019-01-01"),
         "rel": 2, "green": 0, "deal_size": np.nan, "stage_group": "Early-stage VC"},
    ])


def _deal_investors() -> pd.DataFrame:
    return pd.DataFrame([
        {"deal_id": "d1", "investor_id": "P"},   # G1 grant: public
        {"deal_id": "d2", "investor_id": "V"},   # G1 VC: private
        {"deal_id": "d3", "investor_id": "P"},   # O1 VC: public...
        {"deal_id": "d3", "investor_id": "V"},   # ...and private (same deal)
        {"deal_id": "d4", "investor_id": "X"},   # O2 accelerator (exclude)
        # d5 has no investor rows -> O3 has no record
    ])


def _elig_controls() -> pd.DataFrame:
    return pd.DataFrame([
        {"company_id": "G1", "green": 1, "cohort": "2016-2018",
         "hq_country": "A", "primary_industry_group": "I1", "n_deals_5yr": 2},
        {"company_id": "O1", "green": 0, "cohort": "2016-2018",
         "hq_country": "A", "primary_industry_group": "I1", "n_deals_5yr": 1},
        {"company_id": "O2", "green": 0, "cohort": "2016-2018",
         "hq_country": "B", "primary_industry_group": "I2", "n_deals_5yr": 1},
        {"company_id": "O3", "green": 0, "cohort": "2016-2018",
         "hq_country": "B", "primary_industry_group": "I2", "n_deals_5yr": 1},
    ])


# --------------------------------------------------------------------------
# Classification + amount audit
# --------------------------------------------------------------------------
def test_classification_public_private_exclude():
    inv = classify_investors(_investors())
    by_id = inv.set_index("investor_id")
    assert by_id.loc["P", "analytical_group"] == config.PUBLIC_LABEL
    assert by_id.loc["P", "is_public"] == 1 and by_id.loc["P", "is_private"] == 0
    assert by_id.loc["V", "analytical_group"] == config.PRIVATE_LABEL
    assert by_id.loc["V", "is_private"] == 1 and by_id.loc["V", "is_public"] == 0
    assert by_id.loc["X", "analytical_group"] == config.EXCLUDE_LABEL
    assert by_id.loc["X", "is_public"] == 0 and by_id.loc["X", "is_private"] == 0


def test_mapping_covers_all_and_flags_unmapped():
    investors = pd.concat([_investors(), pd.DataFrame([
        {"investor_id": "Z", "investor_type_grp": "BrandNewType"},
    ])], ignore_index=True)
    di = pd.concat([_deal_investors(), pd.DataFrame([
        {"deal_id": "d1", "investor_id": "Z"},
    ])], ignore_index=True)
    deals = pd.DataFrame([
        {"deal_id": "d1", "company_id": "G1"},
        {"deal_id": "d2", "company_id": "G1"},
        {"deal_id": "d3", "company_id": "O1"},
        {"deal_id": "d4", "company_id": "O2"},
    ])
    mapping = build_investor_mapping(investors, di, deals)
    # BrandNewType is not in ANALYTICAL_GROUP -> surfaced as UNMAPPED
    row = mapping.set_index("investor_type_grp").loc["BrandNewType"]
    assert row["analytical_group"] == "UNMAPPED"
    assert row["n_investors"] == 1
    # known types resolve to their groups and carry relationship/firm counts
    pub = mapping.set_index("investor_type_grp").loc["Public/Government"]
    assert pub["analytical_group"] == config.PUBLIC_LABEL
    assert pub["n_relationships"] >= 1


def test_amount_audit_reports_no_investor_level_amount():
    audit = build_amount_audit(_deal_investors())
    row = audit.iloc[0]
    assert row["has_investor_level_amount"] == 0
    assert "composition" in row["decision"].lower()


# --------------------------------------------------------------------------
# Firm-level participation panel
# --------------------------------------------------------------------------
def test_firm_panel_flags_and_same_deal_subset_of_both():
    rel = build_relations(_in_window(), _deal_investors(), _investors())
    panel = build_firm_panel(_elig_controls(), rel).set_index("company_id")

    # G1: public + private on different deals -> both, NOT same-deal
    assert panel.loc["G1", "any_public_5yr"] == 1
    assert panel.loc["G1", "any_private_5yr"] == 1
    assert panel.loc["G1", "both_public_private_5yr"] == 1
    assert panel.loc["G1", "same_deal_public_private_5yr"] == 0
    assert panel.loc["G1", "n_investors_5yr"] == 2
    assert panel.loc["G1", "has_investor_record_5yr"] == 1

    # O1: one deal carrying both -> same-deal (and both)
    assert panel.loc["O1", "same_deal_public_private_5yr"] == 1
    assert panel.loc["O1", "both_public_private_5yr"] == 1

    # O2: accelerator only -> record, but no public/private
    assert panel.loc["O2", "has_investor_record_5yr"] == 1
    assert panel.loc["O2", "any_public_5yr"] == 0
    assert panel.loc["O2", "any_private_5yr"] == 0
    assert panel.loc["O2", "n_investors_5yr"] == 1

    # O3: no investor rows -> no record, observed zero (not missing)
    assert panel.loc["O3", "has_investor_record_5yr"] == 0
    assert panel.loc["O3", "n_investors_5yr"] == 0

    # invariant: same_deal is a subset of both
    viol = panel[(panel["same_deal_public_private_5yr"] == 1)
                 & (panel["both_public_private_5yr"] != 1)]
    assert len(viol) == 0


def test_participation_two_denominators():
    rel = build_relations(_in_window(), _deal_investors(), _investors())
    panel = build_firm_panel(_elig_controls(), rel)
    part = build_participation(panel).set_index("outcome")
    # invested denominator = firms with a record (G1, O1, O2) = 3
    assert part.loc["any_public_5yr", "n_startups_invested"] == 3
    # eligible denominator = all 4
    assert part.loc["any_public_5yr", "n_startups_eligible"] == 4
    # has_investor_record is 1.0 by construction within the invested sample
    assert part.loc["has_investor_record_5yr", "green_pct_invested"] == 1.0


# --------------------------------------------------------------------------
# Sequencing
# --------------------------------------------------------------------------
def test_grant_vc_sequencing_in_window():
    seq = build_grant_vc_sequencing(_in_window()).set_index("measure")
    # only G1 has both an in-window grant and VC
    assert seq.loc["n_firms_grant_and_vc", "n_green"] == 1
    assert seq.loc["n_firms_grant_and_vc", "n_others"] == 0
    # G1's grant (2018) precedes its VC (2019)
    assert seq.loc["pct_grant_first", "green_stat"] == 1.0


def test_pubpriv_sequencing_ordering():
    rel = build_relations(_in_window(), _deal_investors(), _investors())
    seq = build_pubpriv_sequencing(rel).set_index("measure")
    # firms with both public and private in-window: G1 (green), O1 (other)
    assert seq.loc["n_firms_public_and_private", "n_green"] == 1
    assert seq.loc["n_firms_public_and_private", "n_others"] == 1
    # G1: public (2018) precedes private (2019)
    assert seq.loc["pct_public_first", "green_stat"] == 1.0
    # O1: single deal carries both -> same deal / same date
    assert seq.loc["pct_same_deal", "other_stat"] == 1.0


# --------------------------------------------------------------------------
# Capital by investor composition (disclosed only, never zero-filled)
# --------------------------------------------------------------------------
def test_capital_composition_disclosed_only():
    rel = build_relations(_in_window(), _deal_investors(), _investors())
    comp = build_capital_composition(_in_window(), rel)
    idx = comp.set_index(["composition", "group"])
    # d1 public-only (0.5, green); d2 private-only (2.0, green);
    # d3 mixed (3.0, other); d4 other/neither (1.0, other); d5 excluded (NaN)
    assert idx.loc[("public_only", config.GREEN_LABEL), "median_deal_size"] == 0.5
    assert idx.loc[("private_only", config.GREEN_LABEL), "median_deal_size"] == 2.0
    assert idx.loc[("mixed_public_private", config.OTHER_LABEL), "median_deal_size"] == 3.0
    # a cell with no disclosed deals must be NaN, never 0
    empty = comp[comp["n_deals_disclosed"] == 0]
    assert empty["median_deal_size"].isna().all()


# --------------------------------------------------------------------------
# Regressions (1)-(5)
# --------------------------------------------------------------------------
def _reg_panel() -> pd.DataFrame:
    rows = []
    for i in range(40):
        rows.append({
            "company_id": f"F{i}",
            "green": i % 2,
            "has_investor_record_5yr": 1,
            "any_public_5yr": 1 if i % 3 == 0 else 0,
            "any_private_5yr": 1 if i % 2 == 0 else 0,
            "both_public_private_5yr": 1 if (i % 3 == 0 and i % 2 == 0) else 0,
            "same_deal_public_private_5yr": 1 if i % 6 == 0 else 0,
            "n_deals_5yr": 1 + (i % 4),
            "cohort": "2016-2018" if i % 2 == 0 else "2019-2021",
            "hq_country": "A" if i % 2 == 0 else "B",
            "primary_industry_group": "I1" if i % 3 else "I2",
        })
    return pd.DataFrame(rows)


def test_regressions_have_five_columns_with_dealcount_only_in_five():
    panel = _reg_panel()
    reg, audit = build_regressions(panel, config.INDUSTRY_COL_GROUP)
    assert list(reg.columns) == config.RESULT_COLUMNS
    for outcome, grp in reg.groupby("outcome"):
        assert set(grp["spec"]) == {"spec1", "spec2", "spec3", "spec4", "spec5"}
        assert set(grp["column"]) == {"(1)", "(2)", "(3)", "(4)", "(5)"}
        # deal-count control only in column (5)
        assert (grp.loc[grp["column"] == "(5)", "deal_count_control"] == 1).all()
        assert (grp.loc[grp["column"] != "(5)", "deal_count_control"] == 0).all()
        # every spec runs on the full invested sample
        assert (grp["n"] == len(panel)).all()
    # audit reconciles the trio and one row per firm
    a = pd.DataFrame(audit)
    assert (a["n_green"] + a["n_other"] == a["n"]).all()
    assert (a["n"] == a["n_unique_firms"]).all()


def test_stars_and_rounding_helpers():
    assert _stars(0.001) == "***"
    assert _stars(0.03) == "**"
    assert _stars(0.08) == "*"
    assert _stars(0.5) == ""
    df = pd.DataFrame([{"coef": 0.123456, "coef_pp": 12.34567}])
    out = _round_cols(df)
    assert out["coef"].iloc[0] == round(0.123456, config.DECIMALS)
    assert out["coef_pp"].iloc[0] == round(12.34567, config.DECIMALS_PP)


# --------------------------------------------------------------------------
# Full build_all integration
# --------------------------------------------------------------------------
def _integration_frames():
    firm_rows, panel_rows, deal_rows, di_rows = [], [], [], []
    inv_rows = [
        {"investor_id": "P", "investor_type_grp": "Public/Government"},
        {"investor_id": "V", "investor_type_grp": "Independent VC"},
        {"investor_id": "C", "investor_type_grp": "Corporate"},
        {"investor_id": "X", "investor_type_grp": "Accelerator/Incubator"},
    ]
    for i in range(40):
        cid = f"F{i}"
        yf = 2017 + (i % 2)
        green = i % 2
        country = "A" if i % 2 == 0 else "B"
        ind = "I1" if i % 3 else "I2"
        firm_rows.append({"company_id": cid, "green": green, "year_founded": yf,
                          "green_signal_group": "none", "cohort": "2016-2018"})
        panel_rows.append({"company_id": cid, "green": green, "cohort": "2016-2018",
                           "hq_country": country, "primary_industry_group": ind,
                           "n_deals_5yr": 2})
        dg, dv = f"{cid}g", f"{cid}v"
        deal_rows.append({"company_id": cid, "deal_id": dg,
                          "deal_date": pd.Timestamp(f"{yf + 1}-01-01"),
                          "stage_group": "Grant",
                          "deal_size": float(1 + i) if i % 2 == 0 else np.nan,
                          "size_is_actual": 1 if i % 2 == 0 else 0})
        deal_rows.append({"company_id": cid, "deal_id": dv,
                          "deal_date": pd.Timestamp(f"{yf + 2}-01-01"),
                          "stage_group": "Early-stage VC",
                          "deal_size": float(2 + i), "size_is_actual": 1})
        # public on the grant deal for half the firms
        if i % 2 == 0:
            di_rows.append({"deal_id": dg, "investor_id": "P"})
        # private on the VC deal for most firms
        if i % 3 != 0:
            di_rows.append({"deal_id": dv, "investor_id": "V"})
        # some firms get both public + private on the same VC deal
        if i % 4 == 0:
            di_rows.append({"deal_id": dv, "investor_id": "P"})
            di_rows.append({"deal_id": dv, "investor_id": "C"})
        # a couple firms only see an accelerator (record but no public/private)
        if i % 7 == 0:
            di_rows.append({"deal_id": dg, "investor_id": "X"})
    return (pd.DataFrame(panel_rows), pd.DataFrame(firm_rows),
            pd.DataFrame(deal_rows), pd.DataFrame(di_rows), pd.DataFrame(inv_rows))


def test_build_all_and_acceptance(tmp_path):
    panel5b, firm, deals, di, inv = _integration_frames()
    result = build_all(panel5b, firm, deals, di, inv,
                       industry_col=config.INDUSTRY_COL_GROUP)

    for name in config.STEP14_OUTPUT_NAMES:
        assert name in result.tables or name in (config.OUT_FIRM_PANEL,
                                                 config.SAMPLE_AUDIT,
                                                 config.CAPTIONS_FILE)
    assert len(result.firm_panel) == int(result.diagnostics["n_eligible"])

    lines = acceptance_report(result)
    assert not any("FAIL" in ln for ln in lines), "\n".join(lines)

    write_outputs(result, tmp_path)
    for name in (config.OUT_MAPPING, config.OUT_PARTICIPATION, config.OUT_REGRESSION,
                 config.OUT_GRANT_VC, config.OUT_SEQUENCING,
                 config.OUT_CAPITAL_COMPOSITION, config.SAMPLE_AUDIT,
                 config.CAPTIONS_FILE):
        assert (tmp_path / f"{name}.csv").exists()
    assert (tmp_path / f"{config.OUT_FIRM_PANEL}.parquet").exists()
    # no LaTeX / formatted tables
    assert not list(tmp_path.glob("*.tex"))
