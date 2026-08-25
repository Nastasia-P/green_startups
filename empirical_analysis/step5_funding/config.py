"""Configuration for Step 5 (funding).

Self-contained: input/output paths, the group labels, the cohort and stage orders,
the VC grouping, the censoring constants, and the acceptance anchors all live here.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root: step5_funding/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Firm table (Step 2 output, input here) --------------------------------
# Resolution order (first existing wins); --firm-table overrides all of these.
#   1. env var STEP5_FIRM_TABLE
#   2. the target machine's OneDrive company_analysis.parquet (Windows only)
#   3. <repo>/data/outputs/company_analysis.parquet
_FIRM_TABLE_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\company_analysis.parquet",
]
_FIRM_TABLE_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "outputs" / "company_analysis.parquet"),
]


def _resolve_firm_table() -> Path:
    env = os.environ.get("STEP5_FIRM_TABLE")
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

# --- Step 1 clean tables (for the deal-level cuts) -------------------------
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
#   1. env var STEP5_OUTPUT_DIR
#   2. the target machine's OneDrive chapter4_outputs folder (Windows only)
#   3. <repo>/data/outputs/chapter4
_OUTPUT_DIR_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\chapter4_outputs",
]


def _resolve_output_dir() -> Path:
    env = os.environ.get("STEP5_OUTPUT_DIR")
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
# Reporting order for stage_group (any stage not listed is appended, then Unmapped).
STAGE_GROUP_ORDER = [
    "Grant", "Accelerator/Incubator", "Angel/Seed", "Early-stage VC",
    "Later-stage VC", "Growth/PE", "Debt", "Crowdfunding", "Spin-out/Corporate",
    "Other", "Unmapped",
]

# --- Robustness R1 (green_signal_group values) -----------------------------
STAGE1_LABEL = "Stage 1"     # vertical-tagged green firms
STAGE23_LABEL = "Stage 2+3"  # text-signal green firms

# --- Financing groupings (copied from Step 2) ------------------------------
# stage_group values that count as "VC" for the first-VC and progression measures.
VC_STAGE_GROUPS = {"Angel/Seed", "Early-stage VC", "Later-stage VC"}

# Access flags reported in T4.9 (rule N8: accelerator is its own row).
ACCESS_FLAGS = [
    ("any_financing", "financed"),
    ("any_vc", "any_vc"),
    ("any_grant", "any_grant"),
    ("any_debt", "any_debt"),
    ("any_accelerator", "any_accelerator"),
    ("any_growth_pe", "any_growth_pe"),
    ("any_crowdfunding", "any_crowdfunding"),
]

# Firm-level amount fields reported by cohort in T4.10 (rules N1, N4).
AMOUNT_FIELDS = ["total_raised", "last_deal_size", "median_deal_size"]

# --- Censoring (rule R4 / N5) ----------------------------------------------
SNAPSHOT_YEAR = 2026
FOLLOWON_MIN_WINDOW_YEARS = 1          # a follow-on needs at least this much time
FINANCED_CURVE_HORIZONS = list(range(0, 11))   # F4.4 years since founding: 0..10

# --- Reporting -------------------------------------------------------------
LOW_N_FLAG = 30
P90 = 0.90

# --- Acceptance anchors ----------------------------------------------------
POP_TOTAL = 116_005
GREEN_TOTAL = 8_306
OTHER_TOTAL = POP_TOTAL - GREEN_TOTAL
FINANCED_TOTAL = 47_714

# --- Engineering -----------------------------------------------------------
VERBOSE = False
