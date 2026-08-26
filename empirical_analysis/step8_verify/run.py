"""Step 8 CLI: verification (cross-table reconciliation).

Re-runs Steps 3-7 in-memory, reconciles counts and shares, compares to the on-disk
outputs, and writes step8_reconciliation.csv.

Examples
--------
    python -m empirical_analysis.step8_verify.run --verbose
    python -m empirical_analysis.step8_verify.run \
        --firm-table data/outputs/company_analysis.parquet \
        --clean-dir data/outputs/clean_tables \
        --output-dir data/outputs/chapter4
    python -m empirical_analysis.step8_verify.run --strict   # non-zero exit on FAIL
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from . import sources
from .build import acceptance_report, build_all, write_outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Step 8: verification (reconciliation).")
    p.add_argument("--firm-table", type=Path, default=None,
                   help="Path to company_analysis.parquet, or the Step 2 output "
                        "directory that contains it.")
    p.add_argument("--clean-dir", type=Path, default=None,
                   help="Directory with the Step 1 clean parquet tables.")
    p.add_argument("--population", type=Path, default=None,
                   help="Eurostat population CSV (Step 4 T4.7 re-run input).")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Directory to write the reconciliation CSV and to compare "
                        "on-disk outputs against.")
    p.add_argument("--strict", action="store_true",
                   help="Return a non-zero exit code if any check FAILs.")
    p.add_argument("--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config.VERBOSE = args.verbose

    firm_table = sources.resolve_firm_table(args.firm_table or config.FIRM_TABLE)
    clean_dir = args.clean_dir or config.CLEAN_DIR
    output_dir = args.output_dir or config.OUTPUT_DIR

    print("[step8] firm table :", firm_table)
    print("[step8] clean dir  :", clean_dir)
    print("[step8] output dir :", output_dir)

    firm = sources.load_firm_table(firm_table)
    deals = sources.load_deals_clean(clean_dir)
    company_investors = sources.load_company_investors(clean_dir)
    investors = sources.load_investors(clean_dir)
    deal_investors = sources.load_deal_investors(clean_dir)
    industries = sources.load_industries(clean_dir)
    verticals = sources.load_verticals(clean_dir)
    population = sources.load_population(args.population or config.POPULATION_FILE)

    result = build_all(
        firm, deals, company_investors, investors, deal_investors,
        industries, verticals, population, output_dir=output_dir)
    write_outputs(result, output_dir)

    print("\n[step8] acceptance report")
    for line in acceptance_report(result):
        print("  " + line)

    if args.strict and result.summary["FAIL"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
