"""Step 6 CLI: build the investor and grant outputs (T4.18-T4.25, F4.5).

Examples
--------
    python -m empirical_analysis.step6_investors.run --verbose
    python -m empirical_analysis.step6_investors.run \
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
    p = argparse.ArgumentParser(description="Step 6: investors and grants (T4.18-T4.25, F4.5).")
    p.add_argument("--firm-table", type=Path, default=None,
                   help="Path to company_analysis.parquet, or the Step 2 output "
                        "directory that contains it.")
    p.add_argument("--clean-dir", type=Path, default=None,
                   help="Directory with Step 1 clean parquet tables (deals_clean, "
                        "company_investors_clean, investors_clean, deal_investors_clean).")
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

    print("[step6] firm table :", firm_table)
    print("[step6] clean dir  :", clean_dir)
    print("[step6] output dir :", output_dir)

    firm = sources.load_firm_table(firm_table)
    deals = sources.load_deals_clean(clean_dir)
    company_investors = sources.load_company_investors(clean_dir)
    investors = sources.load_investors(clean_dir)
    deal_investors = sources.load_deal_investors(clean_dir)

    result = build_all(firm, deals, company_investors, investors, deal_investors)
    write_outputs(result, output_dir)

    print("\n[step6] acceptance report")
    for line in acceptance_report(firm, result):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
