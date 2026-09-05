"""Tests for the Step 4 map set (step4_maps).

Unit tests use a tiny synthetic geometry and synthetic value frames so they need no
network and no committed data. Two integration tests run against the committed geometry
and Step 4 CSVs when present, and additionally assert the input CSVs are left untouched
(the module is read-only over its inputs).
"""

from __future__ import annotations

import hashlib

import geopandas as gpd
import pandas as pd
import pytest
from matplotlib.colors import TwoSlopeNorm
from shapely.geometry import box

from empirical_analysis.step4_maps import build, config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _synthetic_geom() -> gpd.GeoDataFrame:
    """Five European countries with trivial box geometries (EPSG:3035-ish frame)."""
    rows = [
        ("DE", "Germany"), ("FR", "France"), ("IT", "Italy"),
        ("ES", "Spain"), ("NL", "Netherlands"),
    ]
    geoms = [box(i, i, i + 1, i + 1) for i, _ in enumerate(rows)]
    return gpd.GeoDataFrame(
        {"iso_a2": [r[0] for r in rows],
         "admin": [r[1] for r in rows],
         "name": [r[1] for r in rows]},
        geometry=geoms, crs=config.MAP_CRS,
    )


def _synthetic_values() -> pd.DataFrame:
    return pd.DataFrame({
        "country": ["Germany", "France", "Italy", "Spain", "Netherlands"],
        "n_startups": [100, 80, 60, 40, 0],   # includes a 0 to exercise log flooring
        "lq": [0.4, 1.0, 2.5, 0.8, 0.0],
    })


# ---------------------------------------------------------------------------
# Crosswalk / config completeness
# ---------------------------------------------------------------------------
def test_crosswalk_covers_all_analytical_countries():
    assert len(config.ANALYTICAL_COUNTRIES) == 46
    for c in config.ANALYTICAL_COUNTRIES:
        assert c in config.COUNTRY_TO_ISO2
    # ISO2 codes must be unique so the geometry join is one-to-one.
    iso2 = list(config.COUNTRY_TO_ISO2.values())
    assert len(iso2) == len(set(iso2))


def test_map_specs_are_well_formed():
    stems = [s["output_stem"] for s in config.MAP_SPECS]
    assert len(stems) == len(set(stems)) == 5
    for spec in config.MAP_SPECS:
        assert spec["kind"] in {"log", "lq"}
        assert spec["source_file"] in {config.F4_02_FILE, config.T4_07_FILE, config.F4_03_FILE}


# ---------------------------------------------------------------------------
# Join behaviour (fails loudly)
# ---------------------------------------------------------------------------
def test_attach_value_joins_all_rows():
    geom = _synthetic_geom()
    merged = build._attach_value(geom, _synthetic_values(), "n_startups")
    assert len(merged) == 5
    assert merged["n_startups"].notna().all()
    assert merged.loc[merged["iso_a2"] == "DE", "n_startups"].iloc[0] == 100


def test_attach_value_raises_on_unknown_country():
    geom = _synthetic_geom()
    bad = pd.DataFrame({"country": ["Atlantis"], "n_startups": [5]})
    with pytest.raises(ValueError, match="no ISO2 mapping"):
        build._attach_value(geom, bad, "n_startups")


def test_attach_value_raises_when_country_missing_from_geometry():
    geom = _synthetic_geom().iloc[:3]  # drop Spain + Netherlands geometries
    df = _synthetic_values()           # still references Spain/Netherlands
    with pytest.raises(ValueError, match="no geometry"):
        build._attach_value(geom, df, "n_startups")


# ---------------------------------------------------------------------------
# LQ diverging norm is centred on the benchmark
# ---------------------------------------------------------------------------
def test_lq_norm_centered_on_benchmark():
    norm = TwoSlopeNorm(vmin=0.0, vcenter=config.LQ_CENTER, vmax=2.8)
    assert config.LQ_CENTER == 1.0
    assert norm(config.LQ_CENTER) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Rendering produces PNG + PDF
# ---------------------------------------------------------------------------
def test_render_log_and_lq_create_outputs(tmp_path):
    geom = _synthetic_geom()
    sources = {
        config.F4_02_FILE: _synthetic_values().rename(columns={}),
        config.F4_03_FILE: _synthetic_values(),
    }
    bounds = build._view_bounds(geom)

    log_spec = dict(config.MAP_SPECS[0])          # M1 log-scale count (n_startups, F4_02)
    lq_spec = dict(config.MAP_SPECS[4])           # M5 lq (F4_03)
    for spec in (log_spec, lq_spec):
        res = build.render_map(geom, sources, spec, bounds, tmp_path)
        assert res.n_countries == 5
        for name in res.outputs:
            assert (tmp_path / name).exists()
        assert any(n.endswith(".png") for n in res.outputs)
        assert any(n.endswith(".pdf") for n in res.outputs)


# ---------------------------------------------------------------------------
# Integration against committed inputs (skipped if absent) + read-only guarantee
# ---------------------------------------------------------------------------
def _inputs_available() -> bool:
    if not config.GEOMETRY_FILE.exists():
        return False
    return all((config.INPUT_DIR / f).exists()
               for f in {s["source_file"] for s in config.MAP_SPECS})


@pytest.mark.skipif(not _inputs_available(), reason="committed geometry/CSVs not present")
def test_build_all_and_inputs_unmodified(tmp_path):
    src_files = sorted({s["source_file"] for s in config.MAP_SPECS})
    before = {f: hashlib.sha256((config.INPUT_DIR / f).read_bytes()).hexdigest()
              for f in src_files}

    results = build.build_all(output_dir=tmp_path)

    assert len(results) == 5
    assert all(r.n_countries == 46 for r in results)
    assert (tmp_path / "maps_manifest.csv").exists()
    assert (tmp_path / "maps_report.txt").exists()
    for r in results:
        for name in r.outputs:
            assert (tmp_path / name).exists()

    after = {f: hashlib.sha256((config.INPUT_DIR / f).read_bytes()).hexdigest()
             for f in src_files}
    assert before == after, "input CSVs must not be modified by the map build"
