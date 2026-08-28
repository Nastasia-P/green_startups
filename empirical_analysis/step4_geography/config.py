"""Configuration for Step 4 (geography).

Self-contained: input/output paths, the reporting minimums (decision D4), the group
labels, the PitchBook -> World Bank ISO2 country map, and the acceptance anchors all live
here.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root: step4_geography/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Firm table (Step 2 output, input here) --------------------------------
# Resolution order (first existing wins); --firm-table overrides all of these.
#   1. env var STEP4_FIRM_TABLE
#   2. the target machine's OneDrive company_analysis.parquet (Windows only)
#   3. <repo>/data/outputs/company_analysis.parquet
_FIRM_TABLE_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\company_analysis.parquet",
]
_FIRM_TABLE_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "outputs" / "company_analysis.parquet"),
]


def _resolve_firm_table() -> Path:
    env = os.environ.get("STEP4_FIRM_TABLE")
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

# --- World Bank population file (committed input for T4.7) -----------------
# Resolution order (first existing wins); --population overrides all of these.
#   1. env var STEP4_POPULATION
#   2. <repo>/data/sources/worldbank_population.csv
_POPULATION_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "sources" / "worldbank_population.csv"),
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
    return REPO_ROOT / "data" / "sources" / "worldbank_population.csv"


POPULATION_FILE: Path = _resolve_population()

# --- Output directory ------------------------------------------------------
# Resolution order (first usable wins); --output-dir overrides all.
#   1. env var STEP4_OUTPUT_DIR
#   2. the target machine's OneDrive chapter4_outputs folder (Windows only)
#   3. <repo>/data/outputs/chapter4
_OUTPUT_DIR_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\chapter4_outputs",
]


def _resolve_output_dir() -> Path:
    env = os.environ.get("STEP4_OUTPUT_DIR")
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

# --- Reporting minimums (decision D4, country floor dropped per user) -------
# The country floor is removed: every country with at least one start-up gets a
# row and thin green cells are marked with low_n_flag instead of being dropped.
# MIN_COUNTRY_N stays as an explicit "include all" knob (set to 1) so the filter
# can be reinstated by raising it. The old 500 gate is kept only as an
# informational sensitivity count in the acceptance report.
MIN_COUNTRY_N = 1            # report every country (no floor); raise to re-gate
MIN_COUNTRY_N_SENSITIVITY = 500   # the former floor, printed as a sensitivity count
MIN_CITY_N = 100             # cities keep their own floor (unchanged)
LOW_N_FLAG = 30              # flag any reported cell with green_n below this

# --- Concentration reporting ----------------------------------------------
TOP_COUNTRY_K = (5, 10)      # top-k country shares reported in T4.8
TOP_CITY_K = 5               # top-k city share reported in T4.8

# --- Robustness R1 (green_signal_group values) -----------------------------
STAGE1_LABEL = "Stage 1"     # vertical-tagged green firms
STAGE23_LABEL = "Stage 2+3"  # text-signal green firms

# --- Acceptance anchors ----------------------------------------------------
POP_TOTAL = 116_005
GREEN_TOTAL = 8_306
OTHER_TOTAL = POP_TOTAL - GREEN_TOTAL
# EU-wide green intensity: the fixed reference for the location quotient (rule N9).
EU_GREEN_INTENSITY = round(GREEN_TOTAL / POP_TOTAL, 6)
# Reference Spearman(startups_per_million, green_intensity) from the spec.
SPEARMAN_REFERENCE = -0.67

# --- World Bank fetch (fetch_worldbank.py) ---------------------------------
# Indicator SP.POP.TOTL (total population). We take each country's most recent value
# (World Bank returns a single, uniform latest year across all countries), so the
# per-capita cross-check uses one consistent vintage and one source for every country.
WORLDBANK_INDICATOR = "SP.POP.TOTL"
WORLDBANK_BASE_URL = "https://api.worldbank.org/v2"

# PitchBook hq_country -> World Bank ISO alpha-2 code. World Bank covers all 46
# start-up countries (including the UK, Russia, Gibraltar and the micro-states), so no
# country is left with NA population. Note WB uses GR for Greece and GB for the UK.
COUNTRY_TO_ISO2 = {
    "Albania": "AL",
    "Andorra": "AD",
    "Austria": "AT",
    "Belarus": "BY",
    "Belgium": "BE",
    "Bosnia and Herzegovina": "BA",
    "Bulgaria": "BG",
    "Croatia": "HR",
    "Cyprus": "CY",
    "Czech Republic": "CZ",
    "Denmark": "DK",
    "Estonia": "EE",
    "Finland": "FI",
    "France": "FR",
    "Germany": "DE",
    "Gibraltar": "GI",
    "Greece": "GR",
    "Hungary": "HU",
    "Iceland": "IS",
    "Ireland": "IE",
    "Italy": "IT",
    "Kosovo": "XK",
    "Latvia": "LV",
    "Liechtenstein": "LI",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Malta": "MT",
    "Moldova": "MD",
    "Monaco": "MC",
    "Montenegro": "ME",
    "Netherlands": "NL",
    "North Macedonia": "MK",
    "Norway": "NO",
    "Poland": "PL",
    "Portugal": "PT",
    "Romania": "RO",
    "Russia": "RU",
    "San Marino": "SM",
    "Serbia": "RS",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Ukraine": "UA",
    "United Kingdom": "GB",
}

# --- Engineering -----------------------------------------------------------
VERBOSE = False
