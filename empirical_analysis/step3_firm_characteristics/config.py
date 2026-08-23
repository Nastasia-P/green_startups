"""Configuration for Step 3 (firm characteristics).

Self-contained: input/output paths, the group labels, cohort and employee-band
orders, and the reporting constants all live here.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root: step3_firm_characteristics/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Firm table (Step 2 output, input here) --------------------------------
# Resolution order (first existing wins); --firm-table overrides all of these.
#   1. env var STEP3_FIRM_TABLE
#   2. the target machine's OneDrive company_analysis.parquet (Windows only)
#   3. <repo>/data/outputs/company_analysis.parquet
_FIRM_TABLE_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\company_analysis.parquet",
]
_FIRM_TABLE_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "outputs" / "company_analysis.parquet"),
]


def _resolve_firm_table() -> Path:
    env = os.environ.get("STEP3_FIRM_TABLE")
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

# --- Step 1 clean tables (for the relational cuts) -------------------------
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

# --- Output directory ------------------------------------------------------
# Resolution order (first usable wins); --output-dir overrides all.
#   1. env var STEP3_OUTPUT_DIR
#   2. the target machine's OneDrive chapter4_outputs folder (Windows only)
#   3. <repo>/data/outputs/chapter4
_OUTPUT_DIR_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\chapter4_outputs",
]


def _resolve_output_dir() -> Path:
    env = os.environ.get("STEP3_OUTPUT_DIR")
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

# --- Group labels (rule N10) ----------------------------------------------
GREEN_LABEL = "Green start-ups"
OTHER_LABEL = "Other European start-ups"

# --- Orders ----------------------------------------------------------------
COHORT_ORDER = ["2016-2018", "2019-2021", "2022-2024", "2025-2026"]
EMPLOYEE_BAND_ORDER = ["1-10", "11-50", "51-200", "200+"]

# --- Reporting constants ---------------------------------------------------
TOP_N_SECTORS = 5
# Show a mean alongside the median for age only (rule N6: medians primary).
SHOW_MEAN_FOR_AGE = True

# --- Acceptance anchors ----------------------------------------------------
POP_TOTAL = 116_005
GREEN_TOTAL = 8_306
OTHER_TOTAL = POP_TOTAL - GREEN_TOTAL
# Overall green benchmark for F4.1 (green / population).
GREEN_BENCHMARK = round(GREEN_TOTAL / POP_TOTAL, 4)

# --- Engineering -----------------------------------------------------------
VERBOSE = False
