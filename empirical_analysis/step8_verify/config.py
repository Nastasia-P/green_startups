"""Configuration for Step 8 (verification).

Self-contained: input/output paths, the acceptance anchors reused across the pipeline,
and the reconciliation tolerances all live here.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root: step8_verify/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Firm table (Step 2 output, input here) --------------------------------
_FIRM_TABLE_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\company_analysis.parquet",
]
_FIRM_TABLE_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "outputs" / "company_analysis.parquet"),
]


def _resolve_firm_table() -> Path:
    env = os.environ.get("STEP8_FIRM_TABLE")
    win = _FIRM_TABLE_CANDIDATES_WIN if os.name == "nt" else []
    for cand in ([env] if env else []) + win + _FIRM_TABLE_CANDIDATES_ANY:
        try:
            path = Path(cand)
            if path.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "outputs" / "company_analysis.parquet"


FIRM_TABLE: Path = _resolve_firm_table()

# --- Step 1 clean tables ---------------------------------------------------
_CLEAN_DIR_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\clean_tables",
]
_CLEAN_DIR_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "outputs" / "clean_tables"),
    str(REPO_ROOT / "data" / "interim"),
]


def _resolve_clean_dir() -> Path:
    env = os.environ.get("STEP2_CLEAN_DIR")
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

# --- Eurostat population (Step 4 T4.7 re-run input) ------------------------
_POPULATION_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "sources" / "eurostat_population.csv"),
]


def _resolve_population() -> Path:
    env = os.environ.get("STEP4_POPULATION")
    for cand in ([env] if env else []) + _POPULATION_CANDIDATES_ANY:
        try:
            path = Path(cand)
            if path.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "sources" / "eurostat_population.csv"


POPULATION_FILE: Path = _resolve_population()

# --- Output directory ------------------------------------------------------
_OUTPUT_DIR_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\chapter4_outputs",
]


def _resolve_output_dir() -> Path:
    env = os.environ.get("STEP8_OUTPUT_DIR")
    win = _OUTPUT_DIR_CANDIDATES_WIN if os.name == "nt" else []
    for cand in ([env] if env else []) + win:
        try:
            path = Path(cand)
            if path.exists() or path.parent.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "outputs" / "chapter4"


OUTPUT_DIR: Path = _resolve_output_dir()

# --- Acceptance anchors (shared with the earlier steps) --------------------
POP_TOTAL = 116_005
GREEN_TOTAL = 8_306
OTHER_TOTAL = POP_TOTAL - GREEN_TOTAL
GREEN_STAGES = (6_636, 834, 836)   # green_stage 1 / 2 / 3, summing to GREEN_TOTAL
FINANCED_TOTAL = 47_714
INVESTED_TOTAL = 50_815
GRANT_AND_VC_TOTAL = 3_960
DEALS_TOTAL = 116_505
LOW_N_FLAG = 30

# --- Fields ----------------------------------------------------------------
N_INVESTORS_FIELD = "n_investors_lifetime"
TOTAL_RAISED_FIELD = "total_raised"

# --- Tolerances ------------------------------------------------------------
SHARE_TOL = 1e-2   # shares rounded to 4dp over up to ~11 rows
REL_TOL = 1e-6     # value equality
STALE_TOL = 1e-6   # on-disk vs re-run numeric compare

# --- Engineering -----------------------------------------------------------
VERBOSE = False
