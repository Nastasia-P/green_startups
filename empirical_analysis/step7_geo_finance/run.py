"""Step 7 CLI: geography x finance (T4.26, T4.28, T4.29, F-data) plus the collapsed
by-country comparison of every Step 5/6 table.

Examples
--------
    python -m empirical_analysis.step7_geo_finance.run --verbose
    python -m empirical_analysis.step7_geo_finance.run \
        --firm-table data/outputs/company_analysis.parquet \
        --clean-dir data/outputs/clean_tables \
        --output-dir data/outputs/chapter4
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import config
from . import sources
from .build import Step7Result, acceptance_report, build_all, write_outputs
from .by_country import build_by_country


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Step 7: geography x finance (T4.26, T4.28, T4.29) + by-country.")
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


def build_everything(
    firm: pd.DataFrame,
    deals: pd.DataFrame,
    company_investors: pd.DataFrame,
    investors: pd.DataFrame,
    deal_investors: pd.DataFrame,
) -> Step7Result:
    """Block A (build_all) plus block B (build_by_country), merged into one result."""
    result = build_all(firm, deals, company_investors, investors)
    by_country = build_by_country(
        firm, deals, company_investors, investors, deal_investors)
    for name, df in by_country.items():
        result.tables[name] = df
    result.caption["_by_country"] = (
        "Collapsed by-country comparison of the Step 5/6 tables: one row per country, "
        "headline statistic green vs other, the secondary dimension (cohort/stage/"
        "measure) collapsed. Values equal the Step 5/6 builder run on that country's "
        "slice. No country floor; low_n_flag marks fewer than "
        f"{config.LOW_N_FLAG} green (firms/relations/deals per the table's grain)."
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config.VERBOSE = args.verbose

    firm_table = sources.resolve_firm_table(args.firm_table or config.FIRM_TABLE)
    clean_dir = args.clean_dir or config.CLEAN_DIR
    output_dir = args.output_dir or config.OUTPUT_DIR

    print("[step7] firm table :", firm_table)
    print("[step7] clean dir  :", clean_dir)
    print("[step7] output dir :", output_dir)

    firm = sources.load_firm_table(firm_table)
    deals = sources.load_deals_clean(clean_dir)
    company_investors = sources.load_company_investors(clean_dir)
    investors = sources.load_investors(clean_dir)
    deal_investors = sources.load_deal_investors(clean_dir)

    result = build_everything(
        firm, deals, company_investors, investors, deal_investors)
    write_outputs(result, output_dir)

    print("\n[step7] acceptance report")
    for line in acceptance_report(firm, result):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
