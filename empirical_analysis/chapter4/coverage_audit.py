"""T4.0 - Field completeness by group (coverage audit).

Builds the coverage audit defined in
`empirical_analysis/specs/T4_0/design.md`: for each audited field, the count and
percentage of non-null values among Green start-ups vs Other European start-ups,
plus the green/other ratio.

Company-level rows come from the merged population spine; deal- and investor-side
rows come from the relational source (fixture in smoke mode, full extract on real
data). Percentages use group population sizes as denominators, never non-null
counts (spec §3.6). Missing funding is never treated as zero (rule N1/N2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
from .data_sources import (
    RelationalSource,
    _log,
    load_company_frame,
    load_population_key,
    make_relational_source,
    nonnull_mask,
)

SCHEMA = [
    "field",
    "variable_id",
    "source_table",
    "source_field",
    "green_n_nonnull",
    "green_pct",
    "other_n_nonnull",
    "other_pct",
    "ratio",
    "notes",
]


@dataclass
class GroupIndex:
    """CompanyID sets and sizes for each group, from the population key."""

    green_ids: set[str]
    other_ids: set[str]
    n_green: int = field(init=False)
    n_other: int = field(init=False)

    def __post_init__(self) -> None:
        self.n_green = len(self.green_ids)
        self.n_other = len(self.other_ids)


def _row_from_company_field(
    frame: pd.DataFrame,
    label: str,
    variable_id: str,
    source_table: str,
    source_field: str,
    column: str,
    notes: str = "",
) -> dict:
    """Coverage row for a company-level scalar column (denominator = group size)."""
    present = nonnull_mask(frame[column]) if column in frame.columns else pd.Series(
        False, index=frame.index
    )
    is_green = frame["green"] == 1
    green_n = int((present & is_green).sum())
    other_n = int((present & ~is_green).sum())
    if column not in frame.columns:
        notes = (notes + " column absent in source").strip()
    return _assemble_row(label, variable_id, source_table, source_field, green_n, other_n, notes)


def _row_from_firm_id_set(
    label: str,
    variable_id: str,
    source_table: str,
    source_field: str,
    present_ids: set[str],
    notes: str = "",
) -> dict:
    """Coverage row where presence = firm appears in a set of qualifying CompanyIDs."""
    green_n = len(present_ids & _GROUPS.green_ids)
    other_n = len(present_ids & _GROUPS.other_ids)
    return _assemble_row(label, variable_id, source_table, source_field, green_n, other_n, notes)


def _assemble_row(
    label: str,
    variable_id: str,
    source_table: str,
    source_field: str,
    green_n: int,
    other_n: int,
    notes: str,
) -> dict:
    green_pct = 100.0 * green_n / _GROUPS.n_green if _GROUPS.n_green else float("nan")
    other_pct = 100.0 * other_n / _GROUPS.n_other if _GROUPS.n_other else float("nan")
    ratio = green_pct / other_pct if other_pct else float("nan")  # D-T4.0-7 guard
    if not other_pct:
        notes = (notes + " ratio undefined (other_pct=0)").strip()
    # Per-variable source_table override (config.SOURCE_TABLE_BY_FIELD).
    source_table = config.SOURCE_TABLE_BY_FIELD.get(label, source_table)
    return {
        "field": label,
        "variable_id": variable_id,
        "source_table": source_table,
        "source_field": source_field,
        "green_n_nonnull": green_n,
        "green_pct": round(green_pct, 4),
        "other_n_nonnull": other_n,
        "other_pct": round(other_pct, 4),
        "ratio": round(ratio, 4) if ratio == ratio else float("nan"),
        "notes": notes,
    }


# Module-level group index, set by build_coverage_audit before row helpers run.
_GROUPS: GroupIndex | None = None  # type: ignore[assignment]


# --------------------------------------------------------------------------
# Deal / investor firm-id sets from the relational source
# --------------------------------------------------------------------------
def _parse_deal_dates(raw: pd.Series) -> pd.Series:
    """Parse deal dates robustly.

    Try the configured format first; for values it fails to parse, fall back to
    pandas' format inference. This keeps F3 from silently dropping every row when
    the real Deal.csv uses a different date layout than config.DEAL_DATE_FORMAT.
    """
    s = raw.astype("string")
    parsed = pd.to_datetime(s, format=config.DEAL_DATE_FORMAT, errors="coerce")
    unparsed = parsed.isna() & nonnull_mask(s)
    if unparsed.any():
        fallback = pd.to_datetime(s[unparsed], errors="coerce")
        parsed.loc[unparsed] = fallback
    return parsed


def _build_deal_sets(rel: RelationalSource) -> dict[str, set[str]]:
    """Firm-id sets from Deal after filters F2-F4 (spec Part III)."""
    deal = rel.table("Deal")
    empty: set[str] = set()
    result = {"financed": empty, "deal_size": empty, "deal_size_actual": empty, "first_date": empty}
    if deal.empty or "CompanyID" not in deal.columns:
        return result

    d = deal.copy()
    _log(f"[T4.0] deal filter: start rows={len(d)}")
    if "DealStatus" in d.columns:  # F2
        d = d[d["DealStatus"].astype("string").str.strip() == config.DEAL_STATUS_COMPLETED]
        _log(f"[T4.0] deal filter: after F2 (DealStatus=={config.DEAL_STATUS_COMPLETED}) rows={len(d)}")
    if "DealDate" in d.columns:  # F3
        d["_date"] = _parse_deal_dates(d["DealDate"])
        d = d[d["_date"].notna() & (d["_date"] <= pd.Timestamp(config.EXTRACT_DATE))]
        _log(f"[T4.0] deal filter: after F3 (valid DealDate<={config.EXTRACT_DATE}) rows={len(d)}")
    if "DealType" in d.columns:  # F4
        d = d[~d["DealType"].astype("string").str.strip().isin(config.DEAL_TYPE_EXCLUSIONS)]
        _log(f"[T4.0] deal filter: after F4 (non-excluded DealType) rows={len(d)}")

    if d.empty:
        return result
    cid = d["CompanyID"].astype("string")
    result["financed"] = set(cid.dropna())
    result["first_date"] = set(cid[nonnull_mask(d["DealDate"])].dropna()) if "DealDate" in d.columns else empty
    if "DealSize" in d.columns:
        result["deal_size"] = set(cid[nonnull_mask(d["DealSize"])].dropna())
    if "DealSizeStatus" in d.columns:
        actual = d["DealSizeStatus"].astype("string").str.strip() == "Actual"
        result["deal_size_actual"] = set(cid[actual].dropna())
    return result


def _build_investor_sets(rel: RelationalSource) -> tuple[dict[str, set[str]], str]:
    """Firm-id sets for investor rows, plus an unclassified-share note."""
    empty: set[str] = set()
    result = {"relation": empty, "type_matched": empty, "country_matched": empty}
    note = ""

    cir = rel.table("CompanyInvestorRelation")
    if cir.empty or "CompanyID" not in cir.columns:
        return result, note
    cir = cir.copy()
    cir["CompanyID"] = cir["CompanyID"].astype("string")
    result["relation"] = set(cir["CompanyID"].dropna())

    investor = rel.table("Investor")
    if investor.empty or "InvestorID" not in investor.columns or "InvestorID" not in cir.columns:
        return result, note

    inv = investor.copy()
    inv["InvestorID"] = inv["InvestorID"].astype("string")
    if "PrimaryInvestorType" in inv.columns:
        inv["_grp"] = (
            inv["PrimaryInvestorType"].astype("string").str.strip().map(config.INVESTOR_TYPE_GRP)
        )
        inv["_grp"] = inv["_grp"].fillna("Other/Unclassified")
    country_col = next((c for c in config.INVESTOR_COUNTRY_CANDIDATES if c in inv.columns), None)

    merged = cir.merge(
        inv[["InvestorID"] + [c for c in ("_grp", country_col) if c]],
        on="InvestorID",
        how="left",
    )
    if "_grp" in merged.columns:
        typed = merged[merged["_grp"].notna()]
        result["type_matched"] = set(typed["CompanyID"].dropna())
        n_rel = len(merged)
        n_unclassified = int((merged["_grp"] == "Other/Unclassified").sum())
        if n_rel:
            note = f"unclassified investor share {100.0 * n_unclassified / n_rel:.1f}%"
    if country_col:
        has_country = nonnull_mask(merged[country_col])
        result["country_matched"] = set(merged.loc[has_country, "CompanyID"].dropna())
    return result, note


def _firm_ids_with_relation(rel: RelationalSource, table: str) -> set[str]:
    """CompanyIDs appearing at least once in a company-keyed relational table."""
    df = rel.table(table)
    if df.empty or "CompanyID" not in df.columns:
        return set()
    return set(df["CompanyID"].astype("string").dropna())


# --------------------------------------------------------------------------
# Audit assembly
# --------------------------------------------------------------------------
def build_coverage_audit(mode: str = "fixture") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the T4.0 audit. Returns (main 17-row table, full table with anchors)."""
    global _GROUPS

    population_key = load_population_key()
    company = load_company_frame(population_key)

    green_ids = set(population_key.loc[population_key["green"] == 1, "company_id"].dropna())
    other_ids = set(population_key.loc[population_key["green"] == 0, "company_id"].dropna())
    _GROUPS = GroupIndex(green_ids=green_ids, other_ids=other_ids)

    rel = make_relational_source(mode, population_ids=green_ids | other_ids)
    deal_sets = _build_deal_sets(rel)
    investor_sets, unclassified_note = _build_investor_sets(rel)
    emp_hist_ids = _firm_ids_with_relation(rel, "CompanyEmployeeHistoryRelation")

    fixture_note = "fixture: relational overlap with population is near-zero" if mode == "fixture" else ""

    # 17 Output_Register rows (design §3.4)
    rows = [
        _row_from_company_field(company, "year_founded", "V1.5", "Company", "YearFounded", "YearFounded"),
        _row_from_company_field(company, "hq_country", "V1.8", "Company", "HQCountry", "HQCountry"),
        _row_from_company_field(company, "hq_city", "V1.9", "Company", "HQCity", "HQCity"),
        _row_from_company_field(company, "employees", "V1.10", "Company", "Employees", "Employees"),
        _row_from_firm_id_set("employee_history", "derived", "CompanyEmployeeHistoryRelation", ">=1 row", emp_hist_ids, fixture_note),
        _row_from_company_field(company, "business_status", "V1.12", "Company", "BusinessStatus", "BusinessStatus"),
        _row_from_company_field(company, "primary_sector", "V1.14", "Company", "PrimaryIndustrySector", "PrimaryIndustrySector"),
        _row_from_company_field(company, "total_raised", "V1.17", "Company", "TotalRaised", "TotalRaised", "amount field, not access"),
        _row_from_firm_id_set(">=1 deal record", "V1.20", "Deal", "financed (F2-F4)", deal_sets["financed"], (fixture_note + " ; not total_raised>0 (N2)").strip()),
        _row_from_firm_id_set("deal_size", "V2.6", "Deal", "DealSize", deal_sets["deal_size"], fixture_note),
        _row_from_firm_id_set("deal_size actual", "V2.7", "Deal", "DealSizeStatus=Actual", deal_sets["deal_size_actual"], fixture_note),
        _row_from_firm_id_set("first_deal_date", "V1.27", "Deal", "DealDate", deal_sets["first_date"], fixture_note),
        _row_from_firm_id_set("investor relation present", "derived", "CompanyInvestorRelation", ">=1 row", investor_sets["relation"], fixture_note),
        _row_from_firm_id_set("investor type matched", "V4.4", "Investor", "PrimaryInvestorType->grp", investor_sets["type_matched"], (fixture_note + " ; " + unclassified_note).strip(" ;")),
        _row_from_firm_id_set("investor country matched", "V4.5", "Investor", "Country", investor_sets["country_matched"], fixture_note),
        _row_from_company_field(company, "revenue", "-", "Company", "Revenue", "Revenue", "coverage check only (S5)"),
        _row_from_company_field(company, "EBITDA", "-", "Company", "EBITDA", "EBITDA", "coverage check only (S5)"),
    ]
    main = pd.DataFrame(rows, columns=SCHEMA)

    # §P4 validation anchors (design §3.5)
    anchor_rows = [
        _row_from_company_field(company, "FirstFinancingDealType", "-", "Company", "FirstFinancingDealType", "FirstFinancingDealType", "P4 anchor 97.0/42.6"),
        _row_from_company_field(company, "Verticals", "-", "Company", "Verticals", "Verticals", "P4 anchor 91.0/36.5"),
        _row_from_company_field(company, "FirstFinancingDate", "-", "Company", "FirstFinancingDate", "FirstFinancingDate", "P4 anchor 70.4/32.6"),
        _row_from_company_field(company, "ActiveInvestors", "-", "Company", "ActiveInvestors", "ActiveInvestors", "P4 anchor 89.6/39.0"),
    ]
    full = pd.concat([main, pd.DataFrame(anchor_rows, columns=SCHEMA)], ignore_index=True)
    return main, full


def write_outputs(main: pd.DataFrame, full: pd.DataFrame, output_dir: Path | None = None) -> tuple[Path, Path]:
    """Write the main and full audit tables to CSV, with N10 group labels in headers."""
    output_dir = Path(output_dir or config.OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    def relabel(df: pd.DataFrame) -> pd.DataFrame:
        return df.rename(
            columns={
                "green_n_nonnull": f"{config.GROUP_GREEN}: n non-null",
                "green_pct": f"{config.GROUP_GREEN}: %",
                "other_n_nonnull": f"{config.GROUP_OTHER}: n non-null",
                "other_pct": f"{config.GROUP_OTHER}: %",
            }
        )

    main_path = output_dir / "T4_00_field_completeness.csv"
    full_path = output_dir / "T4_00_field_completeness_full.csv"
    relabel(main).to_csv(main_path, index=False)
    relabel(full).to_csv(full_path, index=False)
    return main_path, full_path


def acceptance_report(full: pd.DataFrame) -> list[str]:
    """Compare computed coverage to spec §P4 anchors. Warns, never raises."""
    lines: list[str] = []
    lines.append(
        f"Population: green={_GROUPS.n_green} other={_GROUPS.n_other} "
        f"total={_GROUPS.n_green + _GROUPS.n_other} "
        f"(spec anchor total={config.SPEC_POP_TOTAL}, green={config.SPEC_GREEN_TOTAL})"
    )
    if _GROUPS.n_green != config.SPEC_GREEN_TOTAL:
        lines.append(
            f"  WARN: green count {_GROUPS.n_green} != spec anchor {config.SPEC_GREEN_TOTAL} "
            "(strong_terms ledger differs from the spec's Chapter 3 inputs)"
        )
    by_field = full.set_index("field")
    for fld, (exp_green, exp_other) in config.COVERAGE_ANCHORS.items():
        if fld not in by_field.index:
            continue
        g = by_field.loc[fld, "green_pct"]
        o = by_field.loc[fld, "other_pct"]
        dg, do = abs(g - exp_green), abs(o - exp_other)
        flag = "" if (dg <= config.ANCHOR_TOLERANCE_PP and do <= config.ANCHOR_TOLERANCE_PP) else "  WARN"
        lines.append(
            f"  {fld}: green {g:.1f}% (exp {exp_green}) other {o:.1f}% (exp {exp_other}){flag}"
        )
    return lines
