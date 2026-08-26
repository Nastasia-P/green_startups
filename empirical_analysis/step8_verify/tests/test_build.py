"""Tests for Step 8 (verification).

The structural checks are exercised directly on small synthetic tables: trio identity,
shares summing to 1, medians inside quartiles, low-n flag integrity, source totals and
the stale-file guard. Population anchors are tested with fixture-scaled values via
monkeypatch. A write round-trip confirms the reconciliation CSV is emitted.
"""

from __future__ import annotations

import pandas as pd

from empirical_analysis.step8_verify import checks, config
from empirical_analysis.step8_verify.build import Step8Result, write_outputs


def _status(rows, check_id):
    for r in rows:
        if r["check_id"] == check_id:
            return r["status"]
    raise KeyError(check_id)


def _trio(g, o):
    return {"n_green": g, "n_others": o, "n_startups": [a + b for a, b in zip(g, o)]}


def test_trio_identity_pass_and_fail():
    good = pd.DataFrame(_trio([1, 2], [3, 4]))
    bad = pd.DataFrame({"n_green": [1], "n_others": [2], "n_startups": [99]})
    rows = checks.check_trio_identity({"good": good, "bad": bad})
    assert _status(rows, "trio_identity.good") == "PASS"
    assert _status(rows, "trio_identity.bad") == "FAIL"


def test_shares_sum_t4_14():
    ok = pd.DataFrame({"green_pct": [0.4, 0.6], "other_pct": [0.5, 0.5],
                       **_trio([2, 3], [4, 5])})
    broken = pd.DataFrame({"green_pct": [0.4, 0.4], "other_pct": [0.5, 0.5],
                           **_trio([2, 3], [4, 5])})
    rows_ok = checks.check_shares_sum({"T4_14_first_financing_type": ok})
    assert _status(rows_ok, "shares_sum.t4_14_green") == "PASS"
    rows_bad = checks.check_shares_sum({"T4_14_first_financing_type": broken})
    assert _status(rows_bad, "shares_sum.t4_14_green") == "FAIL"


def test_median_in_iqr_catches_inversion():
    df = pd.DataFrame({
        "green_q25": [1.0, 5.0], "green_median": [2.0, 4.0], "green_q75": [3.0, 6.0],
        "other_q25": [1.0, 1.0], "other_median": [2.0, 2.0], "other_q75": [3.0, 3.0],
    })
    # Row 2 green: median 4.0 with q75 6.0 fine, q25 5.0 -> 5 <= 4 is False -> violation.
    rows = checks.check_median_in_iqr({"T4_10_total_raised_by_cohort": df})
    assert _status(rows, "median_in_iqr.T4_10_total_raised_by_cohort") == "FAIL"


def test_low_n_flag_mismatch():
    df = pd.DataFrame({"n_green": [5, 40], "low_n_flag": [0, 0],  # 5<30 should be 1
                       "n_others": [1, 1], "n_startups": [6, 41]})
    rows = checks.check_low_n_flag({"T4_26_green_share_firms_vs_capital": df})
    assert _status(rows, "low_n_flag.T4_26_green_share_firms_vs_capital") == "FAIL"
    assert _status(rows, "low_n_flag.present.T4_26_green_share_firms_vs_capital") == "PASS"


def test_source_totals_deal_mismatch():
    t15 = pd.DataFrame({"stage_group": ["A", "B"], **_trio([2, 3], [4, 6])})
    # n_startups sum = 6 + 9 = 15; deals has 10 rows -> mismatch.
    deals = pd.DataFrame({"company_id": [f"F{i}" for i in range(10)]})
    firm = pd.DataFrame({"company_id": ["F1"], "n_investors_lifetime": [1]})
    rows = checks.check_source_totals({"T4_15_stage_composition": t15}, firm, deals,
                                      pd.DataFrame())
    assert _status(rows, "source_totals.t4_15_deals") == "FAIL"


def test_stale_file_guard():
    rerun = pd.DataFrame({"country": ["DE", "FR"], "green_firm_share": [0.5, 0.3],
                          **_trio([2, 1], [2, 2])})
    same = rerun.copy()
    changed = rerun.copy()
    changed.loc[0, "green_firm_share"] = 0.99

    def read_csv(name):
        return {"match_tbl": same, "stale_tbl": changed}.get(name)

    rows = checks.check_stale_files({"match_tbl": rerun, "stale_tbl": rerun}, read_csv)
    assert _status(rows, "stale_files.match_tbl") == "PASS"
    assert _status(rows, "stale_files.stale_tbl") == "WARN"
    assert _status(rows, "stale_files.summary") == "WARN"


def test_population_anchors_with_fixture_values(monkeypatch):
    monkeypatch.setattr(config, "POP_TOTAL", 3)
    monkeypatch.setattr(config, "GREEN_TOTAL", 2)
    monkeypatch.setattr(config, "OTHER_TOTAL", 1)
    monkeypatch.setattr(config, "FINANCED_TOTAL", 2)
    monkeypatch.setattr(config, "INVESTED_TOTAL", 1)
    monkeypatch.setattr(config, "GRANT_AND_VC_TOTAL", 0)
    firm = pd.DataFrame({
        "company_id": ["A", "B", "C"], "green": [1, 1, 0],
        "financed": [1, 1, 0], "n_investors_lifetime": [1, 0, 0],
        "any_grant": [0, 0, 0], "any_vc": [1, 0, 0],
    })
    rows = checks.check_population(firm)
    assert _status(rows, "population.firm_rows") == "PASS"
    assert _status(rows, "population.green") == "PASS"
    assert _status(rows, "population.financed") == "PASS"
    assert _status(rows, "population.invested") == "PASS"


def test_write_roundtrip(tmp_path):
    recon = pd.DataFrame([
        {"check_id": "x", "category": "c", "description": "d", "expected": 1,
         "observed": 1, "status": "PASS", "detail": ""},
    ])
    result = Step8Result(reconciliation=recon,
                         summary={"PASS": 1, "WARN": 0, "FAIL": 0, "total": 1})
    out = write_outputs(result, tmp_path)
    assert (out / "step8_reconciliation.csv").exists()
    reread = pd.read_csv(out / "step8_reconciliation.csv")
    assert list(reread["status"]) == ["PASS"]
