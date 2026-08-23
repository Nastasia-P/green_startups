"""Inspect the Step 1 clean tables from the command line.

Parquet is binary, so it cannot be opened in a text editor or Excel. This gives
you the same three things a viewer would, without installing one.

Examples
--------
List every table in the output directory with its row count:

    python -m empirical_analysis.step1_clean_raw_data.peek --list

Look at one table (shape, dtypes, first rows):

    python -m empirical_analysis.step1_clean_raw_data.peek deals_clean

Only some columns, more rows:

    python -m empirical_analysis.step1_clean_raw_data.peek deals_clean \
        --columns company_id deal_date stage_group deal_size --rows 30

Count the values of one column instead of listing rows:

    python -m empirical_analysis.step1_clean_raw_data.peek deals_clean --value-counts stage_group

Write a CSV sample you can open in Excel:

    python -m empirical_analysis.step1_clean_raw_data.peek deals_clean --to-csv --rows 1000

The output directory resolves exactly as it does for `run`: --output-dir >
STEP1_OUTPUT_DIR > the target machine's OneDrive folder > <repo>/data/interim.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import config


def _resolve_path(output_dir: Path, name: str) -> Path:
    """Accept a bare table name, a file name, or a full path."""
    candidate = Path(name)
    if candidate.is_file():
        return candidate
    if candidate.suffix:
        return output_dir / candidate.name
    return output_dir / f"{name}.parquet"


def _row_count(path: Path) -> str:
    """Row count from the Parquet footer, without reading the data."""
    try:
        import pyarrow.parquet as pq

        return f"{pq.ParquetFile(path).metadata.num_rows:,}"
    except Exception:
        return "?"


def _list_tables(output_dir: Path) -> int:
    if not output_dir.exists():
        print(f"[peek] output dir not found: {output_dir}")
        print("[peek] run the pipeline first, or pass --output-dir.")
        return 1

    print(f"[peek] output dir: {output_dir}\n")
    parquet = sorted(output_dir.glob("*.parquet"))
    if parquet:
        print("Parquet tables (binary - use this tool or pandas):")
        for path in parquet:
            print(f"  {path.stem:<28} {_row_count(path):>12} rows")
    csvs = sorted(output_dir.glob("*.csv"))
    if csvs:
        print("\nCSV files (open these directly in Excel):")
        for path in csvs:
            print(f"  {path.name}")
    if not parquet and not csvs:
        print("  (nothing here yet)")
    return 0


def _show(path: Path, args: argparse.Namespace) -> int:
    if not path.exists():
        print(f"[peek] not found: {path}")
        print("[peek] use --list to see what is available.")
        return 1

    frame = pd.read_parquet(path, columns=args.columns)

    print(f"[peek] {path}")
    print(f"[peek] {len(frame):,} rows x {frame.shape[1]} columns\n")

    if args.value_counts:
        if args.value_counts not in frame.columns:
            print(f"[peek] no column named '{args.value_counts}'")
            print(f"[peek] columns are: {list(frame.columns)}")
            return 1
        print(f"=== {args.value_counts} ===")
        print(frame[args.value_counts].value_counts(dropna=False).to_string())
        return 0

    print("=== Columns ===")
    print(frame.dtypes.to_string())

    print(f"\n=== First {min(args.rows, len(frame))} rows ===")
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(frame.head(args.rows).to_string())

    if args.to_csv:
        out = path.with_name(f"_peek_{path.stem}.csv")
        frame.head(args.rows).to_csv(out, index=False)
        print(f"\n[peek] wrote {out}  ({min(args.rows, len(frame)):,} rows)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the Step 1 clean tables")
    parser.add_argument("table", nargs="?",
                        help="Table name (e.g. deals_clean), file name, or full path")
    parser.add_argument("--list", action="store_true",
                        help="List the tables in the output directory and exit")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Where the clean tables live")
    parser.add_argument("--columns", nargs="+", default=None,
                        help="Read only these columns")
    parser.add_argument("--rows", type=int, default=20,
                        help="How many rows to show, or export with --to-csv")
    parser.add_argument("--value-counts", metavar="COLUMN", default=None,
                        help="Count the values of one column instead of showing rows")
    parser.add_argument("--to-csv", action="store_true",
                        help="Also write the shown rows next to the source as _peek_<name>.csv")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir or config.OUTPUT_DIR)

    if args.list or not args.table:
        return _list_tables(output_dir)
    return _show(_resolve_path(output_dir, args.table), args)


if __name__ == "__main__":
    raise SystemExit(main())
