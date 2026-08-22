"""CLI entry point for Step 1: clean the raw data.

Examples
--------
Smoke test on the committed sample (no raw extract needed):

    python -m empirical_analysis.step1_clean_raw_data.run --mode fixture

Full run against the real extract:

    python -m empirical_analysis.step1_clean_raw_data.run --mode full

The extract directory resolves as: --extract-dir > PITCHBOOK_EXTRACT_DIR >
the target machine's OneDrive esade_20260707 folder > <repo>/data/raw.

Outputs resolve as: --output-dir > STEP1_OUTPUT_DIR > the target machine's
OneDrive "09_Python_Empirical Analysis\\clean_tables" folder > <repo>/data/interim.

Requires pyarrow (tables are written as Parquet):  pip install pyarrow
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from .clean import acceptance_report, build_all, write_outputs
from .sources import load_population_key, make_source

REQUIRED_TABLES = [
    "Deal.csv",
    "DealInvestorRelation.csv",
    "CompanyInvestorRelation.csv",
    "Investor.csv",
    "CompanyIndustryRelation.csv",
    "CompanyVerticalRelation.csv",
    "CompanyEmployeeHistoryRelation.csv",
]


def _report_extract_dir(extract_dir: Path) -> None:
    """Print the resolved extract directory and confirm the needed files are there."""
    print(f"[step1] extract dir: {extract_dir}")
    print(f"[step1] extract dir exists: {extract_dir.exists()}")
    if not extract_dir.exists():
        print("[step1] WARNING: extract dir not found -> every table will be empty. "
              "Pass --extract-dir or set PITCHBOOK_EXTRACT_DIR.")
        return
    present = {p.name for p in extract_dir.glob("*.csv")}
    print(f"[step1] {len(present)} CSV file(s) present")
    missing = [t for t in REQUIRED_TABLES if t not in present]
    if missing:
        print(f"[step1] WARNING: missing expected table(s): {missing}")
    else:
        print("[step1] all required tables found")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Step 1: clean the raw PitchBook data")
    parser.add_argument("--mode", choices=["fixture", "full"], default="fixture")
    parser.add_argument("--extract-dir", type=Path, default=None,
                        help="Directory holding the raw PitchBook CSVs (mode=full)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Where to write the clean tables")
    parser.add_argument("--ledger", type=Path, default=None,
                        help="Green classification ledger defining the population")
    parser.add_argument("--verbose", action="store_true",
                        help="Log per-table paths and row counts")
    args = parser.parse_args(argv)

    if args.verbose or args.mode == "full":
        config.VERBOSE = True

    extract_dir = Path(args.extract_dir or config.EXTRACT_DIR)
    output_dir = Path(args.output_dir or config.OUTPUT_DIR)

    print(f"[step1] mode={args.mode}")
    if args.mode == "full":
        _report_extract_dir(extract_dir)
    print(f"[step1] output dir: {output_dir}")

    population_key = load_population_key(args.ledger)
    source = make_source(args.mode, extract_dir=extract_dir)
    result = build_all(source, population_key)
    write_outputs(result, output_dir=output_dir)

    print("\n=== Row counts ===")
    for name, df in result.tables.items():
        print(f"  {name:<26} {len(df):>10,} rows")

    print("\n=== Acceptance checks ===")
    for line in acceptance_report(result):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
