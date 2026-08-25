"""Step 6 build logic: the investor and grant tables.

Everything is descriptive. The master population is the INVESTED subsample (firms
with at least one recorded investor, rule: `n_investors_lifetime >= 1`), because
green firms are far better documented and a full-population composition comparison
would measure coverage. Investor-type and origin questions are answered at the
relation grain (firm x investor); syndication at the deal grain; grant -> VC
sequencing uses deal dates and is descriptive only. Medians are primary (rule N6);
accelerator is never folded into VC (rule N8). Every table ends with the uniform
n_green / n_others / n_startups trio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config


@dataclass
class Step6Result:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    caption: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Small statistics helpers
# --------------------------------------------------------------------------
def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    green = df[df["green"] == 1]
    other = df[df["green"] != 1]
    return green, other


def _invested(firm: pd.DataFrame) -> pd.DataFrame:
    n = _num(firm[config.N_INVESTORS_FIELD]).fillna(0)
    return firm[n >= config.INVESTED_MIN]


def _median(series: pd.Series) -> float:
    s = _num(series).dropna()
    return round(float(s.median()), 2) if len(s) else float("nan")


def _pp(green_share: float, other_share: float) -> float:
    if pd.isna(green_share) or pd.isna(other_share):
        return float("nan")
    return round((green_share - other_share) * 100, 1)


def _ratio(green: float, other: float) -> float:
    if pd.isna(green) or pd.isna(other) or other == 0:
        return float("nan")
    return round(green / other, 3)


def _share(mask: pd.Series, base: pd.DataFrame) -> float:
    return round(float(mask.mean()), 4) if len(base) else float("nan")


def _is_stage1(df: pd.DataFrame) -> pd.Series:
    return (df["green"] == 1) & (df["green_signal_group"] == config.STAGE1_LABEL)


def _is_stage23(df: pd.DataFrame) -> pd.Series:
    return (df["green"] == 1) & (df["green_signal_group"] == config.STAGE23_LABEL)


def _type_sort(values) -> list:
    """Order investor_type_grp by INVESTOR_TYPE_ORDER; unknowns appended, the
    Other/Unclassified label forced last."""
    order = {name: i for i, name in enumerate(config.INVESTOR_TYPE_ORDER)}
    present = sorted({v for v in values if pd.notna(v)},
                     key=lambda v: order.get(v, len(order)))
    if config.UNCLASSIFIED_LABEL in present:
        present = [v for v in present if v != config.UNCLASSIFIED_LABEL]
        present.append(config.UNCLASSIFIED_LABEL)
    return present


def _stage_sort(values) -> list:
    order = {name: i for i, name in enumerate(config.STAGE_GROUP_ORDER)}
    present = [v for v in values if pd.notna(v)]
    return sorted(set(present), key=lambda v: order.get(v, len(order)))


def _firm_attr(firm: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    attr = firm.copy()
    attr["company_id"] = attr["company_id"].astype("string")
    keep = [c for c in cols if c in attr.columns]
    return attr.set_index("company_id")[keep]


# --------------------------------------------------------------------------
# Join helpers: relation grain (firm x investor) and deal grain
# --------------------------------------------------------------------------
def relation_frame(
    firm: pd.DataFrame,
    company_investors: pd.DataFrame,
    investors: pd.DataFrame,
) -> pd.DataFrame:
    """One row per firm x investor link, restricted to INVESTED firms, carrying
    green / green_signal_group / hq_country and investor type_grp / country."""
    cols = ["company_id", "investor_id", "investor_type_grp", "investor_country",
            "green", "green_signal_group", "hq_country"]
    if company_investors.empty:
        return pd.DataFrame(columns=cols)
    rel = company_investors[["company_id", "investor_id"]].copy()
    rel["company_id"] = rel["company_id"].astype("string")
    rel["investor_id"] = rel["investor_id"].astype("string")

    attr = _firm_attr(firm, ["green", "green_signal_group", "hq_country",
                             config.N_INVESTORS_FIELD])
    rel = rel.join(attr, on="company_id")
    # INVESTED firms only.
    n = _num(rel[config.N_INVESTORS_FIELD]).fillna(0)
    rel = rel[n >= config.INVESTED_MIN].copy()
    rel["green"] = rel["green"].fillna(0).astype(int)

    if not investors.empty:
        inv = investors.copy()
        inv["investor_id"] = inv["investor_id"].astype("string")
        inv_attr = inv.set_index("investor_id")[["investor_type_grp", "investor_country"]]
        rel = rel.join(inv_attr, on="investor_id")
    else:
        rel["investor_type_grp"] = pd.NA
        rel["investor_country"] = pd.NA
    for c in cols:
        if c not in rel.columns:
            rel[c] = pd.NA
    return rel[cols].reset_index(drop=True)


def _deals_with_green(firm: pd.DataFrame, deals: pd.DataFrame) -> pd.DataFrame:
    d = deals.copy()
    d["company_id"] = d["company_id"].astype("string")
    green_by = _firm_attr(firm, ["green"])["green"]
    d["green"] = d["company_id"].map(green_by).fillna(0).astype(int)
    return d


# --------------------------------------------------------------------------
# T4.18 investor type distribution (relation grain over INVESTED, rule R1)
# --------------------------------------------------------------------------
def build_investor_type_distribution(
    firm: pd.DataFrame,
    company_investors: pd.DataFrame,
    investors: pd.DataFrame,
) -> pd.DataFrame:
    cols = [
        "investor_type_grp", "green_n_relations", "green_pct_relations",
        "green_pct_firms", "other_n_relations", "other_pct_relations",
        "other_pct_firms", "pp_difference", "green_pct_firms_stage1",
        "green_pct_firms_stage2plus3", "n_green", "n_others", "n_startups",
    ]
    rel = relation_frame(firm, company_investors, investors)
    if rel.empty:
        return pd.DataFrame(columns=cols)

    invested = _invested(firm)
    g_inv, o_inv = _split(invested)
    n_g_firms, n_o_firms = len(g_inv), len(o_inv)
    s1_firms = invested[_is_stage1(invested)]
    s23_firms = invested[_is_stage23(invested)]
    g_ids = set(g_inv["company_id"].astype("string"))
    o_ids = set(o_inv["company_id"].astype("string"))
    s1_ids = set(s1_firms["company_id"].astype("string"))
    s23_ids = set(s23_firms["company_id"].astype("string"))

    g_rel, o_rel = _split(rel)
    n_g_rel, n_o_rel = len(g_rel), len(o_rel)

    rows = []
    for t in _type_sort(rel["investor_type_grp"].dropna().unique()):
        rel_t = rel[rel["investor_type_grp"] == t]
        gn = int((g_rel["investor_type_grp"] == t).sum())
        on = int((o_rel["investor_type_grp"] == t).sum())
        ids_t = set(rel_t["company_id"].astype("string"))
        g_firms_t = len(g_ids & ids_t)
        o_firms_t = len(o_ids & ids_t)
        s1_firms_t = len(s1_ids & ids_t)
        s23_firms_t = len(s23_ids & ids_t)
        g_pf = g_firms_t / n_g_firms if n_g_firms else float("nan")
        o_pf = o_firms_t / n_o_firms if n_o_firms else float("nan")
        rows.append(
            {
                "investor_type_grp": t,
                "green_n_relations": gn,
                "green_pct_relations": round(gn / n_g_rel, 4) if n_g_rel else float("nan"),
                "green_pct_firms": round(g_pf, 4),
                "other_n_relations": on,
                "other_pct_relations": round(on / n_o_rel, 4) if n_o_rel else float("nan"),
                "other_pct_firms": round(o_pf, 4),
                "pp_difference": _pp(g_pf, o_pf),
                "green_pct_firms_stage1": (round(s1_firms_t / len(s1_ids), 4)
                                           if s1_ids else float("nan")),
                "green_pct_firms_stage2plus3": (round(s23_firms_t / len(s23_ids), 4)
                                                if s23_ids else float("nan")),
                "n_green": gn,
                "n_others": on,
                "n_startups": gn + on,
            }
        )
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# T4.19 company-level investor flags (firm grain over INVESTED)
# --------------------------------------------------------------------------
def build_investor_flags(firm: pd.DataFrame) -> pd.DataFrame:
    cols = ["flag", "green_stat", "other_stat", "difference",
            "n_green", "n_others", "n_startups"]
    invested = _invested(firm)
    g, o = _split(invested)
    n_g, n_o = len(g), len(o)
    rows = []
    for flag in config.INVESTOR_FLAGS:
        if flag not in invested.columns:
            continue
        g_hit = (_num(g[flag]) == 1)
        o_hit = (_num(o[flag]) == 1)
        gs = _share(g_hit, g)
        os_ = _share(o_hit, o)
        rows.append(
            {
                "flag": flag,
                "green_stat": gs,
                "other_stat": os_,
                "difference": _pp(gs, os_),
                "n_green": n_g,
                "n_others": n_o,
                "n_startups": n_g + n_o,
            }
        )
    # Median distinct investors (rule N6).
    g_med = _median(g[config.N_INVESTORS_FIELD])
    o_med = _median(o[config.N_INVESTORS_FIELD])
    rows.append(
        {
            "flag": "median_n_investors",
            "green_stat": g_med,
            "other_stat": o_med,
            "difference": (round(g_med - o_med, 2)
                           if pd.notna(g_med) and pd.notna(o_med) else float("nan")),
            "n_green": n_g,
            "n_others": n_o,
            "n_startups": n_g + n_o,
        }
    )
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# T4.21 public and private capital (firm grain over INVESTED, rule R1)
# --------------------------------------------------------------------------
def build_public_private(firm: pd.DataFrame) -> pd.DataFrame:
    cols = ["measure", "green_pct", "other_pct", "pp_difference",
            "green_pct_stage1", "green_pct_stage2plus3",
            "n_green", "n_others", "n_startups"]
    invested = _invested(firm)
    g, o = _split(invested)
    s1 = invested[_is_stage1(invested)]
    s23 = invested[_is_stage23(invested)]
    n_g, n_o = len(g), len(o)

    rows = []
    shares = {}
    for measure, col in (
        ("lifetime_combination", config.PUBLIC_PRIVATE_LIFETIME),
        ("same_deal_coinvestment", config.PUBLIC_PRIVATE_SAME_DEAL),
    ):
        if col not in invested.columns:
            continue
        g_hit = (_num(g[col]) == 1)
        o_hit = (_num(o[col]) == 1)
        gs = _share(g_hit, g)
        os_ = _share(o_hit, o)
        shares[measure] = (gs, os_)
        rows.append(
            {
                "measure": measure,
                "green_pct": gs,
                "other_pct": os_,
                "pp_difference": _pp(gs, os_),
                "green_pct_stage1": _share((_num(s1[col]) == 1), s1),
                "green_pct_stage2plus3": _share((_num(s23[col]) == 1), s23),
                "n_green": int(g_hit.sum()),
                "n_others": int(o_hit.sum()),
                "n_startups": int(g_hit.sum()) + int(o_hit.sum()),
            }
        )
    if "lifetime_combination" in shares and "same_deal_coinvestment" in shares:
        g_life, o_life = shares["lifetime_combination"]
        g_same, o_same = shares["same_deal_coinvestment"]
        rows.append(
            {
                "measure": "ratio_same_deal_to_lifetime",
                "green_pct": _ratio(g_same, g_life),
                "other_pct": _ratio(o_same, o_life),
                "pp_difference": float("nan"),
                "green_pct_stage1": float("nan"),
                "green_pct_stage2plus3": float("nan"),
                "n_green": n_g,
                "n_others": n_o,
                "n_startups": n_g + n_o,
            }
        )
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# T4.22 grant -> VC sequencing (firms with both; descriptive only)
# --------------------------------------------------------------------------
def _grant_vc_frame(firm: pd.DataFrame, deals: pd.DataFrame) -> pd.DataFrame:
    """Per firm: earliest grant date and earliest VC date, with green."""
    d = deals[["company_id", "deal_date", "stage_group"]].copy()
    d["company_id"] = d["company_id"].astype("string")
    d["deal_date"] = pd.to_datetime(d["deal_date"], errors="coerce")
    grant = (
        d[d["stage_group"] == config.GRANT_STAGE_GROUP]
        .groupby("company_id")["deal_date"].min().rename("grant_date")
    )
    vc = (
        d[d["stage_group"].isin(config.VC_STAGE_GROUPS)]
        .groupby("company_id")["deal_date"].min().rename("vc_date")
    )
    per = pd.concat([grant, vc], axis=1).reset_index()
    green_by = _firm_attr(firm, ["green"])["green"]
    per["green"] = per["company_id"].map(green_by).fillna(0).astype(int)
    return per


def _gv_row(measure, g_stat, o_stat, n_g, n_o) -> dict:
    diff = (round(g_stat - o_stat, 2)
            if pd.notna(g_stat) and pd.notna(o_stat) else float("nan"))
    return {
        "measure": measure,
        "green_stat": g_stat,
        "other_stat": o_stat,
        "difference": diff,
        "n_green": int(n_g),
        "n_others": int(n_o),
        "n_startups": int(n_g) + int(n_o),
    }


def build_grant_to_vc(firm: pd.DataFrame, deals: pd.DataFrame) -> pd.DataFrame:
    cols = ["measure", "green_stat", "other_stat", "difference",
            "n_green", "n_others", "n_startups"]
    if deals.empty:
        return pd.DataFrame(columns=cols)
    per = _grant_vc_frame(firm, deals)
    both = per[per["grant_date"].notna() & per["vc_date"].notna()].copy()
    both["preceded"] = both["grant_date"] < both["vc_date"]
    both["months"] = (both["vc_date"] - both["grant_date"]).dt.days / 30.44

    gb, ob = _split(both)
    rows = []
    rows.append(_gv_row("n_firms_grant_and_vc", len(gb), len(ob), len(gb), len(ob)))

    gp = _share(gb["preceded"], gb)
    op = _share(ob["preceded"], ob)
    rows.append(_gv_row("pct_grant_preceded_vc", gp, op, len(gb), len(ob)))

    g_pre = gb[gb["preceded"]]
    o_pre = ob[ob["preceded"]]
    rows.append(_gv_row(
        "median_months_grant_to_vc",
        _median(g_pre["months"]), _median(o_pre["months"]),
        len(g_pre), len(o_pre),
    ))

    # % of VC-backed firms (have a VC round) with a grant that preceded first VC.
    vc_backed = per[per["vc_date"].notna()].copy()
    vc_backed["prior_grant"] = (
        vc_backed["grant_date"].notna() & (vc_backed["grant_date"] < vc_backed["vc_date"])
    )
    gv, ov = _split(vc_backed)
    rows.append(_gv_row(
        "pct_vc_backed_with_prior_grant",
        _share(gv["prior_grant"], gv), _share(ov["prior_grant"], ov),
        len(gv), len(ov),
    ))
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# T4.23 investor origin (relation grain over INVESTED, known-country, rule R1)
# --------------------------------------------------------------------------
def _european_set(firm: pd.DataFrame) -> set:
    return set(firm["hq_country"].dropna().astype(str).unique())


def _classify_origin(rel: pd.DataFrame, european: set) -> pd.Series:
    ic = rel["investor_country"].astype("string")
    hq = rel["hq_country"].astype("string")
    is_domestic = ic == hq
    is_european = ic.isin(european)
    origin = pd.Series("non_european", index=rel.index, dtype="object")
    origin = origin.mask(is_european & ~is_domestic, "european_cross_border")
    origin = origin.mask(is_domestic, "domestic")
    return origin


def build_investor_origin(
    firm: pd.DataFrame,
    company_investors: pd.DataFrame,
    investors: pd.DataFrame,
) -> pd.DataFrame:
    cols = [
        "origin", "green_pct_relations", "green_pct_firms",
        "other_pct_relations", "other_pct_firms", "pp_difference",
        "green_pct_firms_stage1", "green_pct_firms_stage2plus3",
        "country_coverage", "n_green", "n_others", "n_startups",
    ]
    rel = relation_frame(firm, company_investors, investors)
    if rel.empty:
        return pd.DataFrame(columns=cols)
    coverage = round(float(rel["investor_country"].notna().mean()), 4)
    known = rel[rel["investor_country"].notna()].copy()
    if known.empty:
        return pd.DataFrame(columns=cols)
    european = _european_set(firm)
    known["origin"] = _classify_origin(known, european)

    invested = _invested(firm)
    g_inv, o_inv = _split(invested)
    n_g_firms, n_o_firms = len(g_inv), len(o_inv)
    s1_ids = set(invested[_is_stage1(invested)]["company_id"].astype("string"))
    s23_ids = set(invested[_is_stage23(invested)]["company_id"].astype("string"))
    g_ids = set(g_inv["company_id"].astype("string"))
    o_ids = set(o_inv["company_id"].astype("string"))

    g_known, o_known = _split(known)
    n_g_rel, n_o_rel = len(g_known), len(o_known)

    order = ["domestic", "european_cross_border", "non_european"]
    rows = []
    for origin in order:
        sub = known[known["origin"] == origin]
        gn = int((g_known["origin"] == origin).sum())
        on = int((o_known["origin"] == origin).sum())
        ids_o = set(sub["company_id"].astype("string"))
        g_pf = len(g_ids & ids_o) / n_g_firms if n_g_firms else float("nan")
        o_pf = len(o_ids & ids_o) / n_o_firms if n_o_firms else float("nan")
        g_pr = gn / n_g_rel if n_g_rel else float("nan")
        o_pr = on / n_o_rel if n_o_rel else float("nan")
        rows.append(
            {
                "origin": origin,
                "green_pct_relations": round(g_pr, 4),
                "green_pct_firms": round(g_pf, 4),
                "other_pct_relations": round(o_pr, 4),
                "other_pct_firms": round(o_pf, 4),
                "pp_difference": _pp(g_pr, o_pr),
                "green_pct_firms_stage1": (round(len(s1_ids & ids_o) / len(s1_ids), 4)
                                           if s1_ids else float("nan")),
                "green_pct_firms_stage2plus3": (round(len(s23_ids & ids_o) / len(s23_ids), 4)
                                                if s23_ids else float("nan")),
                "country_coverage": coverage,
                "n_green": gn,
                "n_others": on,
                "n_startups": gn + on,
            }
        )
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# T4.25 syndication (deal grain, within stage group)
# --------------------------------------------------------------------------
def _lead_by_deal(deal_investors: pd.DataFrame) -> pd.Series:
    """Per deal_id: whether it has at least one identified lead investor."""
    if deal_investors.empty or "is_lead" not in deal_investors.columns:
        return pd.Series(dtype=bool)
    di = deal_investors[["deal_id", "is_lead"]].copy()
    di["deal_id"] = di["deal_id"].astype("string")
    di["has_lead"] = di["is_lead"].astype("string").str.strip().str.lower() == "yes"
    return di.groupby("deal_id")["has_lead"].max()


def build_syndication(
    firm: pd.DataFrame,
    deals: pd.DataFrame,
    deal_investors: pd.DataFrame,
) -> pd.DataFrame:
    cols = ["stage_group", "group", "median_investors", "pct_multi_investor",
            "median_new_investors", "pct_with_lead",
            "n_green", "n_others", "n_startups"]
    if deals.empty:
        return pd.DataFrame(columns=cols)
    d = _deals_with_green(firm, deals)
    d["n_investors"] = _num(d.get("n_investors"))
    d["n_new_investors"] = _num(d.get("n_new_investors"))
    lead = _lead_by_deal(deal_investors)
    if len(lead) and "deal_id" in d.columns:
        d["deal_id"] = d["deal_id"].astype("string")
        d["has_lead"] = d["deal_id"].map(lead).fillna(False).astype(bool)
    else:
        d["has_lead"] = False

    rows = []
    for stage in _stage_sort(d["stage_group"].dropna().unique()):
        stage_all = d[d["stage_group"] == stage]
        g_all, o_all = _split(stage_all)
        n_g, n_o = len(g_all), len(o_all)
        for label, sub in ((config.GREEN_LABEL, g_all), (config.OTHER_LABEL, o_all)):
            rows.append(
                {
                    "stage_group": stage,
                    "group": label,
                    "median_investors": _median(sub["n_investors"]),
                    "pct_multi_investor": _share(
                        (sub["n_investors"] >= config.MULTI_INVESTOR_MIN), sub),
                    "median_new_investors": _median(sub["n_new_investors"]),
                    "pct_with_lead": _share(sub["has_lead"], sub),
                    "n_green": n_g,
                    "n_others": n_o,
                    "n_startups": n_g + n_o,
                }
            )
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# F4.5 investor-type participation figure data (from T4.18)
# --------------------------------------------------------------------------
def build_investor_participation_figure(
    firm: pd.DataFrame, t418: pd.DataFrame
) -> pd.DataFrame:
    cols = ["investor_type_grp", "green_pct_firms", "other_pct_firms",
            "pp_difference", "n_green", "n_others", "n_startups"]
    if t418.empty:
        return pd.DataFrame(columns=cols)
    invested = _invested(firm)
    g_inv, o_inv = _split(invested)
    n_g, n_o = len(g_inv), len(o_inv)
    rows = []
    for _, r in t418.iterrows():
        rows.append(
            {
                "investor_type_grp": r["investor_type_grp"],
                "green_pct_firms": r["green_pct_firms"],
                "other_pct_firms": r["other_pct_firms"],
                "pp_difference": r["pp_difference"],
                "n_green": n_g,
                "n_others": n_o,
                "n_startups": n_g + n_o,
            }
        )
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def build_all(
    firm: pd.DataFrame,
    deals: pd.DataFrame | None = None,
    company_investors: pd.DataFrame | None = None,
    investors: pd.DataFrame | None = None,
    deal_investors: pd.DataFrame | None = None,
) -> Step6Result:
    result = Step6Result()
    deals = deals if deals is not None else pd.DataFrame()
    company_investors = company_investors if company_investors is not None else pd.DataFrame()
    investors = investors if investors is not None else pd.DataFrame()
    deal_investors = deal_investors if deal_investors is not None else pd.DataFrame()

    t418 = build_investor_type_distribution(firm, company_investors, investors)
    result.tables["T4_18_investor_type_distribution"] = t418
    result.tables["T4_19_investor_flags"] = build_investor_flags(firm)
    result.tables["T4_21_public_private"] = build_public_private(firm)
    result.tables["T4_22_grant_to_vc"] = build_grant_to_vc(firm, deals)
    result.tables["T4_23_investor_origin"] = build_investor_origin(
        firm, company_investors, investors)
    result.tables["T4_25_syndication"] = build_syndication(firm, deals, deal_investors)
    result.tables["F4_05_investor_participation"] = build_investor_participation_figure(
        firm, t418)

    result.caption["T4_18_investor_type_distribution"] = (
        "Relation grain: n_green / n_others / n_startups count investor relations, "
        "not firms; green_pct_firms is the firm-with-≥1 view. INVESTED firms only."
    )
    result.caption["T4_19_investor_flags"] = (
        "Firm grain over the INVESTED subsample (firms with >=1 recorded investor). "
        "Share rows report percentage-point differences; the median row reports the "
        "difference in distinct-investor counts (rule N6)."
    )
    result.caption["T4_21_public_private"] = (
        "Lifetime combination (ever both public and private) and same-deal "
        "co-investment (a single deal with both) are reported separately: they are "
        "not the same thing. INVESTED firms only."
    )
    result.caption["T4_22_grant_to_vc"] = (
        "Descriptive sequencing only: a grant preceding VC is an ordering in the "
        "deal record, not evidence of causation. Population: firms with both a grant "
        "and a VC round."
    )
    result.caption["T4_23_investor_origin"] = (
        "Relation grain over known-country relations only (coverage reported on the "
        "table). European = any firm hq_country; domestic = investor country equals "
        "the firm's country."
    )
    result.caption["T4_25_syndication"] = (
        "Deal grain within stage group: n_green / n_others / n_startups count rounds. "
        "Compared within stage because later rounds carry more investors."
    )
    return result


def write_outputs(result: Step6Result, output_dir: Path | None = None) -> Path:
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in result.tables.items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"[step6] wrote {path}  ({len(df)} rows)")
    if result.caption:
        cap = pd.DataFrame(
            [{"output": k, "caption": v} for k, v in result.caption.items()]
        )
        cap.to_csv(out / "captions_step6.csv", index=False)
        print(f"[step6] wrote {out / 'captions_step6.csv'}")
    return out


def acceptance_report(firm: pd.DataFrame, result: Step6Result) -> list[str]:
    lines: list[str] = []

    invested = _invested(firm)
    g_inv, o_inv = _split(invested)
    lines.append(
        f"INVESTED subsample: {len(invested)} (green={len(g_inv)}, other={len(o_inv)}) "
        f"(expected {config.INVESTED_TOTAL})"
    )
    if len(invested) != config.INVESTED_TOTAL:
        lines.append("  WARN: INVESTED count differs from the expected 50,815")

    # T4.19 flags reconcile with firm-column means over INVESTED.
    t19 = result.tables["T4_19_investor_flags"].set_index("flag")
    for flag in config.INVESTOR_FLAGS:
        if flag in t19.index and flag in invested.columns:
            expect = round(float((_num(g_inv[flag]) == 1).mean()), 4) if len(g_inv) else float("nan")
            got = t19.loc[flag, "green_stat"]
            ok = "" if abs(float(got) - expect) < 1e-6 else "  <-- MISMATCH"
            lines.append(f"T4.19 {flag}: green_stat={got} (firm-mean {expect}){ok}")

    # T4.18 relation total and Other/Unclassified share.
    t18 = result.tables["T4_18_investor_type_distribution"]
    if not t18.empty:
        rel_total = int(t18["n_startups"].sum())
        lines.append(f"T4.18 investor relations (INVESTED): {rel_total}")
        unc = t18[t18["investor_type_grp"] == config.UNCLASSIFIED_LABEL]
        if not unc.empty:
            share = int(unc["n_startups"].iloc[0]) / rel_total if rel_total else float("nan")
            warn = "  WARN: >10% unclassified" if share > config.UNCLASSIFIED_WARN_SHARE else ""
            lines.append(f"T4.18 Other/Unclassified relation share: {round(share, 4)}{warn}")

    # T4.22 grant-and-VC population and non-negative months.
    t22 = result.tables["T4_22_grant_to_vc"].set_index("measure")
    if "n_firms_grant_and_vc" in t22.index:
        n_both = int(t22.loc["n_firms_grant_and_vc", "n_startups"])
        lines.append(f"T4.22 firms with grant AND VC: {n_both} (expected {config.GRANT_AND_VC_TOTAL})")
        if n_both != config.GRANT_AND_VC_TOTAL:
            lines.append("  WARN: grant-and-VC count differs from the expected 3,960")
    if "median_months_grant_to_vc" in t22.index:
        r = t22.loc["median_months_grant_to_vc"]
        neg = [v for v in (r["green_stat"], r["other_stat"]) if pd.notna(v) and v < 0]
        lines.append(f"T4.22 median months grant->VC: green={r['green_stat']} other={r['other_stat']}")
        if neg:
            lines.append("  WARN: negative grant->VC months present")

    # T4.23 origin shares sum to 1 within group.
    t23 = result.tables["T4_23_investor_origin"]
    if not t23.empty:
        gsum = round(float(t23["green_pct_relations"].sum()), 3)
        osum = round(float(t23["other_pct_relations"].sum()), 3)
        cov = t23["country_coverage"].iloc[0]
        lines.append(f"T4.23 origin relation shares sum: green={gsum} other={osum} "
                     f"(country coverage {cov})")

    # T4.25 within-stage sanity.
    t25 = result.tables["T4_25_syndication"]
    if not t25.empty:
        lines.append(f"T4.25 rows (stage x group): {len(t25)}; "
                     f"stages={t25['stage_group'].nunique()}")

    return lines
