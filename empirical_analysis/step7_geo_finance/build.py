"""Step 7 build logic (block A): the geography x finance tables.

Everything is descriptive and a 2026 snapshot of recorded capital. T4.26 crosses each
country's green share of firms with its green share of capital (reported with both
`total_raised` and summed disclosed `deal_size`, coverage shown). T4.28 resolves the
Step 6 investor-origin question per country. T4.29 splits disclosed deal capital by
country x stage_group. No country floor: every country with a start-up is reported and
thin green cells carry low_n_flag. Block B (the collapsed by-country comparison of the
Step 5/6 tables) lives in `by_country.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
# Reuse the Step 6 relation join and origin classification so T4.28 matches T4.23.
from ..step6_investors import build as s6


@dataclass
class Step7Result:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    caption: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _clean_str(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    return s.mask(s == "")


def _ratio(num: float, den: float) -> float:
    if pd.isna(num) or pd.isna(den) or den == 0:
        return float("nan")
    return round(num / den, 3)


def _stage_sort(values) -> list:
    order = {name: i for i, name in enumerate(config.STAGE_GROUP_ORDER)}
    present = [v for v in values if pd.notna(v)]
    return sorted(set(present), key=lambda v: order.get(v, len(order)))


def _deal_size_by_firm(deals: pd.DataFrame) -> pd.Series:
    """Sum of disclosed deal_size per company_id (recorded amounts only, rule N1)."""
    if deals.empty or config.DEAL_SIZE_FIELD not in deals.columns:
        return pd.Series(dtype=float)
    d = deals[["company_id", config.DEAL_SIZE_FIELD]].copy()
    d["company_id"] = d["company_id"].astype("string")
    d[config.DEAL_SIZE_FIELD] = _num(d[config.DEAL_SIZE_FIELD])
    d = d[d[config.DEAL_SIZE_FIELD].notna()]
    return d.groupby("company_id")[config.DEAL_SIZE_FIELD].sum()


# --------------------------------------------------------------------------
# T4.26 green firm-share vs green funding-share by country
# --------------------------------------------------------------------------
def build_green_share_firms_vs_capital(
    firm: pd.DataFrame, deals: pd.DataFrame, min_country_n: int | None = None
) -> pd.DataFrame:
    min_n = config.MIN_COUNTRY_N if min_country_n is None else min_country_n
    cols = [
        "country", "green_firm_share", "green_funding_share_total_raised",
        "green_funding_share_dealsize", "ratio_tr", "ratio_ds",
        "coverage_total_raised", "coverage_dealsize", "low_n_flag",
        "n_green", "n_others", "n_startups",
    ]

    work = pd.DataFrame(
        {
            "company_id": firm["company_id"].astype("string"),
            "country": _clean_str(firm[config.HQ_COUNTRY_FIELD]),
            "green": (firm["green"] == 1).astype(int),
            "total_raised": _num(firm[config.TOTAL_RAISED_FIELD]),
        }
    ).dropna(subset=["country"])

    ds_by_firm = _deal_size_by_firm(deals)
    work["deal_size_sum"] = work["company_id"].map(ds_by_firm)

    rows = []
    for country, sub in work.groupby("country"):
        n_startups = len(sub)
        n_green = int(sub["green"].sum())
        n_others = n_startups - n_green
        if n_startups < min_n:
            continue
        green = sub[sub["green"] == 1]
        other = sub[sub["green"] == 0]

        tr = sub["total_raised"]
        tr_total = float(tr[tr.notna()].sum())
        tr_green = float(green["total_raised"][green["total_raised"].notna()].sum())
        ds = sub["deal_size_sum"]
        ds_total = float(ds[ds.notna()].sum())
        ds_green = float(green["deal_size_sum"][green["deal_size_sum"].notna()].sum())

        firm_share = round(n_green / n_startups, 4) if n_startups else float("nan")
        fs_tr = round(tr_green / tr_total, 4) if tr_total else float("nan")
        fs_ds = round(ds_green / ds_total, 4) if ds_total else float("nan")
        rows.append(
            {
                "country": country,
                "green_firm_share": firm_share,
                "green_funding_share_total_raised": fs_tr,
                "green_funding_share_dealsize": fs_ds,
                "ratio_tr": _ratio(fs_tr, firm_share),
                "ratio_ds": _ratio(fs_ds, firm_share),
                "coverage_total_raised": round(float(tr.notna().mean()), 4),
                "coverage_dealsize": round(float(ds.notna().mean()), 4),
                "low_n_flag": int(n_green < config.LOW_N_FLAG),
                "n_green": n_green,
                "n_others": n_others,
                "n_startups": n_startups,
            }
        )
    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values("n_startups", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# T4.10 cumulative total_raised by country (absolute amounts, not shares)
# --------------------------------------------------------------------------
def build_cumulative_total_raised_by_country(
    firm: pd.DataFrame, min_country_n: int | None = None
) -> pd.DataFrame:
    """Sum lifetime total_raised by country and group (USD m, recorded amounts only)."""
    min_n = config.MIN_COUNTRY_N if min_country_n is None else min_country_n
    cols = [
        "country", "green_total_raised", "other_total_raised", "total_total_raised",
        "coverage_total_raised", "low_n_flag",
        "n_green", "n_others", "n_startups",
    ]

    work = pd.DataFrame(
        {
            "country": _clean_str(firm[config.HQ_COUNTRY_FIELD]),
            "green": (firm["green"] == 1).astype(int),
            "total_raised": _num(firm[config.TOTAL_RAISED_FIELD]),
        }
    ).dropna(subset=["country"])

    rows = []
    for country, sub in work.groupby("country"):
        n_startups = len(sub)
        n_green = int(sub["green"].sum())
        n_others = n_startups - n_green
        if n_startups < min_n:
            continue
        green = sub[sub["green"] == 1]
        other = sub[sub["green"] == 0]
        tr = sub["total_raised"]
        tr_green = float(green["total_raised"].dropna().sum())
        tr_other = float(other["total_raised"].dropna().sum())
        rows.append(
            {
                "country": country,
                "green_total_raised": round(tr_green, 2),
                "other_total_raised": round(tr_other, 2),
                "total_total_raised": round(tr_green + tr_other, 2),
                "coverage_total_raised": round(float(tr.notna().mean()), 4),
                "low_n_flag": int(n_green < config.LOW_N_FLAG),
                "n_green": n_green,
                "n_others": n_others,
                "n_startups": n_startups,
            }
        )
    return pd.DataFrame(rows, columns=cols).sort_values(
        "n_startups", ascending=False
    ).reset_index(drop=True)


# --------------------------------------------------------------------------
# T4.28 investor origin by country
# --------------------------------------------------------------------------
def build_investor_origin_by_country(
    firm: pd.DataFrame,
    company_investors: pd.DataFrame,
    investors: pd.DataFrame,
    min_country_n: int | None = None,
) -> pd.DataFrame:
    min_n = config.MIN_COUNTRY_N if min_country_n is None else min_country_n
    cols = [
        "country",
        "green_domestic", "green_eu_cross_border", "green_non_european",
        "other_domestic", "other_eu_cross_border", "other_non_european",
        "country_coverage", "low_n_flag", "n_green", "n_others", "n_startups",
    ]
    rel = s6.relation_frame(firm, company_investors, investors)
    if rel.empty:
        return pd.DataFrame(columns=cols)

    european = s6._european_set(firm)
    rel["country"] = _clean_str(rel["hq_country"])
    rel = rel.dropna(subset=["country"])

    origins = ["domestic", "european_cross_border", "non_european"]
    col_by_origin = {
        "domestic": "domestic",
        "european_cross_border": "eu_cross_border",
        "non_european": "non_european",
    }

    rows = []
    for country, sub in rel.groupby("country"):
        # Country-level population count uses all firms in the country.
        n_country_firms = int((_clean_str(firm[config.HQ_COUNTRY_FIELD]) == country).sum())
        if n_country_firms < min_n:
            continue
        coverage = round(float(sub["investor_country"].notna().mean()), 4)
        known = sub[sub["investor_country"].notna()].copy()
        if known.empty:
            continue
        known["origin"] = s6._classify_origin(known, european)
        g_known = known[known["green"] == 1]
        o_known = known[known["green"] != 1]
        n_g, n_o = len(g_known), len(o_known)

        row = {"country": country, "country_coverage": coverage,
               "low_n_flag": int(n_g < config.LOW_N_FLAG),
               "n_green": n_g, "n_others": n_o, "n_startups": n_g + n_o}
        for origin in origins:
            suffix = col_by_origin[origin]
            g_share = ((g_known["origin"] == origin).sum() / n_g) if n_g else float("nan")
            o_share = ((o_known["origin"] == origin).sum() / n_o) if n_o else float("nan")
            row[f"green_{suffix}"] = round(float(g_share), 4)
            row[f"other_{suffix}"] = round(float(o_share), 4)
        rows.append(row)

    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values("n_startups", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# T4.29 country funding by financing type (disclosed deal_size)
# --------------------------------------------------------------------------
def build_country_funding_by_type(
    firm: pd.DataFrame, deals: pd.DataFrame, min_country_n: int | None = None
) -> pd.DataFrame:
    min_n = config.MIN_COUNTRY_N if min_country_n is None else min_country_n
    cols = [
        "country", "stage_group", "green_amount", "other_amount", "total_amount",
        "green_amount_share", "low_n_flag", "n_green", "n_others", "n_startups",
    ]
    if deals.empty or config.DEAL_SIZE_FIELD not in deals.columns:
        return pd.DataFrame(columns=cols)

    attr = firm[["company_id", "green", config.HQ_COUNTRY_FIELD]].copy()
    attr["company_id"] = attr["company_id"].astype("string")
    attr["country"] = _clean_str(attr[config.HQ_COUNTRY_FIELD])
    attr["green"] = (attr["green"] == 1).astype(int)

    d = deals[["company_id", "stage_group", config.DEAL_SIZE_FIELD]].copy()
    d["company_id"] = d["company_id"].astype("string")
    d[config.DEAL_SIZE_FIELD] = _num(d[config.DEAL_SIZE_FIELD])
    d = d[d[config.DEAL_SIZE_FIELD].notna()]
    d = d.merge(attr[["company_id", "green", "country"]], on="company_id", how="left")
    d = d.dropna(subset=["country"])

    # Country populations for the floor gate.
    country_pop = _clean_str(firm[config.HQ_COUNTRY_FIELD]).value_counts()
    keep = set(country_pop[country_pop >= min_n].index)

    rows = []
    for country in [c for c in country_pop.index if c in keep]:
        dc = d[d["country"] == country]
        if dc.empty:
            continue
        for stage in _stage_sort(dc["stage_group"].dropna().unique()):
            ds = dc[dc["stage_group"] == stage]
            g = ds[ds["green"] == 1]
            o = ds[ds["green"] == 0]
            g_amt = round(float(g[config.DEAL_SIZE_FIELD].sum()), 2)
            o_amt = round(float(o[config.DEAL_SIZE_FIELD].sum()), 2)
            total = round(g_amt + o_amt, 2)
            rows.append(
                {
                    "country": country,
                    "stage_group": stage,
                    "green_amount": g_amt,
                    "other_amount": o_amt,
                    "total_amount": total,
                    "green_amount_share": round(g_amt / total, 4) if total else float("nan"),
                    "low_n_flag": int(len(g) < config.LOW_N_FLAG),
                    "n_green": len(g),
                    "n_others": len(o),
                    "n_startups": len(ds),
                }
            )
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# F4.26 figure data (green firm-share vs green funding-share scatter)
# --------------------------------------------------------------------------
def build_green_share_figure(t426: pd.DataFrame) -> pd.DataFrame:
    cols = ["country", "green_firm_share", "green_funding_share_total_raised",
            "reference", "low_n_flag", "n_green", "n_others", "n_startups"]
    if t426.empty:
        return pd.DataFrame(columns=cols)
    out = t426[["country", "green_firm_share", "green_funding_share_total_raised",
                "low_n_flag", "n_green", "n_others", "n_startups"]].copy()
    out["reference"] = out["green_firm_share"]
    return out[cols].reset_index(drop=True)


# --------------------------------------------------------------------------
# Orchestration (block A only; block B is added by run.py via by_country.py)
# --------------------------------------------------------------------------
def build_all(
    firm: pd.DataFrame,
    deals: pd.DataFrame | None = None,
    company_investors: pd.DataFrame | None = None,
    investors: pd.DataFrame | None = None,
) -> Step7Result:
    result = Step7Result()
    deals = deals if deals is not None else pd.DataFrame()
    company_investors = company_investors if company_investors is not None else pd.DataFrame()
    investors = investors if investors is not None else pd.DataFrame()

    t426 = build_green_share_firms_vs_capital(firm, deals)
    result.tables["T4_26_green_share_firms_vs_capital"] = t426
    result.tables["T4_10_cumulative_total_raised_by_country"] = (
        build_cumulative_total_raised_by_country(firm)
    )
    result.tables["T4_28_investor_origin_by_country"] = build_investor_origin_by_country(
        firm, company_investors, investors)
    result.tables["T4_29_country_funding_by_type"] = build_country_funding_by_type(
        firm, deals)
    result.tables["F4_26_green_share_scatter"] = build_green_share_figure(t426)

    result.caption["T4_26_green_share_firms_vs_capital"] = (
        "Green share of firms (full population) vs green share of capital, reported "
        "with both total_raised and summed disclosed deal_size (coverage on the row). "
        "ratio>1 means green attracts more capital than its firm count implies. A 2026 "
        "snapshot of recorded capital, not an investment-flow series. Every country is "
        "shown; rows with fewer than 30 green firms carry low_n_flag."
    )
    result.caption["T4_10_cumulative_total_raised_by_country"] = (
        "Country grain: summed lifetime total_raised (USD millions, recorded amounts "
        "only, rule N1) on the full country population. Complements the block-B T4.10 "
        "median and T4.26 funding shares with absolute green / other / total capital. "
        "Missing total_raised is unobserved, not zero. A 2026 snapshot, not a flow "
        "series; coverage_total_raised is on every row."
    )
    result.caption["T4_28_investor_origin_by_country"] = (
        "Relation grain over the INVESTED subsample, known investor-country only "
        "(coverage on the row). Origin matches T4.23: domestic = investor country "
        "equals the firm's; European cross-border = any other firm hq_country; "
        "non-European otherwise. Every country shown; low_n_flag on thin green cells."
    )
    result.caption["T4_29_country_funding_by_type"] = (
        "Country x stage_group split of disclosed deal capital (summed deal_size, "
        "recorded amounts only, rule N1). n counts deals with a disclosed size."
    )
    return result


def write_outputs(result: Step7Result, output_dir: Path | None = None) -> Path:
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in result.tables.items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"[step7] wrote {path}  ({len(df)} rows)")
    if result.caption:
        cap = pd.DataFrame(
            [{"output": k, "caption": v} for k, v in result.caption.items()]
        )
        cap.to_csv(out / "captions_step7.csv", index=False)
        print(f"[step7] wrote {out / 'captions_step7.csv'}")
    return out


def acceptance_report(firm: pd.DataFrame, result: Step7Result) -> list[str]:
    lines: list[str] = []

    t426 = result.tables["T4_26_green_share_firms_vs_capital"]
    n_countries = len(t426)
    flagged = int(t426["low_n_flag"].sum()) if not t426.empty else 0
    n_sens = int((t426["n_startups"] >= config.MIN_COUNTRY_N_SENSITIVITY).sum()) if not t426.empty else 0
    lines.append(
        f"T4.26: {n_countries} countries reported (no floor); "
        f"{flagged} with low_n_flag; {n_sens} at n>={config.MIN_COUNTRY_N_SENSITIVITY} "
        f"(the former floor)"
    )
    if not t426.empty:
        conc = t426[(t426["ratio_tr"].notna()) & (t426["ratio_tr"] > 1)]
        top = conc.sort_values("n_startups", ascending=False).head(3)
        for _, r in top.iterrows():
            lines.append(
                f"  {r['country']}: firm_share={r['green_firm_share']} "
                f"funding_share_tr={r['green_funding_share_total_raised']} "
                f"ratio_tr={r['ratio_tr']} (cov_tr={r['coverage_total_raised']})"
            )

    t428 = result.tables["T4_28_investor_origin_by_country"]
    if not t428.empty:
        g_sum = (t428["green_domestic"] + t428["green_eu_cross_border"]
                 + t428["green_non_european"])
        o_sum = (t428["other_domestic"] + t428["other_eu_cross_border"]
                 + t428["other_non_european"])
        bad_g = int((g_sum.sub(1).abs() > 1e-2).sum())
        bad_o = int((o_sum.sub(1).abs() > 1e-2).sum())
        lines.append(
            f"T4.28: {len(t428)} countries; origin shares off-by-one rows: "
            f"green={bad_g} other={bad_o} (expect 0, small rounding tolerated)"
        )

    t429 = result.tables["T4_29_country_funding_by_type"]
    if not t429.empty:
        total = round(float(t429["total_amount"].sum()), 2)
        lines.append(f"T4.29: {len(t429)} country x stage rows; "
                     f"summed disclosed deal capital={total}")

    t410 = result.tables.get("T4_10_cumulative_total_raised_by_country")
    if t410 is not None and not t410.empty and not t426.empty:
        merged = t426.merge(
            t410[["country", "green_total_raised", "total_total_raised"]],
            on="country",
            how="inner",
        )
        merged["share_check"] = merged.apply(
            lambda r: round(r["green_total_raised"] / r["total_total_raised"], 4)
            if r["total_total_raised"] else float("nan"),
            axis=1,
        )
        bad = merged[
            merged["share_check"].notna()
            & merged["green_funding_share_total_raised"].notna()
            & (merged["share_check"] - merged["green_funding_share_total_raised"]).abs()
            > 1e-3
        ]
        lines.append(
            f"T4.10 cumulative total_raised: {len(t410)} countries; "
            f"share reconcile with T4.26: {len(bad)} mismatches (expect 0)"
        )

    return lines
