"""Tests for Step 10 (expanded start-up-status population).

A small synthetic source exercises the pipeline: the age filter, the Step 10
Universe rule (excluding Other Private Companies), baseline membership and the
exclusion decomposition, hybrid green labels, and the read-only guarantee on the
baseline population file.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pandas as pd
import pytest

from empirical_analysis.step10_expanded_status import config
from empirical_analysis.step10_expanded_status.build import (
    apply_age_filter,
    apply_step10_universe,
    build_exclusion,
    run_diagnostic,
    write_outputs,
)

TOKENS = {"solar"}
PHRASES = {"carbon capture"}


def _source_rows() -> list[dict]:
    base = dict(HQCountry="France", Keywords="", Description="", Verticals="")
    return [
        # B1: baseline, green via CleanTech vertical.
        {**base, "CompanyID": "B1", "CompanyName": "B1", "YearFounded": "2020",
         "OwnershipStatus": "Privately Held (no backing)", "BusinessStatus": "",
         "Universe": "Venture Capital", "Verticals": "CleanTech"},
        # B2: baseline, not green.
        {**base, "CompanyID": "B2", "CompanyName": "B2", "YearFounded": "2021",
         "OwnershipStatus": "Privately Held (backing)", "BusinessStatus": "Generating Revenue",
         "Universe": "Pre-venture", "Keywords": "software", "Description": "b2b saas"},
        # O1: outside via fails_alive; green via token "solar".
        {**base, "CompanyID": "O1", "CompanyName": "O1", "YearFounded": "2019",
         "OwnershipStatus": "Privately Held (no backing)", "BusinessStatus": "Out of Business",
         "Universe": "Venture Capital", "Keywords": "solar,energy"},
        # O2: outside via fails_ownership (Acquired/Merged); not green.
        {**base, "CompanyID": "O2", "CompanyName": "O2", "YearFounded": "2018",
         "OwnershipStatus": "Acquired/Merged", "BusinessStatus": "Generating Revenue",
         "Universe": "Venture Capital", "Keywords": "logistics"},
        # O3: outside via Universe M&A only (still private + operating).
        {**base, "CompanyID": "O3", "CompanyName": "O3", "YearFounded": "2022",
         "OwnershipStatus": "Privately Held (no backing)", "BusinessStatus": "",
         "Universe": "M&A, Venture Capital", "Description": "circular logistics platform"},
        # O4: outside via Publicly Held + Publicly Listed.
        {**base, "CompanyID": "O4", "CompanyName": "O4", "YearFounded": "2017",
         "OwnershipStatus": "Publicly Held", "BusinessStatus": "",
         "Universe": "Publicly Listed"},
        # O5: outside via multiple (acquired + bankruptcy + M&A universe).
        {**base, "CompanyID": "O5", "CompanyName": "O5", "YearFounded": "2016",
         "OwnershipStatus": "Acquired/Merged", "BusinessStatus": "Bankruptcy: Liquidation",
         "Universe": "M&A"},
        # X1: too old -> dropped by the age filter.
        {**base, "CompanyID": "X1", "CompanyName": "X1", "YearFounded": "2000",
         "OwnershipStatus": "Privately Held (no backing)", "BusinessStatus": "",
         "Universe": "Venture Capital"},
        # X2: Other Private Companies -> excluded from the expanded population.
        {**base, "CompanyID": "X2", "CompanyName": "X2", "YearFounded": "2020",
         "OwnershipStatus": "Privately Held (no backing)", "BusinessStatus": "",
         "Universe": "Other Private Companies"},
    ]


def _baseline() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"company_id": "B1", "green": 1, "green_stage": "vertical"},
            {"company_id": "B2", "green": 0, "green_stage": "none"},
        ]
    ).astype({"company_id": "string"})


def _write_inputs(tmp: Path) -> dict[str, Path]:
    source = tmp / "Company_Europe.csv"
    pd.DataFrame(_source_rows())[config.SOURCE_USECOLS].to_csv(source, index=False)

    population = tmp / "population_key.parquet"
    _baseline().to_parquet(population, engine="pyarrow", index=False)

    standalone = tmp / "strong_terms_active.csv"
    with standalone.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["token"])
        for t in sorted(TOKENS):
            w.writerow([t])

    phrases = tmp / "strong_term_phrases.csv"
    with phrases.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["phrase"])
        for p in PHRASES:
            w.writerow([p])

    return {"source": source, "population": population, "standalone": standalone, "phrases": phrases}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_age_filter_drops_old_and_invalid():
    df = pd.DataFrame(
        [
            {"YearFounded": "2020"}, {"YearFounded": "2000"}, {"YearFounded": ""},
        ]
    )
    young = apply_age_filter(df)
    assert len(young) == 1
    assert int(young["age_years"].iloc[0]) == config.CURRENT_YEAR - 2020


def test_universe_rule_excludes_other_private_companies():
    young = pd.DataFrame(
        {"Universe": ["Venture Capital", "M&A, Venture Capital", "Other Private Companies",
                      "Other Private Companies, Venture Capital", ""]}
    )
    kept = apply_step10_universe(young)
    assert list(kept["Universe"]) == ["Venture Capital", "M&A, Venture Capital"]


@pytest.fixture()
def result(tmp_path):
    paths = _write_inputs(tmp_path)
    return run_diagnostic(
        paths["source"], paths["population"], paths["standalone"], paths["phrases"], tmp_path / "out"
    )


def test_population_counts(result):
    df = result.expanded
    assert len(result.young) == 8          # all except X1 (too old)
    assert len(df) == 7                    # minus X2 (Other Private Companies)
    assert int(df["in_baseline_2026"].sum()) == 2
    assert int(df["outside_baseline_2026"].sum()) == 5
    assert "X2" not in set(df["company_id"])


def test_no_other_private_companies_and_membership_matches_filters(result):
    recon = result.audit.set_index("key")["observed"]
    assert int(recon["other_private_companies_in_expanded"]) == 0
    assert int(recon["membership_matches_filters"]) == 0
    assert int(recon["duplicate_company_ids"]) == 0
    assert int(recon["all_baseline_ids_present"]) == 2


def test_hybrid_green_reconciles_baseline(result):
    df = result.expanded.set_index("company_id")
    # Baseline green reconciles to canonical (B1 green, B2 other).
    assert int((result.expanded[result.expanded["in_baseline_2026"]]["green"] == 1).sum()) == 1
    # Outside firm O1 is green via the applied token "solar".
    assert df.loc["O1", "green"] == 1
    assert df.loc["O1", "green_stage"] == "token"


def test_exclusion_groups(result):
    df = result.expanded.set_index("company_id")
    assert df.loc["O1", "baseline_exclusion_group"] == "out_of_business_or_bankrupt"
    assert df.loc["O2", "baseline_exclusion_group"] == "acquired_or_merged"
    assert df.loc["O3", "baseline_exclusion_group"] == "universe_exit_marker_only"
    assert df.loc["O4", "baseline_exclusion_group"] == "public_or_exited"
    assert df.loc["O5", "baseline_exclusion_group"] == "multiple_exit_statuses"


def test_exclusion_table_green_vs_other(result):
    exc = build_exclusion(result.expanded).set_index("criterion")
    # Outside failure decomposition: fails_alive = O1,O5; fails_ownership = O2,O4,O5; fails_universe = O3,O4,O5.
    assert int(exc.loc["fails_alive", "all_outside_n"]) == 2
    assert int(exc.loc["fails_ownership", "all_outside_n"]) == 3
    assert int(exc.loc["fails_universe", "all_outside_n"]) == 3
    # Only O1 is green among the outside firms.
    assert int(exc.loc["out_of_business_or_bankrupt", "green_n"]) == 1


def test_read_only_and_outputs(tmp_path):
    paths = _write_inputs(tmp_path)
    out_dir = tmp_path / "out"
    before = _sha256(paths["population"])
    res = run_diagnostic(
        paths["source"], paths["population"], paths["standalone"], paths["phrases"], out_dir
    )
    write_outputs(res, out_dir)
    after = _sha256(paths["population"])
    assert before == after  # baseline population file is byte-identical

    for name in (
        config.POPULATION_TABLE, config.FLOW_TABLE, config.OUTCOMES_TABLE,
        config.EXCLUSION_TABLE, config.COHORT_TABLE, config.UNIVERSE_DIAG_TABLE,
        config.AUDIT_TABLE, config.REPORT_FILE,
    ):
        assert (out_dir / name).exists()
    reloaded = pd.read_parquet(out_dir / config.POPULATION_TABLE)
    assert len(reloaded) == 7
