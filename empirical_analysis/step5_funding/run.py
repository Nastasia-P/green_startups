"""Step 5 CLI: build the funding outputs (T4.9-T4.17 incl. T4.12, F4.4).

Examples
--------
    python -m empirical_analysis.step5_funding.run --verbose
    python -m empirical_analysis.step5_funding.run \
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
    p = argparse.ArgumentParser(description="Step 5: funding (T4.9-T4.17, F4.4).")
    p.add_argument("--firm-table", type=Path, default=None,
                   help="Path to company_analysis.parquet, or the Step 2 output "
                        "directory that contains it.")
    p.add_argument("--clean-dir", type=Path, default=None,
                   help="Directory with Step 1 clean parquet tables (deals_clean).")
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

    print("[step5] firm table :", firm_table)
    print("[step5] clean dir  :", clean_dir)
    print("[step5] output dir :", output_dir)

    firm = sources.load_firm_table(firm_table)
    deals = sources.load_deals_clean(clean_dir)

    result = build_all(firm, deals)
    write_outputs(result, output_dir)

    print("\n[step5] acceptance report")
    for line in acceptance_report(firm, result):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
