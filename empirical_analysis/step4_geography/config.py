"""Configuration for Step 4 (geography).

Self-contained: input/output paths, the reporting minimums (decision D4), the group
labels, the PitchBook -> Eurostat country map, and the acceptance anchors all live
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

# --- Eurostat population file (committed input for T4.7) -------------------
# Resolution order (first existing wins); --population overrides all of these.
#   1. env var STEP4_POPULATION
#   2. <repo>/data/sources/eurostat_population.csv
_POPULATION_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "sources" / "eurostat_population.csv"),
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
    return REPO_ROOT / "data" / "sources" / "eurostat_population.csv"


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

# --- Reporting minimums (decision D4) --------------------------------------
MIN_COUNTRY_N = 500          # a country needs this many start-ups to get a row
MIN_COUNTRY_N_SENSITIVITY = 800   # printed as a sensitivity count in acceptance
MIN_CITY_N = 100             # a city needs this many start-ups to get a row
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

# --- Eurostat fetch (fetch_eurostat.py) ------------------------------------
EUROSTAT_DATASET = "demo_pjan"          # population on 1 January
EUROSTAT_YEARS = (2024, 2023, 2022)     # try most recent first, fall back
EUROSTAT_BASE_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
)

# PitchBook hq_country -> Eurostat geo code (rule: keep unmatched as NA population).
# Eurostat uses EL for Greece and UK for the United Kingdom; non-EU members it still
# publishes (CH, NO, candidate/neighbour countries) are included where available.
COUNTRY_TO_EUROSTAT = {
    "Albania": "AL",
    "Austria": "AT",
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
    "Greece": "EL",
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
    "Montenegro": "ME",
    "Netherlands": "NL",
    "North Macedonia": "MK",
    "Norway": "NO",
    "Poland": "PL",
    "Portugal": "PT",
    "Romania": "RO",
    "Serbia": "RS",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Ukraine": "UA",
    "United Kingdom": "UK",
    # No Eurostat demo_pjan entry (kept with NA population):
    #   Andorra, Belarus, Gibraltar, Monaco, Russia, San Marino
}

# --- Engineering -----------------------------------------------------------
VERBOSE = False
