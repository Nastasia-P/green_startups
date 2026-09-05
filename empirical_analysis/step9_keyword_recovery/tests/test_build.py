"""Tests for Step 9 (keyword-recovery robustness diagnostic).

A small synthetic population exercises the diagnostics: text-only matching must be
independent of the vertical stage, the recovery invariants must hold, the vertical
cohorts must sum to the Stage-1 total, and running the module must never touch the
baseline population file (read-only guarantee).
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pandas as pd
import pytest

from empirical_analysis.step9_keyword_recovery import config
from empirical_analysis.step9_keyword_recovery.build import (
    build_by_vertical,
    build_stage1_headline,
    build_trie,
    compute_diagnostics,
    load_strong_phrases,
    load_strong_tokens,
    run_diagnostic,
    write_outputs,
)

TOKENS = frozenset({"solar"})
PHRASES = {"carbon capture": "carbon capture"}


def _baseline() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # A: Stage-1 CleanTech, recovered via standalone token "solar".
            {"company_id": "A", "green": 1, "green_stage": "vertical", "green_signal_group": "Stage 1"},
            # B: Stage-1 Climate Tech, recovered via phrase "carbon capture".
            {"company_id": "B", "green": 1, "green_stage": "vertical", "green_signal_group": "Stage 1"},
            # C: Stage-1 both verticals, NO recovering text.
            {"company_id": "C", "green": 1, "green_stage": "vertical", "green_signal_group": "Stage 1"},
            # D: token-stage green (not Stage 1) but text matches.
            {"company_id": "D", "green": 1, "green_stage": "token", "green_signal_group": "Stage 2+3"},
            # E: non-green, no text.
            {"company_id": "E", "green": 0, "green_stage": "none", "green_signal_group": "none"},
        ]
    ).astype({"company_id": "string"})


def _text() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"company_id": "A", "Keywords": "solar,energy", "Description": "we build solar power", "Verticals": "CleanTech"},
            {"company_id": "B", "Keywords": "", "Description": "carbon capture technology", "Verticals": "Climate Tech"},
            {"company_id": "C", "Keywords": "logistics", "Description": "delivery routing", "Verticals": "CleanTech,Climate Tech"},
            {"company_id": "D", "Keywords": "solar", "Description": "", "Verticals": ""},
            {"company_id": "E", "Keywords": "", "Description": "", "Verticals": ""},
        ]
    ).astype({"company_id": "string"})


@pytest.fixture()
def firm_level() -> pd.DataFrame:
    trie = build_trie({p: p for p in PHRASES})
    return compute_diagnostics(_baseline(), _text(), TOKENS, trie)


def test_text_match_is_independent_of_vertical(firm_level):
    fl = firm_level.set_index("company_id")
    # D is not Stage 1 but its text still matches the standalone token.
    assert not bool(fl.loc["D", "is_stage1"])
    assert bool(fl.loc["D", "text_match_standalone"])
    # C is Stage 1 but has no recovering text.
    assert bool(fl.loc["C", "is_stage1"])
    assert not bool(fl.loc["C", "text_match_any"])


def test_text_match_any_invariant(firm_level):
    any_ = firm_level["text_match_any"]
    combined = firm_level["text_match_standalone"] | firm_level["text_match_mwe"]
    assert (any_ == combined).all()


def test_matched_terms_recorded(firm_level):
    fl = firm_level.set_index("company_id")
    assert fl.loc["A", "matched_standalone_terms"] == "solar"
    assert fl.loc["B", "matched_mwes"] == "carbon capture"


def test_vertical_cohorts(firm_level):
    fl = firm_level.set_index("company_id")
    assert fl.loc["A", "vertical_cohort"] == "cleantech_only"
    assert fl.loc["B", "vertical_cohort"] == "climate_only"
    assert fl.loc["C", "vertical_cohort"] == "both"
    assert fl.loc["D", "vertical_cohort"] == "NA"


def test_stage1_headline(firm_level):
    h = build_stage1_headline(firm_level).set_index("metric")["n"]
    assert h["stage1_n"] == 3            # A, B, C
    assert h["recovered_any"] == 2       # A (token), B (phrase); C not
    assert h["recovered_standalone"] == 1
    assert h["recovered_mwe"] == 1
    assert h["not_recovered"] == 1


def test_by_vertical_cohorts_sum_to_stage1(firm_level):
    bv = build_by_vertical(firm_level).set_index("cohort")["n_firms"]
    assert int(bv[["cleantech_only", "climate_only", "both"]].sum()) == int(bv["all_stage1"])
    assert int(bv["all_stage1"]) == 3


def test_recovered_any_ge_components(firm_level):
    h = build_stage1_headline(firm_level).set_index("metric")["n"]
    assert h["recovered_any"] >= max(h["recovered_standalone"], h["recovered_mwe"])


# --------------------------------------------------------------------------
# End-to-end with synthetic input files, including the read-only guarantee.
# --------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_inputs(tmp: Path) -> dict[str, Path]:
    pop = tmp / "population_key.parquet"
    _baseline().to_parquet(pop, engine="pyarrow", index=False)

    spine = tmp / "spine.csv"
    _text().rename(columns={"company_id": "CompanyID"}).to_csv(spine, index=False)

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

    return {"population": pop, "spine": spine, "standalone": standalone, "phrases": phrases}


def test_loaders_read_synthetic_files(tmp_path):
    paths = _write_inputs(tmp_path)
    assert load_strong_tokens(paths["standalone"]) == TOKENS
    assert set(load_strong_phrases(paths["phrases"])) == set(PHRASES)


def test_end_to_end_and_read_only(tmp_path):
    paths = _write_inputs(tmp_path)
    out_dir = tmp_path / "out"

    before = _sha256(paths["population"])
    result = run_diagnostic(
        paths["population"], paths["spine"], paths["standalone"], paths["phrases"], out_dir
    )
    write_outputs(result, out_dir)
    after = _sha256(paths["population"])

    # Read-only guarantee: the baseline population file is byte-identical.
    assert before == after

    # Every output exists and the firm-level table has one row per firm.
    assert (out_dir / config.FIRM_LEVEL_TABLE).exists()
    assert (out_dir / config.STAGE1_TABLE).exists()
    assert (out_dir / config.BY_VERTICAL_TABLE).exists()
    assert (out_dir / config.RECONCILIATION_TABLE).exists()
    assert (out_dir / config.REPORT_FILE).exists()
    reloaded = pd.read_parquet(out_dir / config.FIRM_LEVEL_TABLE)
    assert len(reloaded) == 5

    # Reconciliation records the read-only assertion and the guard.
    recon = result.reconciliation.set_index("key")["observed"]
    assert recon["labels_modified"] == "False"
    assert recon["guard_no_vertical_terms_in_vocab"] == "True"
