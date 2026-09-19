"""Step 5b CLI: build the fixed five-year horizon outputs.

Examples
--------
    python -m empirical_analysis.step5b_fixed_horizon.run --verbose
    python -m empirical_analysis.step5b_fixed_horizon.run \
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
    p = argparse.ArgumentParser(
        description="Step 5b: fixed five-year financing horizon (T_first5_*)."
    )
    p.add_argument("--firm-table", type=Path, default=None,
                   help="Path to company_analysis.parquet, or the Step 2 output "
                        "directory that contains it.")
    p.add_argument("--clean-dir", type=Path, default=None,
                   help="Directory with Step 1 clean parquet tables "
                        "(deals_clean, deal_investors_clean, investors_clean).")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Directory to write CSV/PNG outputs.")
    p.add_argument("--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config.VERBOSE = args.verbose

    firm_table = sources.resolve_firm_table(args.firm_table or config.FIRM_TABLE)
    clean_dir = args.clean_dir or config.CLEAN_DIR
    output_dir = args.output_dir or config.OUTPUT_DIR

    print("[step5b] firm table :", firm_table)
    print("[step5b] clean dir  :", clean_dir)
    print("[step5b] output dir :", output_dir)

    firm = sources.load_firm_table(firm_table)
    deals = sources.load_deals_clean(clean_dir)
    deal_investors = sources.load_deal_investors(clean_dir)
    investors = sources.load_investors(clean_dir)

    result = build_all(firm, deals, deal_investors, investors)
    write_outputs(result, output_dir)

    diag = result.diagnostics
    print("\n[step5b] eligibility summary")
    print(f"  firms total          : {int(diag.get('n_firms_total', 0))}")
    print(f"  eligible (2016-2020) : {int(diag.get('n_eligible', 0))}")
    print(f"  in-window deals      : {int(diag.get('n_in_window_deals', 0))}")
    print(f"  impossible deals     : {int(diag.get('n_impossible_deals', 0))}")

    print("\n[step5b] canonical five-year dataset")
    print(f"  {config.FIRM_PANEL}.parquet rows : {len(result.firm_panel)}")
    if len(result.firm_audit):
        n_fail = int((~result.firm_audit["pass"]).sum())
        print(f"  {config.FIRM_AUDIT} checks     : "
              f"{len(result.firm_audit) - n_fail}/{len(result.firm_audit)} PASS")

    print("\n[step5b] acceptance report")
    for line in acceptance_report(result):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
