"""Configuration for Step 7 (geography x finance).

Self-contained: input/output paths, the group labels, the stage order, the (removed)
country floor, the low-n threshold, and the acceptance anchors all live here.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root: step7_geo_finance/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Firm table (Step 2 output, input here) --------------------------------
# Resolution order (first existing wins); --firm-table overrides all of these.
#   1. env var STEP7_FIRM_TABLE
#   2. the target machine's OneDrive company_analysis.parquet (Windows only)
#   3. <repo>/data/outputs/company_analysis.parquet
_FIRM_TABLE_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\company_analysis.parquet",
]
_FIRM_TABLE_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "outputs" / "company_analysis.parquet"),
]


def _resolve_firm_table() -> Path:
    env = os.environ.get("STEP7_FIRM_TABLE")
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

# --- Step 1 clean tables (deals + investor relations) ----------------------
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
_OUTPUT_DIR_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\chapter4_outputs",
]


def _resolve_output_dir() -> Path:
    env = os.environ.get("STEP7_OUTPUT_DIR")
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

# --- Country floor (dropped per user) --------------------------------------
# No floor: every country with at least one start-up gets a row; thin green cells
# carry low_n_flag. Kept as an explicit "include all" knob (raise to re-gate). The
# former decision-D4 gate is retained only as an informational sensitivity count.
MIN_COUNTRY_N = 1
MIN_COUNTRY_N_SENSITIVITY = 500
LOW_N_FLAG = 30

# --- Stage order (shared with Steps 5/6) -----------------------------------
STAGE_GROUP_ORDER = [
    "Grant", "Accelerator/Incubator", "Angel/Seed", "Early-stage VC",
    "Later-stage VC", "Growth/PE", "Debt", "Crowdfunding", "Spin-out/Corporate",
    "Other", "Unmapped",
]

# --- Fields ----------------------------------------------------------------
HQ_COUNTRY_FIELD = "hq_country"
TOTAL_RAISED_FIELD = "total_raised"
DEAL_SIZE_FIELD = "deal_size"

# --- Acceptance anchors ----------------------------------------------------
POP_TOTAL = 116_005
GREEN_TOTAL = 8_306
OTHER_TOTAL = POP_TOTAL - GREEN_TOTAL
INVESTED_TOTAL = 50_815

# --- Engineering -----------------------------------------------------------
VERBOSE = False
