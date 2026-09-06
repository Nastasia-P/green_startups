"""Configuration for Step 5b (fixed five-year financing horizon).

Self-contained: input/output paths, group labels, the eligibility rule, the
five-year window length, the financing groupings (reused verbatim from Steps 1,
2 and 5) and the public/private investor groups all live here.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo root: step5b_fixed_horizon/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Firm table (Step 2 output) --------------------------------------------
_FIRM_TABLE_ANY = REPO_ROOT / "data" / "outputs" / "company_analysis.parquet"


def _resolve_firm_table() -> Path:
    env = os.environ.get("STEP5_FIRM_TABLE") or os.environ.get("STEP5B_FIRM_TABLE")
    if env and Path(env).exists():
        return Path(env)
    return _FIRM_TABLE_ANY


FIRM_TABLE: Path = _resolve_firm_table()

# --- Step 1 clean tables (deal-level cuts) ---------------------------------
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
    env = os.environ.get("STEP5B_OUTPUT_DIR") or os.environ.get("STEP5_OUTPUT_DIR")
    if env and (Path(env).exists() or Path(env).parent.exists()):
        return Path(env)
    return _OUTPUT_DIR_ANY


OUTPUT_DIR: Path = _resolve_output_dir()

# --- Group labels (rule N10) ----------------------------------------------
GREEN_LABEL = "Green start-ups"
OTHER_LABEL = "Other European start-ups"

# --- Fixed-horizon eligibility & window ------------------------------------
# Founding is year-only and the extract is 2026-07-07, so a first-five-year
# window [year_founded, year_founded + 5] is only guaranteed complete when
# year_founded + 5 <= 2025. Combined with the population's 10-year floor
# (year_founded >= 2016) the headline eligible set is founding years 2016-2020.
EXTRACT_DATE = "2026-07-07"
WINDOW_YEARS = 5
ELIGIBLE_MIN_FOUNDED = 2016
ELIGIBLE_MAX_FOUNDED = 2020  # 2020 + 5 = 2025 <= extract year - 1

ELIGIBILITY_RULE = (
    "year_founded in 2016-2020 inclusive (complete five-year window "
    "[year_founded, year_founded+5] observable by the 2026-07-07 extract)"
)

# --- Financing groupings (reused from Steps 1/2/5) -------------------------
VC_STAGE_GROUPS = {"Angel/Seed", "Early-stage VC", "Later-stage VC"}
GRANT_STAGE_GROUP = "Grant"
ACCELERATOR_STAGE_GROUP = "Accelerator/Incubator"

# Reporting order for stage_group (unlisted appended, then Unmapped).
STAGE_GROUP_ORDER = [
    "Grant", "Accelerator/Incubator", "Angel/Seed", "Early-stage VC",
    "Later-stage VC", "Growth/PE", "Debt", "Crowdfunding", "Spin-out/Corporate",
    "Other", "Unmapped",
]

# Public / private investor groups (reused from Step 2; no new taxonomy).
PUBLIC_INVESTOR_GRPS = {"Public/Government"}
PRIVATE_INVESTOR_GRPS = {"Independent VC", "Corporate"}

# --- Reporting -------------------------------------------------------------
LOW_N_FLAG = 30

# --- Output filenames (distinct from Step 5/6; never collide) --------------
OUT_ACCESS = "T_first5_access"
OUT_TIMING = "T_first5_timing"
OUT_CAPITAL = "T_first5_capital"
OUT_FIRST_CHANNEL = "T_first5_first_channel"
CAPTIONS_FILE = "captions_first5"
FIGURE_ACCESS = "F_first5_access"

# Existing Step 5 output names that must never be produced here (acceptance C4).
STEP5_PROTECTED_NAMES = {
    "T4_09_funding_access", "T4_09b_funding_access_by_cohort",
    "T4_10_total_raised_by_cohort", "T4_11_first_financing_size_by_stage",
    "T4_12_post_valuation", "T4_13_time_to_financing",
    "T4_14_first_financing_type", "T4_15_stage_composition",
    "T4_16_median_deal_size_by_stage", "T4_17_financing_trajectories",
    "F4_04_cumulative_financed", "captions_step5",
}

# --- Engineering -----------------------------------------------------------
VERBOSE = False
