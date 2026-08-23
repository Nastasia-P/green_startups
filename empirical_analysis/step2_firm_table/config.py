"""Configuration for Step 2 (build the firm-level table).

Self-contained: paths, cohort bins, the VC and private-investor groupings, and the
European country set all live here, so the module can be read and run without
opening another document.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root: step2_firm_table/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Company spine (committed) --------------------------------------------
# 94-column merged population: 116,005 firms with the PitchBook company columns.
SPINE = REPO_ROOT / "startups_stages_filtered.csv"

# Only the spine columns Step 2 needs are read.
SPINE_USECOLS = [
    "CompanyID",
    "YearFounded",
    "HQCountry",
    "HQCity",
    "Employees",
    "BusinessStatus",
    "PrimaryIndustrySector",
    "PrimaryIndustryGroup",
    "PrimaryIndustryCode",
    "TotalRaised",
]

# --- Step 1 clean tables (input) ------------------------------------------
# Resolution order (first existing wins); --clean-dir overrides all of these.
#   1. env var STEP2_CLEAN_DIR
#   2. the target machine's OneDrive clean_tables folder (Windows only)
#   3. <repo>/data/outputs/clean_tables
#   4. <repo>/data/interim
_CLEAN_DIR_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\clean_tables",
]
_CLEAN_DIR_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "outputs" / "clean_tables"),
    str(REPO_ROOT / "data" / "interim"),
]

# The five clean tables Step 2 consumes.
CLEAN_TABLES = [
    "population_key",
    "deals_clean",
    "deal_investors_clean",
    "company_investors_clean",
    "investors_clean",
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
# Resolution order (first usable wins); --output-dir overrides all of these.
#   1. env var STEP2_OUTPUT_DIR
#   2. the target machine's OneDrive 09_Python_Empirical Analysis folder (Windows)
#   3. <repo>/data/outputs
_OUTPUT_DIR_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis",
]


def _resolve_output_dir() -> Path:
    env = os.environ.get("STEP2_OUTPUT_DIR")
    win = _OUTPUT_DIR_CANDIDATES_WIN if os.name == "nt" else []
    for cand in ([env] if env else []) + win:
        try:
            path = Path(cand)
            if path.exists() or path.parent.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "outputs"


OUTPUT_DIR: Path = _resolve_output_dir()

OUTPUT_TABLE = "company_analysis.parquet"

# --- Derived-column rules --------------------------------------------------
# Reference year for age and funding-lag (the extract year).
REFERENCE_YEAR = 2026

# Founding cohorts (inclusive edges). Founding years in this population are a
# clean 2016-2026, so every firm lands in exactly one bin.
COHORT_BINS = [
    (2016, 2018, "2016-2018"),
    (2019, 2021, "2019-2021"),
    (2022, 2024, "2022-2024"),
    (2025, 2026, "2025-2026"),
]

# Employee size bands (lower bound inclusive, upper bound inclusive).
EMPLOYEE_BANDS = [
    (1, 10, "1-10"),
    (11, 50, "11-50"),
    (51, 200, "51-200"),
    (201, None, "200+"),
]

# --- Financing groupings ---------------------------------------------------
# stage_group values that count as "VC" for any_vc / n_rounds_vc / first_vc_date.
# Spec V1.19/V1.21 include seed. Drop "Angel/Seed" here if the first-VC literature
# comparison should use institutional VC only.
VC_STAGE_GROUPS = {"Angel/Seed", "Early-stage VC", "Later-stage VC"}

# Investor groups used by the public/private measures (spec V1.38).
PUBLIC_INVESTOR_GRPS = {"Public/Government"}
PRIVATE_INVESTOR_GRPS = {"Independent VC", "Corporate"}

# --- Investor origin (spec V4.6) -------------------------------------------
# Countries counted as European for the domestic / EU-cross-border / non-European
# split. Broad by design (EU27 + EEA + UK + Switzerland + European neighbours).
# Validate against the observed investor_country values before finalising Step 6.
EUROPEAN_COUNTRIES = {
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic",
    "Denmark", "Estonia", "Finland", "France", "Germany", "Greece", "Hungary",
    "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta",
    "Netherlands", "Poland", "Portugal", "Romania", "Slovakia", "Slovenia",
    "Spain", "Sweden",
    # EEA / EFTA and the UK.
    "Iceland", "Liechtenstein", "Norway", "Switzerland", "United Kingdom",
    # Wider Europe / common PitchBook spellings.
    "Albania", "Andorra", "Belarus", "Bosnia and Herzegovina", "Faroe Islands",
    "Gibraltar", "Guernsey", "Isle of Man", "Jersey", "Kosovo", "Moldova",
    "Monaco", "Montenegro", "North Macedonia", "San Marino", "Serbia",
    "Ukraine", "Vatican City",
}

# --- Acceptance anchors ----------------------------------------------------
SPEC_POP_TOTAL = 116_005
# Distinct financed firms in the Step 1 cleaning audit (deals_clean).
EXPECTED_FINANCED = 47_714

# --- Engineering -----------------------------------------------------------
VERBOSE = False
