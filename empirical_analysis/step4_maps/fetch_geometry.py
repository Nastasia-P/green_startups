"""Fetch and subset the committed country geometry for the Step 4 map set.

Downloads Natural Earth Admin-0 country polygons from the nvkelso/natural-earth-vector
GitHub mirror, subsets them to the 46 analytical countries via the ISO alpha-2 key, and
writes a small committed GeoJSON (``data/sources/europe_ne50m.geojson``).

The 1:50m layer covers 45/46 countries; Gibraltar exists only in the 1:10m layer, so
that single polygon is appended from 10m. Run once (network required); the resulting
GeoJSON is committed so map rendering is fully offline afterwards.

Usage
-----
    python -m empirical_analysis.step4_maps.fetch_geometry
    python -m empirical_analysis.step4_maps.fetch_geometry --output data/sources/europe_ne50m.geojson
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import config


def _layer_url(layer: str) -> str:
    return f"{config.NE_BASE_URL}/{layer}.geojson"


def _subset(gdf: gpd.GeoDataFrame, iso2_wanted: set[str]) -> gpd.GeoDataFrame:
    """Return the features whose ISO_A2_EH is in ``iso2_wanted`` with normalised fields."""
    field = config.NE_ISO2_FIELD
    if field not in gdf.columns:
        raise KeyError(f"Natural Earth layer is missing the {field!r} field.")
    keep = gdf[gdf[field].isin(iso2_wanted)].copy()
    keep["iso_a2"] = keep[field]
    keep["admin"] = keep["ADMIN"]
    keep["name"] = keep["NAME"]
    return keep[["iso_a2", "admin", "name", "geometry"]]


def build_geometry() -> gpd.GeoDataFrame:
    """Fetch, subset and combine the country geometry for all 46 analytical countries."""
    wanted = set(config.COUNTRY_TO_ISO2.values())
    only_10m = set(config.GEOMETRY_ONLY_10M_ISO2)
    from_50m = wanted - only_10m

    print(f"[geometry] downloading {config.NE_50M_LAYER} ...")
    g50 = gpd.read_file(_layer_url(config.NE_50M_LAYER))
    sub50 = _subset(g50, from_50m)

    parts = [sub50]
    if only_10m:
        print(f"[geometry] downloading {config.NE_10M_LAYER} for {sorted(only_10m)} ...")
        g10 = gpd.read_file(_layer_url(config.NE_10M_LAYER))
        sub10 = _subset(g10, only_10m)
        parts.append(sub10)

    combined = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True),
        crs=g50.crs,
    )

    got = set(combined["iso_a2"])
    missing = wanted - got
    if missing:
        rev = {v: k for k, v in config.COUNTRY_TO_ISO2.items()}
        names = sorted(rev.get(m, m) for m in missing)
        raise RuntimeError(
            f"Geometry fetch missing {len(missing)} country(ies): {names}. "
            "The committed GeoJSON would be incomplete."
        )
    return combined.sort_values("iso_a2").reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fetch/subset the Step 4 map geometry.")
    p.add_argument("--output", type=Path, default=None,
                   help=f"Output GeoJSON (default: {config.GEOMETRY_FILE}).")
    args = p.parse_args(argv)

    out = args.output or config.GEOMETRY_FILE
    out.parent.mkdir(parents=True, exist_ok=True)

    gdf = build_geometry()
    gdf.to_file(out, driver="GeoJSON")
    print(f"[geometry] wrote {len(gdf)} countries -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
