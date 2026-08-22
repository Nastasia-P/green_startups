"""Step 1 cleaning logic: build the clean per-grain tables.

Build order matters, because each table narrows the next:

    population_key
      -> deals_clean            (filters 1-4)  -> surviving DealIDs
      -> deal_investors_clean   (surviving DealIDs)
      -> company_investors_clean(population)
      -> investors_clean        (InvestorIDs referenced by the two above)
      -> industries / verticals / employee_history (population)

Every table keeps its own grain. Aggregation to firm level is Step 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
from .sources import RawSource, log, nonnull_mask, parse_deal_dates


@dataclass
class AuditRow:
    table: str
    rows_in: int
    rows_out: int
    distinct_companies: int | None
    match_rate: float | None
    note: str = ""


@dataclass
class Step1Result:
    """Everything Step 1 produces: the clean tables, the reference lists, the audit."""

    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    deal_types_seen: pd.DataFrame = field(default_factory=pd.DataFrame)
    investor_types_seen: pd.DataFrame = field(default_factory=pd.DataFrame)
    audit: list[AuditRow] = field(default_factory=list)
    deal_funnel: dict[str, int] = field(default_factory=dict)
    unclassified_investor_share: float = float("nan")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _as_string(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = df[c].astype("string")


def _as_numeric(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def _stage_group(deal_type: pd.Series) -> pd.Series:
    """Map DealType to its stage group; anything unlisted is marked Unmapped."""
    s = deal_type.astype("string").str.strip()
    grp = s.map(config.STAGE_GROUP_MAP).astype("string")
    # Crowdfunding variants are matched by substring so new PitchBook wordings
    # do not silently land in Unmapped.
    crowd = grp.isna() & s.str.contains("Crowdfunding", case=False, na=False)
    grp = grp.mask(crowd, "Crowdfunding")
    return grp.fillna(config.UNMAPPED_STAGE_GROUP)


def _match_rate(distinct: int, population_size: int) -> float | None:
    return (distinct / population_size) if population_size else None


# --------------------------------------------------------------------------
# Table builders
# --------------------------------------------------------------------------
def build_deals_clean(
    source: RawSource, population_ids: set[str]
) -> tuple[pd.DataFrame, set[str], pd.DataFrame, dict[str, int]]:
    """Deals for the population that are genuine, completed, correctly dated financings.

    Returns (deals_clean, surviving DealIDs, deal-type enumeration, filter funnel).
    """
    raw = source.table("Deal", keep_ids=population_ids)
    funnel = {"after_population": len(raw)}
    if raw.empty:
        return raw, set(), pd.DataFrame(), funnel

    d = raw.copy()
    _as_string(d, ["CompanyID", "DealID", "DealType", "DealType2", "DealClass",
                   "DealStatus", "DealSizeStatus", "VCRound"])

    # The enumeration is taken before the type filter so excluded types are visible.
    type_counts = (
        d["DealType"].astype("string").str.strip().value_counts(dropna=False)
        if "DealType" in d.columns
        else pd.Series(dtype="int64")
    )

    # Filter 2: completed deals only.
    if "DealStatus" in d.columns:
        d = d[d["DealStatus"].str.strip() == config.DEAL_STATUS_COMPLETED]
    funnel["after_completed"] = len(d)

    # Filter 3: a parseable date on or before the extract date.
    if "DealDate" in d.columns:
        d["deal_date"] = parse_deal_dates(d["DealDate"])
        d = d[d["deal_date"].notna() & (d["deal_date"] <= pd.Timestamp(config.EXTRACT_DATE))]
    funnel["after_valid_date"] = len(d)

    # Filter 4: drop deal types that are not new capital into the firm.
    if "DealType" in d.columns:
        d = d[~d["DealType"].str.strip().isin(config.DEAL_TYPE_EXCLUSIONS)]
    funnel["after_real_financing"] = len(d)

    if d.empty:
        return d, set(), _deal_type_enumeration(type_counts), funnel

    d = d.rename(columns={"CompanyID": "company_id", "DealID": "deal_id"})
    d["stage_group"] = _stage_group(d["DealType"]) if "DealType" in d.columns else pd.NA
    if "DealSizeStatus" in d.columns:
        d["size_is_actual"] = (d["DealSizeStatus"].str.strip() == "Actual").astype("int64")
    _as_numeric(d, ["DealSize", "PostValuation", "Investors", "NewInvestors", "DealNo"])
    d = d.rename(
        columns={
            "DealType": "deal_type",
            "DealType2": "deal_type_2",
            "DealClass": "deal_class",
            "DealSize": "deal_size",
            "DealNo": "deal_no",
            "VCRound": "vc_round",
            "PostValuation": "post_valuation",
            "Investors": "n_investors",
            "NewInvestors": "n_new_investors",
        }
    )
    # First deal per firm, by date.
    first_date = d.groupby("company_id")["deal_date"].transform("min")
    d["is_first_deal"] = (d["deal_date"] == first_date).astype("int64")

    keep = [
        "company_id", "deal_id", "deal_date", "deal_type", "deal_type_2", "deal_class",
        "stage_group", "deal_size", "size_is_actual", "deal_no", "vc_round",
        "post_valuation", "n_investors", "n_new_investors", "is_first_deal",
    ]
    d = d[[c for c in keep if c in d.columns]].reset_index(drop=True)
    surviving = set(d["deal_id"].dropna())
    return d, surviving, _deal_type_enumeration(type_counts, d), funnel


def _deal_type_enumeration(
    type_counts: pd.Series, deals_clean: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Every DealType seen, its count, the stage group it mapped to, and flags."""
    if type_counts.empty:
        return pd.DataFrame(
            columns=["deal_type", "n_rows", "stage_group", "is_mapped", "excluded_by_filter"]
        )
    rows = []
    for value, n in type_counts.items():
        value_s = "" if pd.isna(value) else str(value)
        excluded = value_s in config.DEAL_TYPE_EXCLUSIONS
        grp = _stage_group(pd.Series([value_s], dtype="string")).iloc[0]
        rows.append(
            {
                "deal_type": value_s,
                "n_rows": int(n),
                "stage_group": "EXCLUDED" if excluded else grp,
                "is_mapped": bool(excluded or grp != config.UNMAPPED_STAGE_GROUP),
                "excluded_by_filter": excluded,
            }
        )
    out = pd.DataFrame(rows).sort_values("n_rows", ascending=False).reset_index(drop=True)
    if deals_clean is not None and "stage_group" in deals_clean.columns:
        kept = deals_clean["deal_type"].value_counts()
        out["n_kept"] = out["deal_type"].map(kept).fillna(0).astype("int64")
    return out


def build_deal_investors_clean(source: RawSource, surviving_deal_ids: set[str]) -> pd.DataFrame:
    """Investor participation in the surviving deals, limited to financing roles."""
    raw = source.table("DealInvestorRelation", keep_ids=surviving_deal_ids)
    if raw.empty:
        return raw
    d = raw.copy()
    _as_string(d, ["DealID", "InvestorID", "InvestorName", "InvestorStatus", "IsLeadInvestor"])
    if "InvestorStatus" in d.columns:
        d = d[d["InvestorStatus"].str.strip().isin(config.DEAL_INVESTOR_STATUS_KEEP)]
    d = d.rename(
        columns={
            "DealID": "deal_id",
            "InvestorID": "investor_id",
            "InvestorName": "investor_name",
            "InvestorStatus": "investor_status",
            "IsLeadInvestor": "is_lead",
        }
    )
    return d.reset_index(drop=True)


def build_company_investors_clean(source: RawSource, population_ids: set[str]) -> pd.DataFrame:
    """Lifetime firm-investor relationships, excluding non-financing roles."""
    raw = source.table("CompanyInvestorRelation", keep_ids=population_ids)
    if raw.empty:
        return raw
    d = raw.copy()
    _as_string(d, ["CompanyID", "InvestorID", "InvestorName", "InvestorStatus", "Holding"])
    if "InvestorStatus" in d.columns:
        d = d[~d["InvestorStatus"].str.strip().isin(config.COMPANY_INVESTOR_STATUS_DROP)]
    d = d.rename(
        columns={
            "CompanyID": "company_id",
            "InvestorID": "investor_id",
            "InvestorName": "investor_name",
            "InvestorStatus": "investor_status",
            "Holding": "holding",
            "InvestorSince": "investor_since",
        }
    )
    return d.reset_index(drop=True)


def build_investors_clean(
    source: RawSource, referenced_investor_ids: set[str]
) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """The investors actually referenced, with their type group and country."""
    raw = source.table("Investor", keep_ids=referenced_investor_ids)
    if raw.empty:
        return raw, pd.DataFrame(columns=["primary_investor_type", "n_investors",
                                          "investor_type_grp", "is_mapped"]), float("nan")
    d = raw.copy()
    _as_string(d, ["InvestorID", "InvestorName", "PrimaryInvestorType", "OtherInvestorTypes"])

    type_counts = (
        d["PrimaryInvestorType"].str.strip().value_counts(dropna=False)
        if "PrimaryInvestorType" in d.columns
        else pd.Series(dtype="int64")
    )

    if "PrimaryInvestorType" in d.columns:
        grp = d["PrimaryInvestorType"].str.strip().map(config.INVESTOR_TYPE_GRP).astype("string")
        d["investor_type_grp"] = grp.fillna(config.UNCLASSIFIED_INVESTOR_GRP)
    else:
        d["investor_type_grp"] = config.UNCLASSIFIED_INVESTOR_GRP

    country_col = next(
        (c for c in config.INVESTOR_COUNTRY_CANDIDATES if c in d.columns), None
    )
    d["investor_country"] = d[country_col].astype("string") if country_col else pd.NA

    d = d.rename(
        columns={
            "InvestorID": "investor_id",
            "InvestorName": "investor_name",
            "PrimaryInvestorType": "primary_investor_type",
            "OtherInvestorTypes": "other_investor_types",
        }
    )
    keep = [
        "investor_id", "investor_name", "primary_investor_type", "other_investor_types",
        "investor_type_grp", "investor_country",
    ]
    d = d[[c for c in keep if c in d.columns]].reset_index(drop=True)

    unclassified = float(
        100.0 * (d["investor_type_grp"] == config.UNCLASSIFIED_INVESTOR_GRP).mean()
    ) if len(d) else float("nan")

    enum_rows = [
        {
            "primary_investor_type": "" if pd.isna(v) else str(v),
            "n_investors": int(n),
            "investor_type_grp": config.INVESTOR_TYPE_GRP.get(
                "" if pd.isna(v) else str(v), config.UNCLASSIFIED_INVESTOR_GRP
            ),
            "is_mapped": ("" if pd.isna(v) else str(v)) in config.INVESTOR_TYPE_GRP,
        }
        for v, n in type_counts.items()
    ]
    enumeration = (
        pd.DataFrame(enum_rows).sort_values("n_investors", ascending=False).reset_index(drop=True)
        if enum_rows
        else pd.DataFrame(columns=["primary_investor_type", "n_investors",
                                   "investor_type_grp", "is_mapped"])
    )
    return d, enumeration, unclassified


def build_relation_clean(
    source: RawSource, table: str, population_ids: set[str], rename: dict[str, str]
) -> pd.DataFrame:
    """A company-keyed relational table, filtered to the population and renamed."""
    raw = source.table(table, keep_ids=population_ids)
    if raw.empty:
        return raw
    d = raw.copy()
    _as_string(d, [c for c in d.columns])
    return d.rename(columns=rename).reset_index(drop=True)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def build_all(source: RawSource, population_key: pd.DataFrame) -> Step1Result:
    """Run every Step 1 build in dependency order and collect the audit."""
    result = Step1Result()
    population_ids = set(population_key["company_id"].dropna())
    pop_size = len(population_ids)
    result.tables["population_key"] = population_key

    deals, surviving_deal_ids, deal_types, funnel = build_deals_clean(source, population_ids)
    result.tables["deals_clean"] = deals
    result.deal_types_seen = deal_types
    result.deal_funnel = funnel
    log(f"[step1] deal funnel: {funnel}")

    deal_investors = build_deal_investors_clean(source, surviving_deal_ids)
    result.tables["deal_investors_clean"] = deal_investors

    company_investors = build_company_investors_clean(source, population_ids)
    result.tables["company_investors_clean"] = company_investors

    referenced = set()
    for frame in (deal_investors, company_investors):
        if not frame.empty and "investor_id" in frame.columns:
            referenced |= set(frame["investor_id"].dropna())
    investors, investor_types, unclassified = build_investors_clean(source, referenced)
    result.tables["investors_clean"] = investors
    result.investor_types_seen = investor_types
    result.unclassified_investor_share = unclassified

    result.tables["industries_clean"] = build_relation_clean(
        source, "CompanyIndustryRelation", population_ids,
        {"CompanyID": "company_id", "IsPrimary": "is_primary",
         "IndustrySector": "industry_sector", "IndustryGroup": "industry_group",
         "IndustryCode": "industry_code"},
    )
    result.tables["verticals_clean"] = build_relation_clean(
        source, "CompanyVerticalRelation", population_ids,
        {"CompanyID": "company_id", "Vertical": "vertical"},
    )
    result.tables["employee_history_clean"] = build_relation_clean(
        source, "CompanyEmployeeHistoryRelation", population_ids,
        {"CompanyID": "company_id", "EmployeeCount": "employee_count", "Date": "date"},
    )

    result.audit = _build_audit(source, result, pop_size)
    return result


_SOURCE_TABLE_FOR = {
    "deals_clean": "Deal",
    "deal_investors_clean": "DealInvestorRelation",
    "company_investors_clean": "CompanyInvestorRelation",
    "investors_clean": "Investor",
    "industries_clean": "CompanyIndustryRelation",
    "verticals_clean": "CompanyVerticalRelation",
    "employee_history_clean": "CompanyEmployeeHistoryRelation",
}


def _build_audit(source: RawSource, result: Step1Result, pop_size: int) -> list[AuditRow]:
    rows = [
        AuditRow(
            table="population_key",
            rows_in=pop_size,
            rows_out=len(result.tables["population_key"]),
            distinct_companies=pop_size,
            match_rate=1.0 if pop_size else None,
        )
    ]
    for name, src in _SOURCE_TABLE_FOR.items():
        df = result.tables.get(name, pd.DataFrame())
        distinct = (
            int(df["company_id"].nunique()) if "company_id" in df.columns and not df.empty else None
        )
        rate = _match_rate(distinct, pop_size) if distinct is not None else None
        note = ""
        if rate is not None and rate < config.MIN_MATCH_RATE:
            note = f"LOW MATCH: under {config.MIN_MATCH_RATE:.0%} of the population"
        if name == "investors_clean":
            note = (note + " keyed by investor, not company").strip()
        rows.append(
            AuditRow(
                table=name,
                rows_in=source.raw_row_count(src),
                rows_out=len(df),
                distinct_companies=distinct,
                match_rate=rate,
                note=note,
            )
        )
    return rows


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------
def write_outputs(result: Step1Result, output_dir: Path | None = None) -> Path:
    """Write every clean table as Parquet, plus the reference lists and audit as CSV."""
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    for name, df in result.tables.items():
        path = out / f"{name}.parquet"
        frame = df if not df.empty else pd.DataFrame(columns=df.columns)
        frame.to_parquet(path, engine="pyarrow", index=False)
        print(f"[step1] wrote {path}  ({len(frame):,} rows)")

    result.deal_types_seen.to_csv(out / "deal_types_seen.csv", index=False)
    result.investor_types_seen.to_csv(out / "investor_types_seen.csv", index=False)
    print(f"[step1] wrote {out / 'deal_types_seen.csv'}")
    print(f"[step1] wrote {out / 'investor_types_seen.csv'}")

    audit = pd.DataFrame([vars(r) for r in result.audit])
    if "match_rate" in audit.columns:
        audit["match_rate"] = audit["match_rate"].astype(float).round(4)
    audit.to_csv(out / "cleaning_audit.csv", index=False)
    print(f"[step1] wrote {out / 'cleaning_audit.csv'}")
    return out


def acceptance_report(result: Step1Result, company_merged: Path | None = None) -> list[str]:
    """Checks that say whether Step 1 succeeded. Warns, never raises."""
    lines: list[str] = []
    pop = result.tables["population_key"]
    n_total = len(pop)
    n_green = int((pop["green"] == 1).sum())
    lines.append(
        f"Population: total={n_total} green={n_green} "
        f"(expected total={config.SPEC_POP_TOTAL}, green={config.SPEC_GREEN_TOTAL})"
    )
    if n_total != config.SPEC_POP_TOTAL:
        lines.append(f"  WARN: population {n_total} != expected {config.SPEC_POP_TOTAL}")
    if n_green != config.SPEC_GREEN_TOTAL:
        lines.append(f"  WARN: green {n_green} != expected {config.SPEC_GREEN_TOTAL}")

    stages = pop["green_stage"].value_counts()
    got = {k: int(stages.get(k, 0)) for k in config.SPEC_GREEN_STAGES}
    lines.append(f"Green stages: {got} (expected {config.SPEC_GREEN_STAGES})")
    if got != config.SPEC_GREEN_STAGES:
        lines.append("  WARN: green stage counts differ from expected")

    if result.deal_funnel:
        lines.append(f"Deal filter funnel: {result.deal_funnel}")

    deals = result.tables.get("deals_clean", pd.DataFrame())
    n_financed = int(deals["company_id"].nunique()) if "company_id" in deals.columns else 0
    lines.append(f"Firms with >=1 qualifying deal: {n_financed}")
    expected = _first_financing_count(company_merged)
    if expected is not None:
        lines.append(
            f"  cross-check vs non-null FirstFinancingDealID in the company file: {expected}"
        )
        if expected and abs(n_financed - expected) / expected > 0.10:
            lines.append("  WARN: differs by more than 10% - a filter may be dropping too much")

    unmapped_deals = result.deal_types_seen
    if not unmapped_deals.empty and "is_mapped" in unmapped_deals.columns:
        missing = unmapped_deals.loc[~unmapped_deals["is_mapped"], "deal_type"].tolist()
        if missing:
            lines.append(f"  WARN: unmapped deal types need classifying: {missing}")

    unmapped_inv = result.investor_types_seen
    if not unmapped_inv.empty and "is_mapped" in unmapped_inv.columns:
        missing = unmapped_inv.loc[~unmapped_inv["is_mapped"], "primary_investor_type"].tolist()
        if missing:
            lines.append(f"  WARN: unmapped investor types need classifying: {missing}")
    if result.unclassified_investor_share == result.unclassified_investor_share:
        lines.append(f"Unclassified investor share: {result.unclassified_investor_share:.1f}%")
        if result.unclassified_investor_share > 10.0:
            lines.append("  WARN: above 10% - revisit the investor type mapping")

    for row in result.audit:
        if row.note.startswith("LOW MATCH"):
            lines.append(f"  WARN: {row.table} matched only {row.match_rate:.1%} of the population")
    return lines


def _first_financing_count(company_merged: Path | None) -> int | None:
    """Count firms with a non-null FirstFinancingDealID, for the deal cross-check."""
    path = Path(company_merged or config.COMPANY_MERGED)
    if not path.exists():
        return None
    try:
        header = pd.read_csv(path, nrows=0).columns
        if "FirstFinancingDealID" not in header:
            return None
        col = pd.read_csv(path, usecols=["FirstFinancingDealID"], dtype=str)
        return int(nonnull_mask(col["FirstFinancingDealID"]).sum())
    except (OSError, ValueError):
        return None
