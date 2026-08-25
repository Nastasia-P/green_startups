"""Configuration for Step 6 (investors and grants).

Self-contained: input/output paths, the group labels, the investor-type order, the
VC / grant stage definitions, the INVESTED threshold, and the acceptance anchors all
live here.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root: step6_investors/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Firm table (Step 2 output, input here) --------------------------------
# Resolution order (first existing wins); --firm-table overrides all of these.
#   1. env var STEP6_FIRM_TABLE
#   2. the target machine's OneDrive company_analysis.parquet (Windows only)
#   3. <repo>/data/outputs/company_analysis.parquet
_FIRM_TABLE_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\company_analysis.parquet",
]
_FIRM_TABLE_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "outputs" / "company_analysis.parquet"),
]


def _resolve_firm_table() -> Path:
    env = os.environ.get("STEP6_FIRM_TABLE")
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
# Resolution order (first usable wins); --output-dir overrides all.
#   1. env var STEP6_OUTPUT_DIR
#   2. the target machine's OneDrive chapter4_outputs folder (Windows only)
#   3. <repo>/data/outputs/chapter4
_OUTPUT_DIR_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\chapter4_outputs",
]


def _resolve_output_dir() -> Path:
    env = os.environ.get("STEP6_OUTPUT_DIR")
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

# --- Robustness R1 (green_signal_group values) -----------------------------
STAGE1_LABEL = "Stage 1"     # vertical-tagged green firms
STAGE23_LABEL = "Stage 2+3"  # text-signal green firms

# --- INVESTED subsample ----------------------------------------------------
# Firms with at least one recorded investor; the master population for Step 6.
INVESTED_MIN = 1  # n_investors_lifetime >= INVESTED_MIN

# --- Investor type reporting order -----------------------------------------
# Any investor_type_grp not listed is appended after these, then Other/Unclassified
# is forced last.
INVESTOR_TYPE_ORDER = [
    "Independent VC",
    "Public/Government",
    "Corporate",
    "PE/Growth",
    "Accelerator/Incubator",
    "Angel",
    "Lender/Debt",
    "Family Office",
    "Impact Investing",
    "Other/Unclassified",
]
UNCLASSIFIED_LABEL = "Other/Unclassified"

# --- Company-level flags reported in T4.19 (rule N8) -----------------------
INVESTOR_FLAGS = [
    "any_public_investor",
    "any_corporate_investor",
    "any_ivc_investor",
    "any_accelerator_investor",
    "any_lender_investor",
]
N_INVESTORS_FIELD = "n_investors_lifetime"

# --- Public/private (T4.21) ------------------------------------------------
PUBLIC_PRIVATE_LIFETIME = "public_private_lifetime"
PUBLIC_PRIVATE_SAME_DEAL = "public_private_same_deal"

# --- Financing groupings (for grant -> VC sequencing, T4.22) ---------------
# stage_group values that count as "VC" for the first-VC measure. Matches Step 5
# and the Step 2 `any_vc` flag (accelerator and growth/PE are their own categories,
# rule N8), so the grant-and-VC population reconciles with `any_grant & any_vc`.
VC_STAGE_GROUPS = {"Angel/Seed", "Early-stage VC", "Later-stage VC"}
GRANT_STAGE_GROUP = "Grant"

# --- Syndication (T4.25) ---------------------------------------------------
MULTI_INVESTOR_MIN = 2  # a round is "multi-investor" if n_investors >= this
# Reporting order for stage_group (any stage not listed is appended).
STAGE_GROUP_ORDER = [
    "Grant", "Accelerator/Incubator", "Angel/Seed", "Early-stage VC",
    "Later-stage VC", "Growth/PE", "Debt", "Crowdfunding", "Spin-out/Corporate",
    "Other", "Unmapped",
]

# --- Reporting -------------------------------------------------------------
LOW_N_FLAG = 30
UNCLASSIFIED_WARN_SHARE = 0.10

# --- Acceptance anchors ----------------------------------------------------
POP_TOTAL = 116_005
GREEN_TOTAL = 8_306
OTHER_TOTAL = POP_TOTAL - GREEN_TOTAL
INVESTED_TOTAL = 50_815
GRANT_AND_VC_TOTAL = 3_960

# --- Engineering -----------------------------------------------------------
VERBOSE = False
