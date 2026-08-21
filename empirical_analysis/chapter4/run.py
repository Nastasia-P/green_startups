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
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from .coverage_audit import acceptance_report, build_coverage_audit, write_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T4.0 field completeness by group")
    parser.add_argument("--mode", choices=["fixture", "full"], default="fixture")
    parser.add_argument("--extract-dir", type=Path, default=None,
                        help="Directory of the 43 raw PitchBook tables (mode=full)")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.extract_dir is not None:
        config.FULL_EXTRACT_DIR = args.extract_dir

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
