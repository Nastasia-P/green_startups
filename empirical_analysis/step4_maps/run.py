"""Step 4 map set CLI: render the five European choropleth maps.

Reads only the existing Step 4 CSV outputs and the committed geometry; writes PNG + PDF
maps plus a manifest and report into the output directory.

Examples
--------
    python -m empirical_analysis.step4_maps.run --verbose
    python -m empirical_analysis.step4_maps.run \
        --input-dir data/outputs/chapter4 \
        --geometry data/sources/europe_ne50m.geojson \
        --output-dir data/outputs/chapter4/maps

Overridable inputs (first match wins):
    --input-dir   / env STEP4_MAPS_INPUT_DIR  (default data/outputs/chapter4)
    --geometry    / env STEP4_MAPS_GEOMETRY   (default data/sources/europe_ne50m.geojson)
    --output-dir  / env STEP4_MAPS_OUTPUT_DIR (default data/outputs/chapter4/maps)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from .build import build_all, report_lines, load_geometry


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Step 4 map set (five European choropleths).")
    p.add_argument("--input-dir", type=Path, default=None,
                   help="Directory holding the Step 4 CSV outputs "
                        "(default data/outputs/chapter4).")
    p.add_argument("--geometry", type=Path, default=None,
                   help="Committed country GeoJSON "
                        "(default data/sources/europe_ne50m.geojson).")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Directory to write map images (default data/outputs/chapter4/maps).")
    p.add_argument("--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config.VERBOSE = args.verbose

    input_dir = args.input_dir or config.INPUT_DIR
    geometry = args.geometry or config.GEOMETRY_FILE
    output_dir = args.output_dir or config.OUTPUT_DIR

    print("[maps] input dir :", input_dir)
    print("[maps] geometry  :", geometry)
    print("[maps] output dir:", output_dir)

    results = build_all(input_dir=input_dir, geometry_path=geometry, output_dir=output_dir)

    n_geom = len(load_geometry(geometry))
    print("\n[maps] report")
    for line in report_lines(results, n_geom):
        print("  " + line)
    print(f"[maps] wrote {len(results)} maps (PNG+PDF) + manifest + report to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
