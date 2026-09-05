"""Configuration for Step 10 (expanded start-up-status population).

Self-contained: the raw source, the baseline labels, the vocabulary, the output
directory, the baseline filter sets (copied verbatim from
filter_startups_stages.py so Step 10 is self-documenting), the founding cohorts,
and the acceptance anchors all live here.

All inputs are overridable via CLI flags (highest priority) or env vars, falling
back to the repo defaults below.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root: step10_expanded_status/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Raw source population (read-only) -------------------------------------
# The full European PitchBook company export (6,453,656 rows) that
# filter_startups_stages.py filters down to the 116,005 baseline. Step 10 starts
# from here so it can reintroduce the exited / non-operating firms the baseline
# removes.
SOURCE: Path = Path(os.environ.get("KWR_STEP10_SOURCE") or (REPO_ROOT / "Company_Europe.csv"))

# Only the columns Step 10 needs are read from the 5.4 GB source.
SOURCE_USECOLS = [
    "CompanyID",
    "CompanyName",
    "YearFounded",
    "OwnershipStatus",
    "BusinessStatus",
    "Universe",
    "HQCountry",
    "Keywords",
    "Description",
    "Verticals",
]

# --- Baseline green labels (canonical, read-only) --------------------------
POPULATION_FILENAME = "population_key.parquet"
_CLEAN_DIR_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\clean_tables",
]
_CLEAN_DIR_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "outputs" / "clean_tables"),
    str(REPO_ROOT / "data" / "interim"),
]


def _resolve_clean_dir() -> Path:
    env = os.environ.get("KWR_CLEAN_DIR") or os.environ.get("STEP2_CLEAN_DIR")
    win = _CLEAN_DIR_CANDIDATES_WIN if os.name == "nt" else []
    for cand in ([env] if env else []) + win + _CLEAN_DIR_CANDIDATES_ANY:
        try:
            path = Path(cand)
            if path.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "outputs" / "clean_tables"


CLEAN_DIR: Path = _resolve_clean_dir()
POPULATION: Path = Path(os.environ.get("KWR_POPULATION") or (CLEAN_DIR / POPULATION_FILENAME))

# --- Vocabulary (current on-disk files; report actual counts) --------------
# Same files and rules as the live classifier and Step 9. On-disk: 68 tokens /
# 456 phrases; thesis quotes 64/458 (recorded in the audit).
STANDALONE: Path = Path(
    os.environ.get("KWR_STANDALONE") or (REPO_ROOT / "data" / "outputs" / "strong_terms_active.csv")
)
PHRASES: Path = Path(
    os.environ.get("KWR_PHRASES") or (REPO_ROOT / "data" / "outputs" / "strong_term_phrases.csv")
)
THESIS_STANDALONE = 64
THESIS_MWE = 458

# --- Output directory ------------------------------------------------------
OUT_DIR: Path = Path(os.environ.get("KWR_OUT_DIR") or (REPO_ROOT / "data" / "outputs" / "chapter4"))

POPULATION_TABLE = "step10_expanded_population.parquet"
FLOW_TABLE = "T_status_population_flow.csv"
OUTCOMES_TABLE = "T_status_outcomes_green_vs_other.csv"
EXCLUSION_TABLE = "T_status_exclusion_green_vs_other.csv"
COHORT_TABLE = "T_status_outcomes_by_cohort.csv"
UNIVERSE_DIAG_TABLE = "step10_universe_diagnostics.csv"
AUDIT_TABLE = "step10_audit.csv"
REPORT_FILE = "step10_expanded_status_report.txt"

# --- Age criterion (identical to the baseline) -----------------------------
CURRENT_YEAR = 2026
MAX_AGE = 10  # at most 10 years old; missing/invalid YearFounded is dropped

# --- Baseline filter sets (verbatim from filter_startups_stages.py) --------
# Ownership states retained by the BASELINE (Step 10 does NOT apply this).
BASELINE_OWNERSHIP = frozenset(
    {"Privately Held (no backing)", "Privately Held (backing)", "In IPO Registration"}
)
# Universe tokens the BASELINE allows (every token must be in this 4-set).
BASELINE_UNIVERSE = frozenset({"Pre-venture", "Venture Capital", "Private Equity", "Debt Financed"})
# Defunct/failed BusinessStatus values the BASELINE excludes (Step 10 keeps them).
DEAD_BUSINESS_STATUSES = frozenset(
    {"Out of Business", "Bankruptcy: Liquidation", "Bankruptcy: Admin/Reorg"}
)

# --- Step 10 Universe rule -------------------------------------------------
# Step 10 admits the 6 entrepreneurial/exit categories and excludes only
# "Other Private Companies". Every Universe token must be in this 6-set (in this
# data that is exactly equivalent to "does not contain Other Private Companies").
STEP10_UNIVERSE = frozenset(
    {"Pre-venture", "Venture Capital", "Private Equity", "Debt Financed", "M&A", "Publicly Listed"}
)
EXCLUDED_UNIVERSE = "Other Private Companies"

# OwnershipStatus values that indicate an exit/non-operation (not in the baseline
# allow-set); used to build the raw flags. Documented from the actual data.
OWNERSHIP_ACQUIRED_MERGED = frozenset({"Acquired/Merged", "Acquired/Merged (Operating Subsidiary)"})
OWNERSHIP_PUBLIC = "Publicly Held"
OWNERSHIP_OUT_OF_BUSINESS = "Out of Business"
BUSINESS_OUT_OF_BUSINESS = "Out of Business"
BUSINESS_BANKRUPTCY = frozenset({"Bankruptcy: Liquidation", "Bankruptcy: Admin/Reorg"})

# --- Founding cohorts (same edges as Step 2) -------------------------------
COHORT_BINS = [
    (2016, 2018, "2016-2018"),
    (2019, 2021, "2019-2021"),
    (2022, 2024, "2022-2024"),
    (2025, 2026, "2025-2026"),
]

# --- Acceptance anchors ----------------------------------------------------
RAW_ROWS = 6_453_656
AGE_FILTERED = 2_702_220
EXPANDED = 152_310
BASELINE = 116_005
GREEN_TOTAL = 8_306
OTHER_TOTAL = 107_699
OUTSIDE = 36_305
