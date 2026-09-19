"""Tests for the pure figure-prep helpers in make_figures.

These exercise only the pandas data-prep (`prep_*`) functions -- no matplotlib
or geopandas is imported -- so they run anywhere. They assert the plan's
invariants: cohort composition is within-group (sums to ~100% per group) and
reproduces the expected percentages; financing/public-private outcomes keep
their fixed order and are scaled to percent; the investor-type figure is
restricted to the nine categories and sorted by green share descending; and
Figure 6 selects the top-10 countries by green count in that order.
"""

from __future__ import annotations

import pandas as pd
import pytest

from empirical_analysis.make_figures import (
    INVESTOR_TYPES_9,
    prep_cohort_composition,
    prep_financing_access,
    prep_firms_vs_capital,
    prep_investor_type,
    prep_public_private,
)


def test_cohort_composition_is_within_group_and_reconciles():
    df = pd.DataFrame({
        "cohort": ["2016-2018", "2019-2021", "2022-2024", "2025-2026"],
        "green_share": [0.127, 0.1597, 0.0497, 0.0124],   # ignored on purpose
        "n_green": [2240, 3264, 2445, 357],
        "n_others": [15399, 17173, 46714, 28413],
    })
    comp = prep_cohort_composition(df)
    # each group's four bars sum to ~100%
    assert comp["green_pct"].sum() == pytest.approx(100.0, abs=1e-6)
    assert comp["other_pct"].sum() == pytest.approx(100.0, abs=1e-6)
    # reproduces the documented (approximate) percentages
    assert comp["green_pct"].tolist() == pytest.approx([27.0, 39.3, 29.4, 4.3], abs=0.15)
    assert comp["other_pct"].tolist() == pytest.approx([14.3, 16.0, 43.4, 26.4], abs=0.15)
    # order preserved (chronological, file order)
    assert comp["cohort"].tolist() == [
        "2016-2018", "2019-2021", "2022-2024", "2025-2026"]


def test_financing_access_order_labels_and_scaling():
    df = pd.DataFrame({
        "financing_type": ["any_grant", "any_financing", "any_accelerator", "any_vc"],
        "green_pct": [0.1938, 0.8441, 0.4777, 0.5253],
        "other_pct": [0.1014, 0.8012, 0.3807, 0.5222],
    })
    acc = prep_financing_access(df)
    # fixed order regardless of input order
    assert acc["outcome"].tolist() == [
        "any_financing", "any_vc", "any_grant", "any_accelerator"]
    assert acc["label"].iloc[0] == "Any recorded financing"
    assert acc["green_pct"].iloc[0] == pytest.approx(84.41)
    assert acc["other_pct"].iloc[2] == pytest.approx(10.14)


def test_public_private_order_and_scaling():
    df = pd.DataFrame({
        "outcome": ["same_deal_public_private", "any_public",
                    "both_public_private", "any_private"],
        "green_share": [0.0589, 0.2528, 0.1826, 0.6704],
        "other_share": [0.0397, 0.1636, 0.1206, 0.7108],
    })
    pp = prep_public_private(df)
    assert pp["outcome"].tolist() == [
        "any_public", "any_private", "both_public_private", "same_deal_public_private"]
    assert pp["label"].tolist()[0] == "Any public investor"
    assert pp["green_pct"].iloc[0] == pytest.approx(25.28)


def test_investor_type_filtered_to_nine_and_sorted_by_green_desc():
    rows = []
    # long format: investor_type x group (green/other) with share_with_type
    shares = {
        "Accelerator/Incubator": (0.62, 0.52),
        "Independent VC": (0.46, 0.50),
        "Public/Government": (0.25, 0.16),
        "Corporate": (0.31, 0.23),
        "PE/Growth": (0.17, 0.17),
        "Angel": (0.18, 0.24),
        "Impact Investing": (0.12, 0.03),
        "Lender/Debt": (0.03, 0.02),
        "Family Office": (0.06, 0.05),
        "Other/Unclassified": (0.11, 0.09),   # must be dropped
    }
    for t, (g, o) in shares.items():
        rows.append({"investor_type": t, "group": "green", "share_with_type": g})
        rows.append({"investor_type": t, "group": "other", "share_with_type": o})
    it = prep_investor_type(pd.DataFrame(rows))
    # only the nine meaningful categories, Other/Unclassified excluded
    assert set(it["investor_type"]) == set(INVESTOR_TYPES_9)
    assert "Other/Unclassified" not in set(it["investor_type"])
    # sorted by green share descending
    assert it["green_pct"].tolist() == sorted(it["green_pct"].tolist(), reverse=True)
    assert it["investor_type"].iloc[0] == "Accelerator/Incubator"  # 62% green


def test_firms_vs_capital_top10_by_n_green_in_order():
    df = pd.DataFrame({
        "country": [f"C{i}" for i in range(15)],
        "n_green": [100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 9, 8, 7, 6, 5],
        "green_firm_share": [0.1] * 15,
        "green_funding_share_total_raised": [0.2] * 15,
    })
    fc = prep_firms_vs_capital(df, n=10)
    assert len(fc) == 10
    assert fc["country"].tolist() == [f"C{i}" for i in range(10)]  # by n_green desc
    assert fc["firm_share_pct"].iloc[0] == pytest.approx(10.0)
    assert fc["capital_share_pct"].iloc[0] == pytest.approx(20.0)
