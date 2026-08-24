"""Step 3 CLI: build the firm-characteristic outputs (T4.1-T4.5, F4.1).

Examples
--------
    python -m empirical_analysis.step3_firm_characteristics.run --verbose
    python -m empirical_analysis.step3_firm_characteristics.run \
        --firm-table data/outputs/company_analysis.parquet \
        --clean-dir data/outputs/clean_tables \
        --output-dir data/outputs/chapter4
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from . import sources
from .build import acceptance_report, build_all, write_outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Step 3: firm characteristics (T4.1-T4.5, F4.1).")
    p.add_argument("--firm-table", type=Path, default=None,
                   help="Path to company_analysis.parquet, or the Step 2 output "
                        "directory that contains it.")
    p.add_argument("--clean-dir", type=Path, default=None,
                   help="Directory with Step 1 clean parquet tables.")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Directory to write CSV outputs.")
    p.add_argument("--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config.VERBOSE = args.verbose

    firm_table = sources.resolve_firm_table(args.firm_table or config.FIRM_TABLE)
    clean_dir = args.clean_dir or config.CLEAN_DIR
    output_dir = args.output_dir or config.OUTPUT_DIR

    print("[step3] firm table :", firm_table)
    print("[step3] clean dir  :", clean_dir)
    print("[step3] output dir :", output_dir)

    firm = sources.load_firm_table(firm_table)
    industries = sources.load_clean_table("industries_clean", clean_dir)
    verticals = sources.load_clean_table("verticals_clean", clean_dir)
    deals = sources.load_clean_table("deals_clean", clean_dir)

    result = build_all(firm, industries, verticals, deals=deals)
    write_outputs(result, output_dir)

    print("\n[step3] acceptance report")
    for line in acceptance_report(result):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
