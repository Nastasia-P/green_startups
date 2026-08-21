"""CLI entry point for the T4.0 coverage audit.

Examples
--------
Smoke test on the committed fixture (relational tables from preview_summary.csv;
company fields from the real merged population):

    python -m empirical_analysis.chapter4.run --mode fixture

Full run against the 43-table extract. The extract directory resolves in this
order: --extract-dir flag > PITCHBOOK_EXTRACT_DIR env var > the target machine's
OneDrive folder > <repo>/data/raw (see config._resolve_extract_dir).

    # target machine (auto-detects the OneDrive esade_20260707 folder):
    python -m empirical_analysis.chapter4.run --mode full

    # explicit path or env var override:
    python -m empirical_analysis.chapter4.run --mode full --extract-dir /path/to/pitchbook
    PITCHBOOK_EXTRACT_DIR=/path/to/pitchbook python -m empirical_analysis.chapter4.run --mode full

Outputs are written to config.OUTPUT_DIR, resolved in this order: --output-dir
flag > T4_OUTPUT_DIR env var > the target machine's OneDrive
"09_Python_Empirical Analysis" folder > <repo>/data/outputs
(see config._resolve_output_dir).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from .coverage_audit import acceptance_report, build_coverage_audit, write_outputs


def _report_extract_dir() -> None:
    """Print the resolved extract directory and the CSV files found there."""
    ext = Path(config.FULL_EXTRACT_DIR)
    print(f"[T4.0] extract dir: {ext}")
    print(f"[T4.0] extract dir exists: {ext.exists()}")
    if not ext.exists():
        print("[T4.0] WARNING: extract dir not found -> deal/investor rows will be 0. "
              "Pass --extract-dir or set PITCHBOOK_EXTRACT_DIR.")
        return
    csvs = sorted(p.name for p in ext.glob("*.csv"))
    print(f"[T4.0] {len(csvs)} CSV file(s) present:")
    for name in csvs:
        print(f"    - {name}")
    required = ["Deal", "CompanyInvestorRelation", "Investor", "CompanyEmployeeHistoryRelation"]
    missing = [f"{r}.csv" for r in required if f"{r}.csv" not in csvs]
    if missing:
        print(f"[T4.0] WARNING: missing expected table(s): {missing}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T4.0 field completeness by group")
    parser.add_argument("--mode", choices=["fixture", "full"], default="fixture")
    parser.add_argument("--extract-dir", type=Path, default=None,
                        help="Directory of the raw PitchBook tables (mode=full)")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true",
                        help="Log per-table file paths and row counts")
    args = parser.parse_args(argv)

    if args.extract_dir is not None:
        config.FULL_EXTRACT_DIR = args.extract_dir
    if args.verbose or args.mode == "full":
        config.VERBOSE = True

    out_dir = args.output_dir or config.OUTPUT_DIR
    if args.mode == "full":
        _report_extract_dir()
        print(f"[T4.0] output dir: {out_dir}")

    main_tbl, full_tbl = build_coverage_audit(mode=args.mode)
    main_path, full_path = write_outputs(main_tbl, full_tbl, output_dir=args.output_dir)

    print(f"[T4.0] mode={args.mode}")
    print(f"[T4.0] wrote {main_path}")
    print(f"[T4.0] wrote {full_path}")
    print("\n=== Coverage audit (main) ===")
    with_pct = main_tbl[["field", "green_n_nonnull", "green_pct", "other_n_nonnull", "other_pct", "ratio"]]
    print(with_pct.to_string(index=False))
    print("\n=== Acceptance report (spec P4 anchors) ===")
    for line in acceptance_report(full_tbl):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
