"""Configuration for the Step 4 map set (step4_maps).

Self-contained: input/output paths, the committed geometry path, the country ->
ISO2 join key (reused from Step 4), the European projection, and the five map
specifications all live here.

The maps read only existing Step 4 CSV outputs; no firm-level data is touched and no
new measure is computed.
"""

from __future__ import annotations

import os
from pathlib import Path

# Reuse the single source of truth for the PitchBook country -> ISO alpha-2 map so the
# geometry join key never drifts from Step 4.
from empirical_analysis.step4_geography.config import COUNTRY_TO_ISO2

# Repository root: step4_maps/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Input CSV directory (Step 4 outputs) ----------------------------------
# Resolution order (first existing wins); --input-dir overrides all of these.
#   1. env var STEP4_MAPS_INPUT_DIR
#   2. <repo>/data/outputs/chapter4
_INPUT_DIR_CANDIDATES = [
    str(REPO_ROOT / "data" / "outputs" / "chapter4"),
]


def _resolve_input_dir() -> Path:
    env = os.environ.get("STEP4_MAPS_INPUT_DIR")
    for cand in ([env] if env else []) + _INPUT_DIR_CANDIDATES:
        try:
            path = Path(cand)
            if path.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "outputs" / "chapter4"


INPUT_DIR: Path = _resolve_input_dir()

# --- Geometry file (committed Natural Earth subset) ------------------------
# Resolution order (first existing wins); --geometry overrides all of these.
#   1. env var STEP4_MAPS_GEOMETRY
#   2. <repo>/data/sources/europe_ne50m.geojson
_GEOMETRY_CANDIDATES = [
    str(REPO_ROOT / "data" / "sources" / "europe_ne50m.geojson"),
]


def _resolve_geometry() -> Path:
    env = os.environ.get("STEP4_MAPS_GEOMETRY")
    for cand in ([env] if env else []) + _GEOMETRY_CANDIDATES:
        try:
            path = Path(cand)
            if path.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "sources" / "europe_ne50m.geojson"


GEOMETRY_FILE: Path = _resolve_geometry()

# --- Output directory ------------------------------------------------------
# Resolution order (first usable wins); --output-dir overrides all.
#   1. env var STEP4_MAPS_OUTPUT_DIR
#   2. <repo>/data/outputs/chapter4/maps
def _resolve_output_dir() -> Path:
    env = os.environ.get("STEP4_MAPS_OUTPUT_DIR")
    if env:
        return Path(env)
    return REPO_ROOT / "data" / "outputs" / "chapter4" / "maps"


OUTPUT_DIR: Path = _resolve_output_dir()

# --- Geometry fetch (fetch_geometry.py) ------------------------------------
# Natural Earth vector, GitHub mirror. 50m Admin-0 covers 45/46 countries; Gibraltar
# exists only at 10m, so that single polygon is appended from the 10m layer.
NE_BASE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
)
NE_50M_LAYER = "ne_50m_admin_0_countries"
NE_10M_LAYER = "ne_10m_admin_0_countries"
# Country only present in the 10m layer (UK overseas territory, a speck at Europe scale).
GEOMETRY_ONLY_10M_ISO2 = ("GI",)
# Natural Earth ISO alpha-2 field that is populated even where ISO_A2 is -99
# (France, Norway, Kosovo). This is the geometry join key.
NE_ISO2_FIELD = "ISO_A2_EH"
# Fields carried into the committed subset (join key + human-readable labels).
GEOMETRY_KEEP_FIELDS = ("iso_a2", "admin", "name")

# --- Projection and viewport -----------------------------------------------
# EPSG:3035 = ETRS89 / LAEA Europe (equal-area). The view window is computed from the
# reprojected geometry excluding Russia so Siberia does not blow out the frame; Russia
# is still drawn and simply extends past the right edge.
MAP_CRS = "EPSG:3035"
# Clip geometry to a European window (lon/lat) BEFORE reprojecting, so overseas
# territories carried in the Natural Earth Admin-0 polygons (e.g. the Dutch/French
# Caribbean, French Guiana, the Azores, Canary and Madeira islands) are not drawn and
# do not blow out the map frame. Each of the 46 countries still has its mainland (or,
# for Iceland, its whole territory) inside this box, so none is dropped; only the
# off-continent pieces are removed. Values are unaffected (the count belongs to the
# country, not the clipped geometry).
EUROPE_BBOX_LONLAT = (-25.0, 34.0, 45.0, 72.0)  # (min_lon, min_lat, max_lon, max_lat)
VIEW_EXCLUDE_ISO2 = ("RU",)   # excluded from view-bounds calc only, not from the map
VIEW_MARGIN_FRAC = 0.04       # padding added around the computed view bounds

# --- Location quotient bins (Map 5) ----------------------------------------
LQ_CENTER = 1.0               # European benchmark: LQ = 1
# Diverging class edges around the benchmark (over- vs under-representation).
LQ_BINS = (0.0, 0.5, 0.8, 1.25, 2.0, float("inf"))
LQ_BIN_LABELS = ("< 0.5", "0.5 - 0.8", "0.8 - 1.25", "1.25 - 2.0", "> 2.0")

# --- Rendering defaults ----------------------------------------------------
SEQUENTIAL_CMAP = "viridis"
DIVERGING_CMAP = "RdBu_r"
FIG_SIZE = (9.0, 9.5)
PNG_DPI = 200
MISSING_COLOR = "#d9d9d9"     # geometry present but no data (grey)
EDGE_COLOR = "white"          # thin light borders (reference-map style)
EDGE_WIDTH = 0.25
# Colorbar ("legend") font sizes.
CBAR_LABEL_FONTSIZE = 14
CBAR_TICK_FONTSIZE = 12

# --- Input file names ------------------------------------------------------
F4_02_FILE = "F4_02_green_count_by_country.csv"
T4_07_FILE = "T4_07_per_capita_crosscheck.csv"
F4_03_FILE = "F4_03_lq_by_country.csv"

# --- Map specifications ----------------------------------------------------
# Each map declares its source CSV, the value column, colour handling, and outputs.
# `kind` drives classification: "quantile" (sequential, k classes) or "lq" (diverging,
# centred at LQ_CENTER with fixed LQ_BINS).
MAP_SPECS = (
    {
        "id": "M1",
        "block": "A. Absolute geographic distribution",
        "title": "Total European start-ups by country",
        "source_file": F4_02_FILE,
        "column": "n_startups",
        "kind": "log",
        "value_fmt": "{:.0f}",
        "legend_title": "Start-ups (count)",
        "output_stem": "F4_M1_total_startups",
    },
    {
        "id": "M2",
        "block": "A. Absolute geographic distribution",
        "title": "Green start-ups by country",
        "source_file": F4_02_FILE,
        "column": "n_green",
        "kind": "log",
        "value_fmt": "{:.0f}",
        "legend_title": "Green start-ups (count)",
        "output_stem": "F4_M2_green_startups",
    },
    {
        "id": "M3",
        "block": "B. Population-adjusted geographic density",
        "title": "Total start-ups per million inhabitants",
        "source_file": T4_07_FILE,
        "column": "startups_per_million",
        "kind": "log",
        "value_fmt": "{:.1f}",
        "legend_title": "Start-ups per million",
        "output_stem": "F4_M3_startups_per_million",
    },
    {
        "id": "M4",
        "block": "B. Population-adjusted geographic density",
        "title": "Green start-ups per million inhabitants",
        "source_file": T4_07_FILE,
        "column": "green_per_million",
        "kind": "log",
        "value_fmt": "{:.1f}",
        "legend_title": "Green start-ups per million",
        "output_stem": "F4_M4_green_per_million",
    },
    {
        "id": "M5",
        "block": "C. Relative green specialisation",
        "title": "Green-start-up location quotient (LQ)",
        "source_file": F4_03_FILE,
        "column": "lq",
        "kind": "lq",
        "value_fmt": "{:.3f}",
        "legend_title": "Green LQ (benchmark = 1.0)",
        "output_stem": "F4_M5_green_lq",
    },
)

# All 46 analytical countries (keys of the ISO2 map) -- used for join validation.
ANALYTICAL_COUNTRIES = tuple(sorted(COUNTRY_TO_ISO2))

# --- Engineering -----------------------------------------------------------
VERBOSE = False
