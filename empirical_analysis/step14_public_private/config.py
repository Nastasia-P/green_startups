"""Configuration for Step 14 (public/private investor participation).

Self-contained: input/output paths, the group labels, the **explicit investor
classification** (public / private / exclude, covering every observed
`investor_type_grp`), the control specifications (columns (1)-(5), the fifth a
deal-count sensitivity), the estimator settings (OLS/LPM + HC1 robust SE), the
significance-star rule, the decimal-precision policy and the output filenames.

Every analysis here runs on the Step 5b common-horizon dataset
(`first5_analysis.parquet`, the 31,257 firms founded 2016-2020) and the Step 1
investor tables, restricted to each firm's first-five-year window.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo root: step14_public_private/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Firm panel (Step 5b canonical five-year dataset) ----------------------
_FIRM_PANEL_ANY = REPO_ROOT / "data" / "outputs" / "chapter4" / "first5_analysis.parquet"


def _resolve_firm_panel() -> Path:
    env = os.environ.get("STEP14_FIRM_PANEL") or os.environ.get("STEP5B_FIRM_PANEL")
    if env and Path(env).exists():
        return Path(env)
    return _FIRM_PANEL_ANY


FIRM_PANEL: Path = _resolve_firm_panel()

# --- Firm table (Step 2 output) -- needed for prepare_window() -------------
_FIRM_TABLE_ANY = REPO_ROOT / "data" / "outputs" / "company_analysis.parquet"


def _resolve_firm_table() -> Path:
    env = os.environ.get("STEP14_FIRM_TABLE") or os.environ.get("STEP5_FIRM_TABLE")
    if env and Path(env).exists():
        return Path(env)
    return _FIRM_TABLE_ANY


FIRM_TABLE: Path = _resolve_firm_table()

# --- Step 1 clean tables (deals + investor relations) ----------------------
_CLEAN_DIR_ANY = REPO_ROOT / "data" / "outputs" / "clean_tables"


def _resolve_clean_dir() -> Path:
    env = os.environ.get("STEP2_CLEAN_DIR")
    if env and Path(env).exists():
        return Path(env)
    return _CLEAN_DIR_ANY


CLEAN_DIR: Path = _resolve_clean_dir()

# --- Output directory ------------------------------------------------------
_OUTPUT_DIR_ANY = REPO_ROOT / "data" / "outputs" / "chapter4"


def _resolve_output_dir() -> Path:
    env = os.environ.get("STEP14_OUTPUT_DIR") or os.environ.get("STEP5_OUTPUT_DIR")
    if env and (Path(env).exists() or Path(env).parent.exists()):
        return Path(env)
    return _OUTPUT_DIR_ANY


OUTPUT_DIR: Path = _resolve_output_dir()

# --- Group labels (rule N10) ----------------------------------------------
GREEN_LABEL = "Green start-ups"
OTHER_LABEL = "Other European start-ups"
GREEN_COL = "green"

# ==========================================================================
# EXPLICIT INVESTOR CLASSIFICATION (supervisor: "define exactly which
# categories count as public and private"). This is the single source of
# truth -- it is NOT decided silently anywhere in the code. Every observed
# investor_type_grp must appear here; an acceptance check enforces 100%
# coverage and `investor_type_mapping.csv` reproduces this table with counts.
# ==========================================================================
PUBLIC_LABEL = "public"
PRIVATE_LABEL = "private"
EXCLUDE_LABEL = "exclude"

ANALYTICAL_GROUP: dict[str, str] = {
    # public = government / state-backed capital
    "Public/Government": PUBLIC_LABEL,
    # private = market / commercial capital
    "Independent VC": PRIVATE_LABEL,
    "Corporate": PRIVATE_LABEL,
    "Angel": PRIVATE_LABEL,
    "PE/Growth": PRIVATE_LABEL,
    "Family Office": PRIVATE_LABEL,
    # exclude / unclassified = not a clean public-vs-private equity signal
    "Impact Investing": EXCLUDE_LABEL,
    "Accelerator/Incubator": EXCLUDE_LABEL,
    "Lender/Debt": EXCLUDE_LABEL,
    "Other/Unclassified": EXCLUDE_LABEL,
}

# --- Financing groupings (grant -> VC sequencing on the window) ------------
VC_STAGE_GROUPS = {"Angel/Seed", "Early-stage VC", "Later-stage VC"}
GRANT_STAGE_GROUP = "Grant"

# --- Controls: the sequential specifications (columns (1)-(5)) -------------
# (1)-(4) are the main specs (identical progression to step13); (5) adds the
# deal-count sensitivity control and is explicitly NOT the baseline.
SPECS = [
    ("spec1", []),
    ("spec2", ["cohort"]),
    ("spec3", ["cohort", "country"]),
    ("spec4", ["cohort", "country", "industry"]),
    ("spec5", ["cohort", "country", "industry", "dealcount"]),
]
SPEC_COLUMN_LABEL = {
    "spec1": "(1)", "spec2": "(2)", "spec3": "(3)", "spec4": "(4)", "spec5": "(5)",
}
DEALCOUNT_LABEL = "+ deal count"

# Control-block -> firm-panel column.
COHORT_COL = "cohort"
COUNTRY_COL = "hq_country"
INDUSTRY_COL_GROUP = "primary_industry_group"
INDUSTRY_COL_CODE = "primary_industry_code"
INDUSTRY_COL = INDUSTRY_COL_GROUP
DEALCOUNT_COL = "n_deals_5yr"          # transformed to log(1 + n_deals_5yr)
DEALCOUNT_DESIGN_COL = "log1p_n_deals_5yr"

MIN_FE_LEVEL_N = 50
OTHER_LEVEL = "Other"

# --- Estimator -------------------------------------------------------------
COV_TYPE = "HC1"
CI_LEVEL = 0.95
ESTIMATOR = "OLS/LPM"

# --- Significance stars (generated from stored p-values, never hard-coded) -
STAR_RULE: dict[float, str] = {0.01: "***", 0.05: "**", 0.10: "*"}

# --- Decimal precision (single tunable source of truth) --------------------
DECIMALS = 4       # coef, std_error, ci_low, ci_high, r_squared, p_value, shares
DECIMALS_PP = 2    # coef_pp, se_pp, pp_difference (percentage-point columns)

# --- Output filenames (distinct; never collide with Steps 5/5b/6/13) -------
OUT_MAPPING = "investor_type_mapping"
OUT_AMOUNT_AUDIT = "investor_amount_audit"
OUT_FIRM_PANEL = "pubpriv_analysis_5yr"
OUT_PARTICIPATION = "T14_pubpriv_participation"
OUT_REGRESSION = "T14_pubpriv_regression"
OUT_GRANT_VC = "T14_grant_vc_sequencing_5yr"
OUT_SEQUENCING = "T14_pubpriv_sequencing_5yr"
OUT_ORDERING_REG = "T14_pubpriv_ordering_regression"
OUT_CAPITAL_COMPOSITION = "T14_deal_size_by_investor_composition_5yr"
SAMPLE_AUDIT = "step14_sample_audit"
CAPTIONS_FILE = "captions_step14"

# Column order for both regression tables (machine-readable; no LaTeX).
RESULT_COLUMNS = [
    "outcome", "family", "spec", "column", "controls", "sample", "estimator",
    "coef", "std_error", "p_value", "p_value_display", "stars",
    "ci_low", "ci_high", "coef_pp", "se_pp",
    "n", "r_squared",
    "cohort_controls", "country_fe", "industry_fe", "deal_count_control",
    "n_fe_country", "n_fe_industry", "cov_type",
]

# Output names this module is allowed to write (acceptance check).
STEP14_OUTPUT_NAMES = {
    OUT_MAPPING, OUT_AMOUNT_AUDIT, OUT_FIRM_PANEL, OUT_PARTICIPATION,
    OUT_REGRESSION, OUT_GRANT_VC, OUT_SEQUENCING, OUT_ORDERING_REG,
    OUT_CAPITAL_COMPOSITION, SAMPLE_AUDIT, CAPTIONS_FILE,
}

# --- Reporting -------------------------------------------------------------
LOW_N_FLAG = 30

# --- Engineering -----------------------------------------------------------
VERBOSE = False
