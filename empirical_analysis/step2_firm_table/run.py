"""CLI entry point for Step 2: build the firm-level table.

Examples
--------
Build from the local Step 1 outputs:

    python -m empirical_analysis.step2_firm_table.run --clean-dir data/outputs/clean_tables

The clean-tables directory resolves as: --clean-dir > STEP2_CLEAN_DIR > the target
machine's OneDrive clean_tables folder > <repo>/data/outputs/clean_tables >
<repo>/data/interim.

Outputs resolve as: --output-dir > STEP2_OUTPUT_DIR > the target machine's OneDrive
"09_Python_Empirical Analysis" folder > <repo>/data/outputs.

Requires pyarrow (input and output are Parquet).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from .build import acceptance_report, build_firm_table, write_outputs
from .sources import load_clean_tables, load_spine


def _report_clean_dir(clean_dir: Path) -> None:
    print(f"[step2] clean-tables dir: {clean_dir}")
    print(f"[step2] clean-tables dir exists: {clean_dir.exists()}")
    if not clean_dir.exists():
        print("[step2] WARNING: clean-tables dir not found -> firm table will be spine-only. "
              "Run Step 1 first, or pass --clean-dir.")
        return
    present = {p.stem for p in clean_dir.glob("*.parquet")}
    missing = [t for t in config.CLEAN_TABLES if t not in present]
    if missing:
        print(f"[step2] WARNING: missing clean table(s): {missing}")
    else:
        print("[step2] all required clean tables found")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Step 2: build the firm-level table")
    parser.add_argument("--clean-dir", type=Path, default=None,
                        help="Directory holding the Step 1 clean parquet tables")
    parser.add_argument("--spine", type=Path, default=None,
                        help="Company spine CSV (startups_stages_filtered.csv)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Where to write company_analysis.parquet")
    parser.add_argument("--ledger", type=Path, default=None,
                        help="Green ledger; defaults to population_key from the clean dir")
    parser.add_argument("--verbose", action="store_true",
                        help="Log per-table paths and row counts")
    args = parser.parse_args(argv)

    if args.verbose:
        config.VERBOSE = True

    clean_dir = Path(args.clean_dir or config.CLEAN_DIR)
    output_dir = Path(args.output_dir or config.OUTPUT_DIR)

    print("[step2] mode=build")
    _report_clean_dir(clean_dir)
    print(f"[step2] output dir: {output_dir}")

    tables = load_clean_tables(clean_dir)
    population_key = tables.get("population_key")
    if population_key is None or population_key.empty:
        # Fall back to reading the ledger directly if population_key is absent.
        from ..step1_clean_raw_data.sources import load_population_key
        population_key = load_population_key(args.ledger)
        tables["population_key"] = population_key
        print("[step2] population_key.parquet missing -> loaded population from the ledger")

    spine_frame = load_spine(population_key, spine_path=args.spine)
    result = build_firm_table(tables, spine_frame)
    write_outputs(result, output_dir=output_dir)

    print("\n=== Acceptance checks ===")
    for line in acceptance_report(result):
        print(line)

    print("\n=== Coverage (green vs other), selected columns ===")
    cov = result.coverage
    show = cov[cov["column"].isin([
        "employees", "total_raised", "first_deal_date", "first_deal_type",
        "n_investors_lifetime", "first_vc_date",
    ])]
    if not show.empty:
        print(show.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
