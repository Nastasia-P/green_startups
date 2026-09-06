"""Configuration for Step 13 (exploratory regression analysis).

Self-contained: input/output paths, the outcome lists per model family, the
control specifications (M0-M3), the fixed-effect bucketing threshold, the
estimator settings (OLS + HC1 robust SE, 95% CI) and the output filenames all
live here.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo root: step13_regression/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Firm table (Step 2 output) --------------------------------------------
_FIRM_TABLE_ANY = REPO_ROOT / "data" / "outputs" / "company_analysis.parquet"


def _resolve_firm_table() -> Path:
    env = os.environ.get("STEP13_FIRM_TABLE") or os.environ.get("STEP5_FIRM_TABLE")
    if env and Path(env).exists():
        return Path(env)
    return _FIRM_TABLE_ANY


FIRM_TABLE: Path = _resolve_firm_table()

# --- Step 1 clean tables (for the family-3 fixed-horizon capital) ----------
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
    env = os.environ.get("STEP13_OUTPUT_DIR") or os.environ.get("STEP5_OUTPUT_DIR")
    if env and (Path(env).exists() or Path(env).parent.exists()):
        return Path(env)
    return _OUTPUT_DIR_ANY


OUTPUT_DIR: Path = _resolve_output_dir()

# --- Group labels (rule N10) ----------------------------------------------
GREEN_LABEL = "Green start-ups"
OTHER_LABEL = "Other European start-ups"
GREEN_COL = "green"

# --- Outcomes per model family ---------------------------------------------
# Family 1: binary access outcomes -> linear probability model (OLS).
# (label -> firm-table column; any_financing is the `financed` column, matching
#  step5_funding.config.ACCESS_FLAGS.)
ACCESS_OUTCOMES = [
    ("any_financing", "financed"),
    ("any_vc", "any_vc"),
    ("any_grant", "any_grant"),
    ("any_accelerator", "any_accelerator"),
]

# Family 2: continuous financing-timing outcomes (years).
TIMING_OUTCOMES = [
    ("first_funding_lag", "first_funding_lag"),
    ("first_vc_lag", "first_vc_lag"),
]

# Family 3: log(1 + disclosed capital) raised in the first five post-founding
# years (built from step5b_fixed_horizon; observed amounts only).
CAPITAL_OUTCOME_LABEL = "log1p_first5_disclosed_capital"

# --- Controls: the sequential specifications (M0 -> M3) --------------------
# Each model lists the control blocks added on top of `green`.
MODEL_SPECS = [
    ("M0", []),                                   # green only
    ("M1", ["cohort"]),                           # + founding cohort
    ("M2", ["cohort", "country"]),                # + country FE
    ("M3", ["cohort", "country", "industry"]),    # + primary industry FE
]

# Control-block -> firm-table column.
COHORT_COL = "cohort"
COUNTRY_COL = "hq_country"
# Industry: ONE stable firm-level tag (never the multi-valued industry join).
INDUSTRY_COL_GROUP = "primary_industry_group"
INDUSTRY_COL_CODE = "primary_industry_code"
INDUSTRY_COL = INDUSTRY_COL_GROUP  # overridable at runtime via run.py --industry

COHORT_ORDER = ["2016-2018", "2019-2021", "2022-2024", "2025-2026"]

# Fixed-effect levels with fewer than this many firms are folded into "Other"
# so the design matrix stays full-rank and free of singleton dummies.
MIN_FE_LEVEL_N = 50
OTHER_LEVEL = "Other"

# --- Estimator -------------------------------------------------------------
COV_TYPE = "HC1"          # heteroskedasticity-robust SE (LPM is heteroskedastic)
CI_LEVEL = 0.95
ESTIMATOR = "OLS/LPM"

# --- Output filenames (distinct; never collide with Steps 5/6/step5b) ------
OUT_ACCESS = "T_regression_financing_access"
OUT_TIMING = "T_regression_timing"
OUT_CAPITAL = "T_regression_first5_capital"
SAMPLE_AUDIT = "step13_regression_sample_audit"
CAPTIONS_FILE = "captions_step13"

# Column order for every regression table.
RESULT_COLUMNS = [
    "outcome", "family", "model", "sample", "estimator",
    "green_coef", "green_se", "green_pvalue", "green_ci_low", "green_ci_high",
    "n", "r_squared", "controls", "n_fe_country", "n_fe_industry", "cov_type",
]

# Output names this module is allowed to write (acceptance C5). Any collision
# with an existing Step 5/6/step5b name would be a bug.
STEP13_OUTPUT_NAMES = {
    OUT_ACCESS, OUT_TIMING, OUT_CAPITAL, SAMPLE_AUDIT, CAPTIONS_FILE,
}

# --- Acceptance anchors ----------------------------------------------------
POP_TOTAL = 116_005

# --- Engineering -----------------------------------------------------------
VERBOSE = False
