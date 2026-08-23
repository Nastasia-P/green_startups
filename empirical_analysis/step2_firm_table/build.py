"""Step 2 build logic: collapse the clean tables to one row per firm.

The firm table is assembled in four blocks, each reduced to firm grain *before*
being joined onto the spine, so a deal with many investors can never multiply a
firm's row (spec Part II.A3):

    spine (1 per firm)
      + deal aggregates        (from deals_clean)
      + investor aggregates    (from company_investors_clean x investors_clean)
      + same-deal co-investment(from deal_investors_clean x investors_clean)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
from .sources import log, nonnull_mask


@dataclass
class Step2Result:
    company_analysis: pd.DataFrame = field(default_factory=pd.DataFrame)
    coverage: pd.DataFrame = field(default_factory=pd.DataFrame)
    audit: pd.DataFrame = field(default_factory=pd.DataFrame)
    n_negative_funding_lag: int = 0
    n_negative_vc_lag: int = 0


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _mask(condition: pd.Series) -> pd.Series:
    """A plain boolean mask; missing comparison results become False.

    Casting to nullable boolean first avoids the object-dtype downcast that
    `fillna` warns about on mixed True/False/NA inputs.
    """
    return condition.astype("boolean").fillna(False).astype(bool)


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _cohort(year: pd.Series) -> pd.Series:
    """Map a founding year to its cohort label; out-of-range/missing -> NA."""
    out = pd.Series(pd.NA, index=year.index, dtype="string")
    for lo, hi, label in config.COHORT_BINS:
        out = out.mask(_mask((year >= lo) & (year <= hi)), label)
    return out


def _employee_band(emp: pd.Series) -> pd.Series:
    """Map an employee count to its size band; <1 or missing -> NA."""
    out = pd.Series(pd.NA, index=emp.index, dtype="string")
    for lo, hi, label in config.EMPLOYEE_BANDS:
        cond = emp >= lo if hi is None else (emp >= lo) & (emp <= hi)
        out = out.mask(_mask(cond), label)
    return out


def _year(series: pd.Series) -> pd.Series:
    """Calendar year of a datetime series, as a nullable integer."""
    return pd.to_datetime(series, errors="coerce").dt.year.astype("Int64")


# --------------------------------------------------------------------------
# Deal aggregates
# --------------------------------------------------------------------------
def _deal_aggregates(deals: pd.DataFrame) -> pd.DataFrame:
    """One row per firm summarising its qualifying deals."""
    cols = [
        "company_id", "n_deals", "n_rounds_vc", "any_vc", "any_grant", "any_debt",
        "any_accelerator", "any_growth_pe", "any_crowdfunding",
        "first_deal_date", "first_deal_type", "first_deal_size",
        "last_deal_date", "last_deal_type", "last_deal_size",
        "median_deal_size", "total_deal_size_obs", "n_deals_with_size", "first_vc_date",
    ]
    if deals.empty or "company_id" not in deals.columns:
        return pd.DataFrame(columns=cols)

    d = deals.copy()
    d["deal_date"] = pd.to_datetime(d["deal_date"], errors="coerce")
    d["deal_size"] = _numeric(d.get("deal_size"))
    stage = d.get("stage_group", pd.Series(pd.NA, index=d.index)).astype("string")
    deal_class = d.get("deal_class", pd.Series(pd.NA, index=d.index)).astype("string")

    d["_is_vc"] = _mask(stage.isin(config.VC_STAGE_GROUPS))
    d["_is_grant"] = _mask(stage == "Grant")
    d["_is_debt"] = _mask((deal_class == "Debt") | (stage == "Debt"))
    d["_is_accel"] = _mask(stage == "Accelerator/Incubator")
    d["_is_growthpe"] = _mask(stage == "Growth/PE")
    d["_is_crowd"] = _mask(stage == "Crowdfunding")
    d["_has_size"] = d["deal_size"].notna()

    grp = d.groupby("company_id")
    agg = grp.agg(
        n_deals=("deal_id", "size"),
        n_rounds_vc=("_is_vc", "sum"),
        any_vc=("_is_vc", "max"),
        any_grant=("_is_grant", "max"),
        any_debt=("_is_debt", "max"),
        any_accelerator=("_is_accel", "max"),
        any_growth_pe=("_is_growthpe", "max"),
        any_crowdfunding=("_is_crowd", "max"),
        first_deal_date=("deal_date", "min"),
        last_deal_date=("deal_date", "max"),
        median_deal_size=("deal_size", "median"),
        total_deal_size_obs=("deal_size", "sum"),
        n_deals_with_size=("_has_size", "sum"),
    ).reset_index()

    # A total over zero observed sizes is unknown, not zero (missing != zero).
    agg.loc[agg["n_deals_with_size"] == 0, "total_deal_size_obs"] = pd.NA

    # First / last deal type and size are taken from the actual earliest/latest
    # row (not a non-null aggregate), so a null size at the first deal stays null.
    ds = d.sort_values(["company_id", "deal_date"], kind="stable")
    first_rows = ds.drop_duplicates("company_id", keep="first")[
        ["company_id", "deal_type", "deal_size"]
    ].rename(columns={"deal_type": "first_deal_type", "deal_size": "first_deal_size"})
    last_rows = ds.drop_duplicates("company_id", keep="last")[
        ["company_id", "deal_type", "deal_size"]
    ].rename(columns={"deal_type": "last_deal_type", "deal_size": "last_deal_size"})

    vc = d[d["_is_vc"]]
    first_vc = (
        vc.groupby("company_id")["deal_date"].min().reset_index(name="first_vc_date")
        if not vc.empty
        else pd.DataFrame(columns=["company_id", "first_vc_date"])
    )

    out = agg.merge(first_rows, on="company_id", how="left")
    out = out.merge(last_rows, on="company_id", how="left")
    out = out.merge(first_vc, on="company_id", how="left")
    return out[cols]


# --------------------------------------------------------------------------
# Investor aggregates
# --------------------------------------------------------------------------
def _investor_aggregates(
    company_investors: pd.DataFrame,
    investors: pd.DataFrame,
    hq_country_by_company: pd.Series,
) -> pd.DataFrame:
    """One row per firm summarising its lifetime investors and their origin."""
    cols = [
        "company_id", "n_investors_lifetime", "any_public_investor",
        "any_corporate_investor", "any_ivc_investor", "any_accelerator_investor",
        "any_lender_investor", "share_investors_domestic",
        "share_investors_eu_cross_border", "share_investors_non_european",
    ]
    if company_investors.empty or "company_id" not in company_investors.columns:
        return pd.DataFrame(columns=cols)

    ci = company_investors[["company_id", "investor_id"]].copy()
    ci["company_id"] = ci["company_id"].astype("string")
    ci["investor_id"] = ci["investor_id"].astype("string")

    if not investors.empty and "investor_id" in investors.columns:
        inv = investors[["investor_id"]].copy()
        inv["investor_id"] = investors["investor_id"].astype("string")
        inv["investor_type_grp"] = investors.get(
            "investor_type_grp", pd.Series(pd.NA, index=investors.index)
        ).astype("string")
        inv["investor_country"] = investors.get(
            "investor_country", pd.Series(pd.NA, index=investors.index)
        ).astype("string")
    else:
        inv = pd.DataFrame(columns=["investor_id", "investor_type_grp", "investor_country"])

    j = ci.merge(inv, on="investor_id", how="left")
    grp_col = j["investor_type_grp"]
    j["_is_public"] = _mask(grp_col.isin(config.PUBLIC_INVESTOR_GRPS))
    j["_is_corporate"] = _mask(grp_col == "Corporate")
    j["_is_ivc"] = _mask(grp_col == "Independent VC")
    j["_is_accel"] = _mask(grp_col == "Accelerator/Incubator")
    j["_is_lender"] = _mask(grp_col == "Lender/Debt")

    agg = j.groupby("company_id").agg(
        n_investors_lifetime=("investor_id", "nunique"),
        any_public_investor=("_is_public", "max"),
        any_corporate_investor=("_is_corporate", "max"),
        any_ivc_investor=("_is_ivc", "max"),
        any_accelerator_investor=("_is_accel", "max"),
        any_lender_investor=("_is_lender", "max"),
    ).reset_index()

    geo = _investor_geo_shares(j, hq_country_by_company)
    return agg.merge(geo, on="company_id", how="left")[cols]


def _investor_geo_shares(
    joined: pd.DataFrame, hq_country_by_company: pd.Series
) -> pd.DataFrame:
    """Domestic / EU cross-border / non-European shares over located investors."""
    cols = [
        "company_id", "share_investors_domestic",
        "share_investors_eu_cross_border", "share_investors_non_european",
    ]
    located = joined[nonnull_mask(joined["investor_country"])].copy()
    if located.empty:
        return pd.DataFrame(columns=cols)

    hq = hq_country_by_company.rename("hq_country")
    located = located.merge(hq, left_on="company_id", right_index=True, how="left")

    country = located["investor_country"].astype("string").str.strip()
    home = located["hq_country"].astype("string").str.strip()
    is_domestic = _mask(country == home)
    is_european = _mask(country.isin(config.EUROPEAN_COUNTRIES))
    located["_domestic"] = is_domestic
    located["_eu_cross"] = _mask(is_european & ~is_domestic)
    located["_non_eu"] = _mask(~is_european)

    shares = located.groupby("company_id").agg(
        share_investors_domestic=("_domestic", "mean"),
        share_investors_eu_cross_border=("_eu_cross", "mean"),
        share_investors_non_european=("_non_eu", "mean"),
    ).reset_index()
    return shares[cols]


def _same_deal_coinvestment(
    deal_investors: pd.DataFrame, investors: pd.DataFrame, deals: pd.DataFrame
) -> set[str]:
    """Company IDs with at least one deal carrying both a public and a private investor."""
    if (
        deal_investors.empty
        or investors.empty
        or deals.empty
        or "deal_id" not in deal_investors.columns
        or "deal_id" not in deals.columns
    ):
        return set()

    di = deal_investors[["deal_id", "investor_id"]].copy()
    di["deal_id"] = di["deal_id"].astype("string")
    di["investor_id"] = di["investor_id"].astype("string")

    inv = investors[["investor_id"]].copy()
    inv["investor_id"] = investors["investor_id"].astype("string")
    inv["investor_type_grp"] = investors.get(
        "investor_type_grp", pd.Series(pd.NA, index=investors.index)
    ).astype("string")

    j = di.merge(inv, on="investor_id", how="left")
    j["_is_public"] = _mask(j["investor_type_grp"].isin(config.PUBLIC_INVESTOR_GRPS))
    j["_is_private"] = _mask(j["investor_type_grp"].isin(config.PRIVATE_INVESTOR_GRPS))

    per_deal = j.groupby("deal_id").agg(
        has_public=("_is_public", "max"), has_private=("_is_private", "max")
    )
    coinvest_deals = set(per_deal[per_deal["has_public"] & per_deal["has_private"]].index)
    if not coinvest_deals:
        return set()

    deal_to_company = deals[["deal_id", "company_id"]].copy()
    deal_to_company["deal_id"] = deal_to_company["deal_id"].astype("string")
    hit = deal_to_company[deal_to_company["deal_id"].isin(coinvest_deals)]
    return set(hit["company_id"].astype("string").dropna())


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------
_FLAG_COLS = [
    "any_vc", "any_grant", "any_debt", "any_accelerator", "any_growth_pe",
    "any_crowdfunding", "any_public_investor", "any_corporate_investor",
    "any_ivc_investor", "any_accelerator_investor", "any_lender_investor",
]
_COUNT_COLS = ["n_deals", "n_rounds_vc", "n_deals_with_size", "n_investors_lifetime"]


def build_firm_table(tables: dict[str, pd.DataFrame], spine_frame: pd.DataFrame) -> Step2Result:
    """Assemble company_analysis, one row per firm, from the clean tables."""
    firm = spine_frame.copy()
    firm["company_id"] = firm["company_id"].astype("string")

    # Firm scalars derived from the spine.
    firm["year_founded"] = _numeric(firm.get("year_founded")).astype("Int64")
    firm["age_years"] = (config.REFERENCE_YEAR - firm["year_founded"]).astype("Int64")
    firm["cohort"] = _cohort(firm["year_founded"])
    firm["employees"] = _numeric(firm.get("employees"))
    firm["employee_band"] = _employee_band(firm["employees"])
    firm["total_raised"] = _numeric(firm.get("total_raised"))

    hq_by_company = firm.set_index("company_id")["hq_country"] if "hq_country" in firm else pd.Series(dtype="string")

    # Block joins, each already at firm grain.
    deals_agg = _deal_aggregates(tables.get("deals_clean", pd.DataFrame()))
    firm = firm.merge(deals_agg, on="company_id", how="left")

    inv_agg = _investor_aggregates(
        tables.get("company_investors_clean", pd.DataFrame()),
        tables.get("investors_clean", pd.DataFrame()),
        hq_by_company,
    )
    firm = firm.merge(inv_agg, on="company_id", how="left")

    coinvest = _same_deal_coinvestment(
        tables.get("deal_investors_clean", pd.DataFrame()),
        tables.get("investors_clean", pd.DataFrame()),
        tables.get("deals_clean", pd.DataFrame()),
    )

    # Counts and flags: absence of a record is a real zero (rule N2).
    for col in _COUNT_COLS:
        firm[col] = _numeric(firm.get(col)).fillna(0).astype("int64")
    for col in _FLAG_COLS:
        firm[col] = _mask(firm.get(col)).astype("int64")

    firm["financed"] = (firm["n_deals"] >= 1).astype("int64")

    # Funding lags: year of first deal minus founding year; negatives are errors.
    firm["first_funding_lag"] = _year(firm["first_deal_date"]) - firm["year_founded"]
    firm["first_vc_lag"] = _year(firm["first_vc_date"]) - firm["year_founded"]
    n_neg_fund = int(_mask(firm["first_funding_lag"] < 0).sum())
    n_neg_vc = int(_mask(firm["first_vc_lag"] < 0).sum())
    firm.loc[_mask(firm["first_funding_lag"] < 0), "first_funding_lag"] = pd.NA
    firm.loc[_mask(firm["first_vc_lag"] < 0), "first_vc_lag"] = pd.NA
    firm["first_funding_lag"] = firm["first_funding_lag"].astype("Int64")
    firm["first_vc_lag"] = firm["first_vc_lag"].astype("Int64")

    # Public / private capital.
    firm["public_private_lifetime"] = (
        _mask(firm["any_public_investor"].astype(bool))
        & _mask(
            firm["any_corporate_investor"].astype(bool)
            | firm["any_ivc_investor"].astype(bool)
        )
    ).astype("int64")
    firm["public_private_same_deal"] = _mask(
        firm["company_id"].isin(coinvest)
    ).astype("int64")

    firm = firm[_ordered_columns(firm)].reset_index(drop=True)
    result = Step2Result(
        company_analysis=firm,
        n_negative_funding_lag=n_neg_fund,
        n_negative_vc_lag=n_neg_vc,
    )
    result.coverage = _coverage_report(firm)
    result.audit = _audit(firm, tables)
    return result


_COLUMN_ORDER = [
    "company_id", "green", "green_stage", "green_signal_group",
    "year_founded", "age_years", "cohort", "hq_country", "hq_city",
    "employees", "employee_band", "business_status",
    "primary_sector", "primary_industry_group", "primary_industry_code", "total_raised",
    "n_deals", "n_rounds_vc", "financed", "any_vc", "any_grant", "any_debt",
    "any_accelerator", "any_growth_pe", "any_crowdfunding",
    "first_deal_date", "first_deal_type", "first_deal_size",
    "last_deal_date", "last_deal_type", "last_deal_size",
    "median_deal_size", "total_deal_size_obs", "n_deals_with_size",
    "first_vc_date", "first_funding_lag", "first_vc_lag",
    "n_investors_lifetime", "any_public_investor", "any_corporate_investor",
    "any_ivc_investor", "any_accelerator_investor", "any_lender_investor",
    "share_investors_domestic", "share_investors_eu_cross_border",
    "share_investors_non_european", "public_private_lifetime", "public_private_same_deal",
]


def _ordered_columns(firm: pd.DataFrame) -> list[str]:
    ordered = [c for c in _COLUMN_ORDER if c in firm.columns]
    extra = [c for c in firm.columns if c not in ordered]
    return ordered + extra


# --------------------------------------------------------------------------
# Coverage and audit
# --------------------------------------------------------------------------
def _presence(series: pd.Series) -> pd.Series:
    if series.dtype == object or str(series.dtype) == "string":
        return nonnull_mask(series)
    return series.notna()


def _coverage_report(firm: pd.DataFrame) -> pd.DataFrame:
    """Per-column non-null share, split green vs other, to expose the T4.0 asymmetry."""
    is_green = _mask(firm.get("green", pd.Series(0, index=firm.index)) == 1)
    n_green = int(is_green.sum())
    n_other = int((~is_green).sum())
    rows = []
    for col in firm.columns:
        if col == "company_id":
            continue
        present = _presence(firm[col])
        rows.append(
            {
                "column": col,
                "pct_all": round(100.0 * present.mean(), 1) if len(firm) else float("nan"),
                "pct_green": round(100.0 * present[is_green].mean(), 1) if n_green else float("nan"),
                "pct_other": round(100.0 * present[~is_green].mean(), 1) if n_other else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def _audit(firm: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    pop = len(firm)
    rows = [
        {"check": "rows", "value": pop, "note": "one row per firm"},
        {"check": "company_id_unique", "value": int(firm["company_id"].is_unique), "note": "1 = unique"},
        {"check": "green_total", "value": int((firm["green"] == 1).sum()), "note": ""},
        {"check": "financed_total", "value": int(firm["financed"].sum()),
         "note": f"expected {config.EXPECTED_FINANCED}"},
    ]
    for name in ("deals_clean", "company_investors_clean"):
        df = tables.get(name, pd.DataFrame())
        distinct = int(df["company_id"].nunique()) if "company_id" in df.columns and not df.empty else 0
        rows.append(
            {
                "check": f"{name}_distinct_firms",
                "value": distinct,
                "note": f"{(distinct / pop):.1%} of population" if pop else "",
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------
def write_outputs(result: Step2Result, output_dir: Path | None = None) -> Path:
    """Write company_analysis.parquet plus the coverage and audit CSVs."""
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    table_path = out / config.OUTPUT_TABLE
    result.company_analysis.to_parquet(table_path, engine="pyarrow", index=False)
    print(f"[step2] wrote {table_path}  ({len(result.company_analysis):,} rows)")

    result.coverage.to_csv(out / "step2_coverage.csv", index=False)
    result.audit.to_csv(out / "step2_audit.csv", index=False)
    print(f"[step2] wrote {out / 'step2_coverage.csv'}")
    print(f"[step2] wrote {out / 'step2_audit.csv'}")
    return out


def acceptance_report(result: Step2Result) -> list[str]:
    """Checks that say whether Step 2 succeeded. Warns, never raises."""
    firm = result.company_analysis
    lines: list[str] = []

    n = len(firm)
    lines.append(f"Rows: {n} (expected {config.SPEC_POP_TOTAL})")
    if n != config.SPEC_POP_TOTAL:
        lines.append(f"  WARN: rows {n} != expected {config.SPEC_POP_TOTAL}")
    if not firm.empty and not firm["company_id"].is_unique:
        lines.append("  WARN: company_id is not unique")

    n_green = int((firm["green"] == 1).sum())
    lines.append(f"Green firms: {n_green}")

    n_financed = int(firm["financed"].sum())
    lines.append(f"Financed firms: {n_financed} (expected {config.EXPECTED_FINANCED})")
    if config.EXPECTED_FINANCED and abs(n_financed - config.EXPECTED_FINANCED) > 0.02 * config.EXPECTED_FINANCED:
        lines.append("  WARN: financed count differs from the Step 1 audit by more than 2%")

    missing_cohort = int((~_presence(firm["cohort"])).sum()) if "cohort" in firm else n
    lines.append(f"Firms without a cohort: {missing_cohort}")
    if missing_cohort:
        lines.append("  WARN: some firms have no cohort (founding year missing or out of range)")

    lines.append(
        f"Negative funding lags set to NA: {result.n_negative_funding_lag} funding, "
        f"{result.n_negative_vc_lag} VC"
    )

    if "n_deals_with_size" in firm and "total_deal_size_obs" in firm:
        lone = int(_mask((firm["n_deals_with_size"] == 0) & _presence(firm["total_deal_size_obs"])).sum())
        if lone:
            lines.append(f"  WARN: {lone} firms have a deal-size total with zero sized deals")

    log("[step2] coverage (green vs other) top rows:")
    return lines
