"""Configuration for Step 13 (common-horizon regression analysis).

Self-contained: input/output paths, the outcome lists per model family, the
control specifications (spec1-spec4), the fixed-effect bucketing threshold,
the estimator settings (OLS + HC1 robust SE, 95% CI), the significance-star
rule, the decimal-precision policy and the output filenames all live here.

Every primary regression in this module runs on the Step 5b common-horizon
dataset (`first5_analysis.parquet`): the 31,257 firms founded 2016-2020 whose
complete five-year window is observable. Access and capital use every
eligible firm (capital restricted further to those with a disclosed amount);
timing is supplementary and conditions on the event having occurred in-window.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo root: step13_regression/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Firm panel (Step 5b canonical five-year dataset) ----------------------
_FIRM_PANEL_ANY = REPO_ROOT / "data" / "outputs" / "chapter4" / "first5_analysis.parquet"


def _resolve_firm_panel() -> Path:
    env = os.environ.get("STEP13_FIRM_PANEL") or os.environ.get("STEP5B_FIRM_PANEL")
    if env and Path(env).exists():
        return Path(env)
    return _FIRM_PANEL_ANY


FIRM_PANEL: Path = _resolve_firm_panel()

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

# --- Outcomes per model family (all sourced from first5_analysis.parquet) --
# Family 1: binary access outcomes over every eligible firm -> LPM.
ACCESS_OUTCOMES = [
    ("any_financing", "any_financing_5yr"),
    ("any_vc", "any_vc_5yr"),
    ("any_grant", "any_grant_5yr"),
    ("any_accelerator", "any_accelerator_5yr"),
]

# Family 2 (supplementary): timing, conditional on the event occurring
# in-window (years from founding to the first in-window event).
TIMING_OUTCOMES = [
    ("first_financing_lag", "first_financing_lag_5yr"),
    ("first_vc_lag", "first_vc_lag_5yr"),
]

# Family 3: intensive-margin capital, over eligible firms with a disclosed
# in-window amount only (never zero-filled; see capital coverage diagnostic).
CAPITAL_SOURCE_COL = "disclosed_capital_5yr"
CAPITAL_HAS_COL = "has_disclosed_capital_5yr"
CAPITAL_OUTCOME_LABEL = "log1p_disclosed_capital_5yr"

# --- Controls: the sequential specifications (spec1 -> spec4) --------------
# Each spec lists the control blocks added on top of `green`. Internal names
# only -- every thesis-facing output uses the `column` label below, never
# these spec names.
SPECS = [
    ("spec1", []),                                   # green only
    ("spec2", ["cohort"]),                           # + founding cohort
    ("spec3", ["cohort", "country"]),                # + country FE
    ("spec4", ["cohort", "country", "industry"]),    # + primary industry FE
]
SPEC_COLUMN_LABEL = {"spec1": "(1)", "spec2": "(2)", "spec3": "(3)", "spec4": "(4)"}

# Control-block -> firm-panel column.
COHORT_COL = "cohort"
COUNTRY_COL = "hq_country"
INDUSTRY_COL_GROUP = "primary_industry_group"
INDUSTRY_COL_CODE = "primary_industry_code"
INDUSTRY_COL = INDUSTRY_COL_GROUP  # overridable at runtime via run.py --industry

COHORT_ORDER = ["2016-2018", "2019-2021"]

# Fixed-effect levels with fewer than this many firms are folded into "Other"
# so the design matrix stays full-rank and free of singleton dummies.
MIN_FE_LEVEL_N = 50
OTHER_LEVEL = "Other"

# --- Estimator -------------------------------------------------------------
COV_TYPE = "HC1"          # heteroskedasticity-robust SE (LPM is heteroskedastic)
CI_LEVEL = 0.95
ESTIMATOR = "OLS/LPM"

# --- Significance stars (generated from stored p-values, never hard-coded) -
# Checked from the smallest threshold up; the first match wins.
STAR_RULE: dict[float, str] = {0.01: "***", 0.05: "**", 0.10: "*"}

# --- Decimal precision (single tunable source of truth) --------------------
# Change these two constants to change every rounded number this module
# writes; nothing else hard-codes a decimal count.
DECIMALS = 4       # coef, std_error, ci_low, ci_high, r_squared, p_value
DECIMALS_PP = 2    # coef_pp, se_pp (percentage-point display columns)

# --- Output filenames (distinct; never collide with Steps 5/6/step5b) ------
OUT_ACCESS = "T_regression_access_5yr"
OUT_TIMING = "T_regression_timing_5yr"
OUT_CAPITAL = "T_regression_capital_5yr"
CAPITAL_COVERAGE = "capital_coverage_diagnostic"
SAMPLE_AUDIT = "step13_regression_sample_audit"
CAPTIONS_FILE = "captions_step13"

# Column order for every regression table (machine-readable; no formatted /
# LaTeX tables are produced -- these CSVs carry everything needed to typeset
# tables later: the column label, coefficient, SE, p-value, auto-generated
# stars, CI, pp-display columns and FE indicators).
RESULT_COLUMNS = [
    "outcome", "family", "spec", "column", "controls", "sample", "estimator",
    "coef", "std_error", "p_value", "p_value_display", "stars",
    "ci_low", "ci_high", "coef_pp", "se_pp",
    "n", "r_squared",
    "cohort_controls", "country_fe", "industry_fe",
    "n_fe_country", "n_fe_industry", "cov_type",
]

# Output names this module is allowed to write (acceptance C5). Any collision
# with an existing Step 5/6/step5b name would be a bug.
STEP13_OUTPUT_NAMES = {
    OUT_ACCESS, OUT_TIMING, OUT_CAPITAL, CAPITAL_COVERAGE, SAMPLE_AUDIT,
    CAPTIONS_FILE,
}

# --- Acceptance anchors ----------------------------------------------------
# The Step 5b headline eligible population (see step5b_fixed_horizon.config);
# not hard-coded elsewhere -- acceptance checks compare against the panel's
# own row count, this is documentation only.
COMMON_HORIZON_N = 31_257

# --- Engineering -----------------------------------------------------------
VERBOSE = False
