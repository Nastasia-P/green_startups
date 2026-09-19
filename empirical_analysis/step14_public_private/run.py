"""Step 14 CLI: build the public/private investor participation outputs.

Examples
--------
    python -m empirical_analysis.step14_public_private.run --verbose
    python -m empirical_analysis.step14_public_private.run \
        --firm-panel data/outputs/chapter4/first5_analysis.parquet \
        --firm-table data/outputs/company_analysis.parquet \
        --clean-dir data/outputs/clean_tables \
        --output-dir data/outputs/chapter4 \
        --industry group

Requires `first5_analysis.parquet` (Step 5b) and the Step 1 clean tables.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from . import sources
from .build import HAVE_STATSMODELS, acceptance_report, build_all, write_outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Step 14: public/private investor participation (common horizon)."
    )
    p.add_argument("--firm-panel", type=Path, default=None,
                   help="Path to first5_analysis.parquet (Step 5b), or its directory.")
    p.add_argument("--firm-table", type=Path, default=None,
                   help="Path to company_analysis.parquet (needed for the window).")
    p.add_argument("--clean-dir", type=Path, default=None,
                   help="Directory with Step 1 clean parquet tables "
                        "(deals_clean, deal_investors_clean, investors_clean).")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Directory to write CSV/Parquet outputs.")
    p.add_argument("--industry", choices=["group", "code"], default="group",
                   help="Firm-level industry FE column: primary_industry_group "
                        "(default) or primary_industry_code.")
    p.add_argument("--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config.VERBOSE = args.verbose

    if not HAVE_STATSMODELS:
        print("[step14] ERROR: statsmodels is not installed.")
        print("[step14] install it with: python -m pip install --user statsmodels")
        return 1

    industry_col = (
        config.INDUSTRY_COL_GROUP if args.industry == "group"
        else config.INDUSTRY_COL_CODE
    )

    firm_panel_path = sources.resolve_firm_panel(args.firm_panel or config.FIRM_PANEL)
    firm_table_path = sources.resolve_firm_table(args.firm_table or config.FIRM_TABLE)
    clean_dir = args.clean_dir or config.CLEAN_DIR
    output_dir = args.output_dir or config.OUTPUT_DIR

    print("[step14] firm panel :", firm_panel_path)
    print("[step14] firm table :", firm_table_path)
    print("[step14] clean dir  :", clean_dir)
    print("[step14] output dir :", output_dir)
    print("[step14] industry FE:", industry_col)

    firm_panel_5b = sources.load_firm_panel(firm_panel_path)
    firm = sources.load_firm_table(firm_table_path)
    deals = sources.load_deals_clean(clean_dir)
    deal_investors = sources.load_deal_investors(clean_dir)
    investors = sources.load_investors(clean_dir)

    if industry_col not in firm_panel_5b.columns:
        print(f"[step14] ERROR: {industry_col!r} not in {firm_panel_path}. "
              "Re-run step5b_fixed_horizon, or pass --industry group.")
        return 1

    result = build_all(
        firm_panel_5b, firm, deals, deal_investors, investors,
        industry_col=industry_col,
    )
    write_outputs(result, output_dir)

    diag = result.diagnostics
    print("\n[step14] sample summary (common horizon)")
    print(f"  eligible firms          : {diag.get('n_eligible')} "
          f"(green={diag.get('n_eligible_green')}, other={diag.get('n_eligible_other')})")
    print(f"  invested (investor rec) : {diag.get('n_invested')} "
          f"(green={diag.get('n_invested_green')}, other={diag.get('n_invested_other')})")
    print(f"  both public+private     : {diag.get('n_both_public_private')}")

    print("\n[step14] investor classification")
    mapping = result.tables.get(config.OUT_MAPPING)
    if mapping is not None and len(mapping):
        for _, r in mapping.iterrows():
            print(f"  {r['investor_type_grp']:<24} -> {r['analytical_group']:<9} "
                  f"n_investors={r['n_investors']:>6}  n_firms={r['n_firms']:>6}")

    print("\n[step14] green coefficient path (1) -> (5)")
    reg = result.tables.get(config.OUT_REGRESSION)
    if reg is not None and len(reg):
        for outcome, grp in reg.groupby("outcome"):
            path = ", ".join(
                f"{config.SPEC_COLUMN_LABEL[s]}="
                f"{grp[grp['spec'] == s]['coef'].iloc[0]:+.4f}"
                f"{grp[grp['spec'] == s]['stars'].iloc[0]}"
                for s, _ in config.SPECS if (grp["spec"] == s).any()
            )
            print(f"  {outcome:<28} {path}")

    print("\n[step14] acceptance report")
    for line in acceptance_report(result):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
