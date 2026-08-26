"""Step 7 block B: the collapsed by-country comparison of every Step 5/6 table.

For each Step 5 (T4.9-T4.17, F4.4) and Step 6 (T4.18/19/21/22/23/25, F4.5) table this
produces one `*_by_country.csv` with one row per country carrying that table's
headline statistic green vs other, the secondary dimension (cohort / stage / measure)
collapsed. No statistic is redefined: every headline is computed with the same helpers
and subsample rules the Step 5/6 builders use (`_financed`, `_invested`, `_median`,
`_split`, the VC/stage sets), applied to a single-country slice and reduced to one row.
No country floor: every country with a start-up is reported; rows with fewer than 30
green (firms / relations / deals, per the table's grain) carry low_n_flag.
"""

from __future__ import annotations

import pandas as pd

from . import config
from ..step5_funding import build as s5
from ..step5_funding import config as s5cfg
from ..step6_investors import build as s6
from ..step6_investors import config as s6cfg


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _clean_str(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    return s.mask(s == "")


def _diff(green: float, other: float, dp: int = 4) -> float:
    if pd.isna(green) or pd.isna(other):
        return float("nan")
    return round(green - other, dp)


# --------------------------------------------------------------------------
# Country slicing
# --------------------------------------------------------------------------
def qualifying_countries(firm: pd.DataFrame, min_n: int | None = None) -> list[str]:
    """Countries present in hq_country with n_startups >= min_n (default: all)."""
    min_n = config.MIN_COUNTRY_N if min_n is None else min_n
    counts = _clean_str(firm[config.HQ_COUNTRY_FIELD]).value_counts()
    return [c for c in counts.index if counts[c] >= min_n]


def _country_slice(
    country: str,
    firm: pd.DataFrame,
    deals: pd.DataFrame,
    company_investors: pd.DataFrame,
    deal_investors: pd.DataFrame,
) -> dict:
    """Firm slice for the country plus the deal / relation frames filtered to it.

    `investors` stays global (joined by id). deal_investors is filtered to the deals
    of the slice.
    """
    mask = _clean_str(firm[config.HQ_COUNTRY_FIELD]) == country
    firm_c = firm[mask].copy()
    ids = set(firm_c["company_id"].astype("string"))

    if not deals.empty:
        d = deals.copy()
        d["company_id"] = d["company_id"].astype("string")
        deals_c = d[d["company_id"].isin(ids)].copy()
    else:
        deals_c = deals

    if not company_investors.empty:
        ci = company_investors.copy()
        ci["company_id"] = ci["company_id"].astype("string")
        ci_c = ci[ci["company_id"].isin(ids)].copy()
    else:
        ci_c = company_investors

    if not deal_investors.empty and not deals_c.empty and "deal_id" in deals_c.columns:
        deal_ids = set(deals_c["deal_id"].astype("string"))
        di = deal_investors.copy()
        di["deal_id"] = di["deal_id"].astype("string")
        di_c = di[di["deal_id"].isin(deal_ids)].copy()
    else:
        di_c = deal_investors

    return {"firm": firm_c, "deals": deals_c, "ci": ci_c, "di": di_c}


# --------------------------------------------------------------------------
# Headline functions — each returns a dict for one country (no country/flag yet)
# --------------------------------------------------------------------------
def _hl_t409(ctx, investors, european) -> dict:
    firm_c = ctx["firm"]
    g, o = s5._split(firm_c)
    gf = float((_num(g["financed"]) == 1).mean()) if len(g) else float("nan")
    of = float((_num(o["financed"]) == 1).mean()) if len(o) else float("nan")
    gv = float((_num(g["any_vc"]) == 1).mean()) if len(g) else float("nan")
    ov = float((_num(o["any_vc"]) == 1).mean()) if len(o) else float("nan")
    return {
        "green_share_financed": round(gf, 4), "other_share_financed": round(of, 4),
        "diff_financed": _diff(gf, of),
        "green_share_vc": round(gv, 4), "other_share_vc": round(ov, 4),
        "diff_vc": _diff(gv, ov),
        "n_green": len(g), "n_others": len(o), "n_startups": len(firm_c),
    }


def _hl_t410(ctx, investors, european) -> dict:
    fin = s5._financed(ctx["firm"])
    g, o = s5._split(fin)
    gm, om = s5._median(g["total_raised"]), s5._median(o["total_raised"])
    return {
        "green_median_total_raised": gm, "other_median_total_raised": om,
        "median_ratio": s5._ratio(gm, om),
        "n_green": len(g), "n_others": len(o), "n_startups": len(fin),
    }


def _hl_t411(ctx, investors, european) -> dict:
    firm_c = ctx["firm"]
    fd = s5._first_deals(ctx["deals"])
    if fd.empty:
        return {"green_median_first_size": float("nan"),
                "other_median_first_size": float("nan"), "median_ratio": float("nan"),
                "n_green": 0, "n_others": 0, "n_startups": 0}
    green_by = firm_c.set_index(firm_c["company_id"].astype("string"))["green"]
    fd["company_id"] = fd["company_id"].astype("string")
    fd["green"] = fd["company_id"].map(green_by).fillna(0).astype(int)
    fd["deal_size"] = _num(fd["deal_size"])
    ws = fd[fd["deal_size"].notna()]
    g, o = s5._split(ws)
    gm, om = s5._median(g["deal_size"]), s5._median(o["deal_size"])
    return {
        "green_median_first_size": gm, "other_median_first_size": om,
        "median_ratio": s5._ratio(gm, om),
        "n_green": len(g), "n_others": len(o), "n_startups": len(ws),
    }


def _hl_t412(ctx, investors, european) -> dict:
    firm_c = ctx["firm"]
    deals_c = ctx["deals"]
    cols_out = {"green_median_valuation": float("nan"),
                "other_median_valuation": float("nan"), "median_ratio": float("nan"),
                "n_green": 0, "n_others": 0, "n_startups": 0}
    if deals_c.empty or "post_valuation" not in deals_c.columns:
        return cols_out
    d = deals_c[["company_id", "post_valuation"]].copy()
    d["company_id"] = d["company_id"].astype("string")
    d["post_valuation"] = _num(d["post_valuation"])
    d = d[d["post_valuation"].notna()]
    if d.empty:
        return cols_out
    per_firm = d.groupby("company_id")["post_valuation"].median().reset_index()
    green_by = firm_c.set_index(firm_c["company_id"].astype("string"))["green"]
    per_firm["green"] = per_firm["company_id"].map(green_by).fillna(0).astype(int)
    g, o = s5._split(per_firm)
    gm, om = s5._median(g["post_valuation"]), s5._median(o["post_valuation"])
    return {
        "green_median_valuation": gm, "other_median_valuation": om,
        "median_ratio": s5._ratio(gm, om),
        "n_green": len(g), "n_others": len(o), "n_startups": len(per_firm),
    }


def _hl_t413(ctx, investors, european) -> dict:
    fin = s5._financed(ctx["firm"])
    g, o = s5._split(fin)
    out = {}
    for measure in ("first_funding_lag", "first_vc_lag"):
        gm = s5._median(g[measure]) if measure in fin.columns else float("nan")
        om = s5._median(o[measure]) if measure in fin.columns else float("nan")
        out[f"green_median_{measure}"] = gm
        out[f"other_median_{measure}"] = om
        out[f"diff_{measure}"] = (round(gm - om, 2)
                                  if pd.notna(gm) and pd.notna(om) else float("nan"))
    out.update({"n_green": len(g), "n_others": len(o), "n_startups": len(fin)})
    return out


def _hl_t414(ctx, investors, european) -> dict:
    firm_c = ctx["firm"]
    fd = s5._first_deals(ctx["deals"])
    if fd.empty:
        return {"green_share_first_vc": float("nan"),
                "other_share_first_vc": float("nan"), "difference": float("nan"),
                "n_green": 0, "n_others": 0, "n_startups": 0}
    green_by = firm_c.set_index(firm_c["company_id"].astype("string"))["green"]
    fd["company_id"] = fd["company_id"].astype("string")
    fd["green"] = fd["company_id"].map(green_by).fillna(0).astype(int)
    fd["is_vc"] = fd["stage_group"].isin(s5cfg.VC_STAGE_GROUPS)
    g, o = s5._split(fd)
    gs = float(g["is_vc"].mean()) if len(g) else float("nan")
    os_ = float(o["is_vc"].mean()) if len(o) else float("nan")
    return {
        "green_share_first_vc": round(gs, 4), "other_share_first_vc": round(os_, 4),
        "difference": _diff(gs, os_),
        "n_green": len(g), "n_others": len(o), "n_startups": len(fd),
    }


def _hl_t415(ctx, investors, european) -> dict:
    firm_c = ctx["firm"]
    deals_c = ctx["deals"]
    if deals_c.empty:
        return {"green_share_vc_deals": float("nan"),
                "other_share_vc_deals": float("nan"), "difference": float("nan"),
                "n_green": 0, "n_others": 0, "n_startups": 0}
    d = s5._deals_with_green(firm_c, deals_c)
    d["is_vc"] = d["stage_group"].isin(s5cfg.VC_STAGE_GROUPS)
    g, o = s5._split(d)
    gs = float(g["is_vc"].mean()) if len(g) else float("nan")
    os_ = float(o["is_vc"].mean()) if len(o) else float("nan")
    return {
        "green_share_vc_deals": round(gs, 4), "other_share_vc_deals": round(os_, 4),
        "difference": _diff(gs, os_),
        "n_green": len(g), "n_others": len(o), "n_startups": len(d),
    }


def _hl_t416(ctx, investors, european) -> dict:
    firm_c = ctx["firm"]
    deals_c = ctx["deals"]
    if deals_c.empty:
        return {"green_median_deal_size": float("nan"),
                "other_median_deal_size": float("nan"), "median_ratio": float("nan"),
                "n_green": 0, "n_others": 0, "n_startups": 0}
    d = s5._deals_with_green(firm_c, deals_c)
    d["deal_size"] = _num(d["deal_size"])
    d = d[d["deal_size"].notna()]
    g, o = s5._split(d)
    gm, om = s5._median(g["deal_size"]), s5._median(o["deal_size"])
    return {
        "green_median_deal_size": gm, "other_median_deal_size": om,
        "median_ratio": s5._ratio(gm, om),
        "n_green": len(g), "n_others": len(o), "n_startups": len(d),
    }


def _hl_t417(ctx, investors, european) -> dict:
    fin = s5._financed(ctx["firm"])
    g, o = s5._split(fin)
    gm, om = s5._median(g["n_deals"]), s5._median(o["n_deals"])
    g2 = float((_num(g["n_deals"]) >= 2).mean()) if len(g) else float("nan")
    o2 = float((_num(o["n_deals"]) >= 2).mean()) if len(o) else float("nan")
    return {
        "green_median_n_deals": gm, "other_median_n_deals": om,
        "diff_n_deals": (round(gm - om, 2) if pd.notna(gm) and pd.notna(om) else float("nan")),
        "green_share_ge2_rounds": round(g2, 4), "other_share_ge2_rounds": round(o2, 4),
        "diff_ge2_rounds": _diff(g2, o2),
        "n_green": len(g), "n_others": len(o), "n_startups": len(fin),
    }


def _hl_f404(ctx, investors, european, horizon: int = 5) -> dict:
    firm_c = ctx["firm"]
    age = _num(firm_c["age_years"])
    fund_lag = _num(firm_c.get("first_funding_lag"))
    vc_lag = _num(firm_c.get("first_vc_lag"))
    green = (firm_c["green"] == 1)
    eligible = age >= horizon
    g_mask = eligible & green
    o_mask = eligible & ~green
    n_g, n_o = int(g_mask.sum()), int(o_mask.sum())
    gf = int(((fund_lag <= horizon) & g_mask).sum()) / n_g if n_g else float("nan")
    of = int(((fund_lag <= horizon) & o_mask).sum()) / n_o if n_o else float("nan")
    gv = int(((vc_lag <= horizon) & g_mask).sum()) / n_g if n_g else float("nan")
    ov = int(((vc_lag <= horizon) & o_mask).sum()) / n_o if n_o else float("nan")
    return {
        "horizon_years": horizon,
        "green_share_financed": round(gf, 4), "other_share_financed": round(of, 4),
        "diff_financed": _diff(gf, of),
        "green_share_vc": round(gv, 4), "other_share_vc": round(ov, 4),
        "diff_vc": _diff(gv, ov),
        "n_green": n_g, "n_others": n_o, "n_startups": n_g + n_o,
    }


def _hl_t418(ctx, investors, european) -> dict:
    invested = s6._invested(ctx["firm"])
    g, o = s6._split(invested)
    gs = float((_num(g["any_ivc_investor"]) == 1).mean()) if len(g) else float("nan")
    os_ = float((_num(o["any_ivc_investor"]) == 1).mean()) if len(o) else float("nan")
    return {
        "green_share_ivc": round(gs, 4), "other_share_ivc": round(os_, 4),
        "difference": _diff(gs, os_),
        "n_green": len(g), "n_others": len(o), "n_startups": len(invested),
    }


def _hl_t419(ctx, investors, european) -> dict:
    invested = s6._invested(ctx["firm"])
    g, o = s6._split(invested)
    gm = s6._median(g[s6cfg.N_INVESTORS_FIELD])
    om = s6._median(o[s6cfg.N_INVESTORS_FIELD])
    return {
        "green_median_n_investors": gm, "other_median_n_investors": om,
        "difference": (round(gm - om, 2) if pd.notna(gm) and pd.notna(om) else float("nan")),
        "n_green": len(g), "n_others": len(o), "n_startups": len(invested),
    }


def _hl_t421(ctx, investors, european) -> dict:
    invested = s6._invested(ctx["firm"])
    g, o = s6._split(invested)
    col = s6cfg.PUBLIC_PRIVATE_LIFETIME
    gs = float((_num(g[col]) == 1).mean()) if len(g) and col in invested.columns else float("nan")
    os_ = float((_num(o[col]) == 1).mean()) if len(o) and col in invested.columns else float("nan")
    return {
        "green_share_lifetime_combo": round(gs, 4), "other_share_lifetime_combo": round(os_, 4),
        "difference": _diff(gs, os_),
        "n_green": len(g), "n_others": len(o), "n_startups": len(invested),
    }


def _hl_t422(ctx, investors, european) -> dict:
    deals_c = ctx["deals"]
    if deals_c.empty:
        return {"green_share_grant_preceded": float("nan"),
                "other_share_grant_preceded": float("nan"), "difference": float("nan"),
                "n_green": 0, "n_others": 0, "n_startups": 0}
    per = s6._grant_vc_frame(ctx["firm"], deals_c)
    both = per[per["grant_date"].notna() & per["vc_date"].notna()].copy()
    both["preceded"] = both["grant_date"] < both["vc_date"]
    gb, ob = s6._split(both)
    gs = float(gb["preceded"].mean()) if len(gb) else float("nan")
    os_ = float(ob["preceded"].mean()) if len(ob) else float("nan")
    return {
        "green_share_grant_preceded": round(gs, 4) if pd.notna(gs) else gs,
        "other_share_grant_preceded": round(os_, 4) if pd.notna(os_) else os_,
        "difference": _diff(gs, os_),
        "n_green": len(gb), "n_others": len(ob), "n_startups": len(both),
    }


def _hl_t423(ctx, investors, european) -> dict:
    cols_default = {
        "green_domestic": float("nan"), "green_eu_cross_border": float("nan"),
        "green_non_european": float("nan"), "other_domestic": float("nan"),
        "other_eu_cross_border": float("nan"), "other_non_european": float("nan"),
        "country_coverage": float("nan"), "n_green": 0, "n_others": 0, "n_startups": 0,
    }
    rel = s6.relation_frame(ctx["firm"], ctx["ci"], investors)
    if rel.empty:
        return cols_default
    coverage = round(float(rel["investor_country"].notna().mean()), 4)
    known = rel[rel["investor_country"].notna()].copy()
    if known.empty:
        return cols_default
    known["origin"] = s6._classify_origin(known, european)
    g, o = s6._split(known)
    n_g, n_o = len(g), len(o)
    row = {"country_coverage": coverage, "n_green": n_g, "n_others": n_o,
           "n_startups": n_g + n_o}
    mapping = {"domestic": "domestic", "european_cross_border": "eu_cross_border",
               "non_european": "non_european"}
    for origin, suffix in mapping.items():
        gs = ((g["origin"] == origin).sum() / n_g) if n_g else float("nan")
        os_ = ((o["origin"] == origin).sum() / n_o) if n_o else float("nan")
        row[f"green_{suffix}"] = round(float(gs), 4)
        row[f"other_{suffix}"] = round(float(os_), 4)
    return row


def _hl_t425(ctx, investors, european) -> dict:
    firm_c = ctx["firm"]
    deals_c = ctx["deals"]
    if deals_c.empty:
        return {"green_median_investors": float("nan"),
                "other_median_investors": float("nan"),
                "green_pct_multi": float("nan"), "other_pct_multi": float("nan"),
                "n_green": 0, "n_others": 0, "n_startups": 0}
    d = s6._deals_with_green(firm_c, deals_c)
    d["n_investors"] = _num(d.get("n_investors"))
    g, o = s6._split(d)
    gm, om = s6._median(g["n_investors"]), s6._median(o["n_investors"])
    gmu = float((g["n_investors"] >= s6cfg.MULTI_INVESTOR_MIN).mean()) if len(g) else float("nan")
    omu = float((o["n_investors"] >= s6cfg.MULTI_INVESTOR_MIN).mean()) if len(o) else float("nan")
    return {
        "green_median_investors": gm, "other_median_investors": om,
        "green_pct_multi": round(gmu, 4), "other_pct_multi": round(omu, 4),
        "n_green": len(g), "n_others": len(o), "n_startups": len(d),
    }


# Registry: output file stem -> headline function.
BY_COUNTRY_TABLES = [
    ("T4_09_funding_access_by_country", _hl_t409),
    ("T4_10_total_raised_by_cohort_by_country", _hl_t410),
    ("T4_11_first_financing_size_by_stage_by_country", _hl_t411),
    ("T4_12_post_valuation_by_country", _hl_t412),
    ("T4_13_time_to_financing_by_country", _hl_t413),
    ("T4_14_first_financing_type_by_country", _hl_t414),
    ("T4_15_stage_composition_by_country", _hl_t415),
    ("T4_16_median_deal_size_by_stage_by_country", _hl_t416),
    ("T4_17_financing_trajectories_by_country", _hl_t417),
    ("F4_04_cumulative_financed_by_country", _hl_f404),
    ("T4_18_investor_type_distribution_by_country", _hl_t418),
    ("T4_19_investor_flags_by_country", _hl_t419),
    ("T4_21_public_private_by_country", _hl_t421),
    ("T4_22_grant_to_vc_by_country", _hl_t422),
    ("T4_23_investor_origin_by_country", _hl_t423),
    ("T4_25_syndication_by_country", _hl_t425),
]


def build_by_country(
    firm: pd.DataFrame,
    deals: pd.DataFrame | None = None,
    company_investors: pd.DataFrame | None = None,
    investors: pd.DataFrame | None = None,
    deal_investors: pd.DataFrame | None = None,
    min_country_n: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Build every `*_by_country` table: one row per qualifying country."""
    deals = deals if deals is not None else pd.DataFrame()
    company_investors = company_investors if company_investors is not None else pd.DataFrame()
    investors = investors if investors is not None else pd.DataFrame()
    deal_investors = deal_investors if deal_investors is not None else pd.DataFrame()

    european = s6._european_set(firm)
    countries = qualifying_countries(firm, min_country_n)

    # Compute one slice per country and reuse it across all headline functions.
    slices = {c: _country_slice(c, firm, deals, company_investors, deal_investors)
              for c in countries}

    tables: dict[str, pd.DataFrame] = {}
    for name, fn in BY_COUNTRY_TABLES:
        rows = []
        for c in countries:
            row = fn(slices[c], investors, european)
            row = {"country": c, **row}
            row["low_n_flag"] = int(row.get("n_green", 0) < config.LOW_N_FLAG)
            rows.append(row)
        df = pd.DataFrame(rows)
        # country first; low_n_flag before the trio; trio last.
        trio = ["n_green", "n_others", "n_startups"]
        lead = ["country"]
        middle = [c for c in df.columns if c not in lead + trio + ["low_n_flag"]]
        df = df[lead + middle + ["low_n_flag"] + trio]
        tables[name] = df.sort_values("n_startups", ascending=False).reset_index(drop=True)
    return tables
