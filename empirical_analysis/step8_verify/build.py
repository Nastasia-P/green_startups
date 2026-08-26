"""Step 8 build logic: re-run Steps 3-7 in-memory and reconcile.

Verification adds no new analytical numbers. It re-runs each reporting step's
`build_all` on the loaded Step 1/2 inputs to get a canonical set of tables, runs the
structural checks in `checks.py` over them, optionally compares them to the on-disk
CSVs (the stale-file guard), and records one row per check in a reconciliation table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import checks
from . import config
from ..step3_firm_characteristics import build as s3
from ..step4_geography import build as s4
from ..step5_funding import build as s5
from ..step6_investors import build as s6
from ..step7_geo_finance import build as s7
from ..step7_geo_finance import by_country as s7bc


@dataclass
class Step8Result:
    reconciliation: pd.DataFrame = field(default_factory=pd.DataFrame)
    summary: dict[str, int] = field(default_factory=dict)


def rerun_tables(
    firm: pd.DataFrame,
    deals: pd.DataFrame,
    company_investors: pd.DataFrame,
    investors: pd.DataFrame,
    deal_investors: pd.DataFrame,
    industries: pd.DataFrame,
    verticals: pd.DataFrame,
    population: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Re-run Steps 3-7 and merge every produced table into one name -> frame dict."""
    tables: dict[str, pd.DataFrame] = {}
    tables.update(s3.build_all(firm, industries, verticals, deals).tables)
    tables.update(s4.build_all(firm, population).tables)
    tables.update(s5.build_all(firm, deals).tables)
    tables.update(s6.build_all(firm, deals, company_investors, investors,
                               deal_investors).tables)
    tables.update(s7.build_all(firm, deals, company_investors, investors).tables)
    tables.update(s7bc.build_by_country(firm, deals, company_investors, investors,
                                        deal_investors))
    return tables


def build_all(
    firm: pd.DataFrame,
    deals: pd.DataFrame | None = None,
    company_investors: pd.DataFrame | None = None,
    investors: pd.DataFrame | None = None,
    deal_investors: pd.DataFrame | None = None,
    industries: pd.DataFrame | None = None,
    verticals: pd.DataFrame | None = None,
    population: pd.DataFrame | None = None,
    output_dir: Path | None = None,
    read_csv=None,
) -> Step8Result:
    deals = deals if deals is not None else pd.DataFrame()
    company_investors = company_investors if company_investors is not None else pd.DataFrame()
    investors = investors if investors is not None else pd.DataFrame()
    deal_investors = deal_investors if deal_investors is not None else pd.DataFrame()
    industries = industries if industries is not None else pd.DataFrame()
    verticals = verticals if verticals is not None else pd.DataFrame()
    population = population if population is not None else pd.DataFrame()

    tables = rerun_tables(firm, deals, company_investors, investors, deal_investors,
                          industries, verticals, population)

    # Wire the stale-file reader: an explicit read_csv wins; otherwise use output_dir.
    if read_csv is None and output_dir is not None:
        from . import sources

        def read_csv(name: str):  # noqa: E306
            return sources.read_output_csv(name, output_dir)

    rows = checks.run_all_checks(tables, firm, deals, company_investors, read_csv)
    recon = pd.DataFrame(rows, columns=[
        "check_id", "category", "description", "expected", "observed",
        "status", "detail"])

    summary = {
        "PASS": int((recon["status"] == "PASS").sum()),
        "WARN": int((recon["status"] == "WARN").sum()),
        "FAIL": int((recon["status"] == "FAIL").sum()),
        "total": len(recon),
    }
    return Step8Result(reconciliation=recon, summary=summary)


def write_outputs(result: Step8Result, output_dir: Path | None = None) -> Path:
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "step8_reconciliation.csv"
    result.reconciliation.to_csv(path, index=False)
    print(f"[step8] wrote {path}  ({len(result.reconciliation)} rows)")
    return out


def acceptance_report(result: Step8Result) -> list[str]:
    lines: list[str] = []
    s = result.summary
    lines.append(f"checks: {s['total']} total; PASS={s['PASS']} WARN={s['WARN']} "
                 f"FAIL={s['FAIL']}")
    recon = result.reconciliation
    for status in ("FAIL", "WARN"):
        sub = recon[recon["status"] == status]
        for _, r in sub.iterrows():
            lines.append(f"  {status} {r['check_id']}: expected={r['expected']} "
                         f"observed={r['observed']}"
                         + (f" ({r['detail']})" if r["detail"] else ""))
    return lines
