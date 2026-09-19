"""Step 5b build logic: the fixed five-year horizon tables.

Everything is descriptive and firm-relative. Each eligible firm (founding year
2016-2020, so its window [year_founded, year_founded+5] is fully observable by
the 2026-07-07 extract) is observed over its own first five post-founding years.
A deal is in-window iff year_founded <= deal_year <= year_founded + 5; deals
dated before founding are impossible (flagged, counted, excluded). Access uses
the eligible population as denominator; timing and capital use only the firms
that actually have the relevant in-window event, and disclosed amounts are never
zero-filled. Medians are primary. Every table ends with the uniform
n_green / n_others / n_startups trio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config


@dataclass
class Step5bResult:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    caption: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, object] = field(default_factory=dict)
    firm_panel: pd.DataFrame = field(default_factory=pd.DataFrame)
    firm_audit: pd.DataFrame = field(default_factory=pd.DataFrame)


# --------------------------------------------------------------------------
# Small statistics helpers (mirrors step5_funding.build)
# --------------------------------------------------------------------------
def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    green = df[df["green"] == 1]
    other = df[df["green"] != 1]
    return green, other


def _median(series: pd.Series) -> float:
    s = _num(series).dropna()
    return round(float(s.median()), config.DECIMALS) if len(s) else float("nan")


def _quantile(series: pd.Series, q: float) -> float:
    s = _num(series).dropna()
    return round(float(s.quantile(q)), config.DECIMALS) if len(s) else float("nan")


def _pp(green_share: float, other_share: float) -> float:
    if pd.isna(green_share) or pd.isna(other_share):
        return float("nan")
    return round((green_share - other_share) * 100, config.DECIMALS_PP)


def _diff(green_val: float, other_val: float) -> float:
    if pd.isna(green_val) or pd.isna(other_val):
        return float("nan")
    return round(green_val - other_val, config.DECIMALS)


def _stage_sort(values) -> list:
    """Order stage_group values by STAGE_GROUP_ORDER; unknowns appended after."""
    order = {name: i for i, name in enumerate(config.STAGE_GROUP_ORDER)}
    present = [v for v in values if pd.notna(v)]
    return sorted(set(present), key=lambda v: order.get(v, len(order)))


# --------------------------------------------------------------------------
# Eligibility + firm-relative window construction
# --------------------------------------------------------------------------
def eligible_firms(firm: pd.DataFrame) -> pd.DataFrame:
    """Headline eligible set: founding year 2016-2020 inclusive.

    A firm-relative five-year window is only complete when year_founded + 5 is
    already observed at the 2026-07-07 extract (year_founded <= 2020), and the
    population's 10-year floor gives year_founded >= 2016.
    """
    yf = _num(firm["year_founded"])
    mask = (yf >= config.ELIGIBLE_MIN_FOUNDED) & (yf <= config.ELIGIBLE_MAX_FOUNDED)
    keep = [c for c in ("company_id", "green", "year_founded",
                        "green_signal_group", "cohort") if c in firm.columns]
    out = firm.loc[mask, keep].copy()
    out["year_founded"] = _num(out["year_founded"]).astype("Int64")
    return out.reset_index(drop=True)


def prepare_window(
    firm: pd.DataFrame, deals: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """Return (eligible firms, in-window deals with green + rel, diagnostics).

    ``rel`` is deal_year - year_founded. In-window deals satisfy
    0 <= rel <= WINDOW_YEARS. Deals with rel < 0 are impossible (excluded and
    counted). Deals with rel > WINDOW_YEARS are past the horizon (excluded).
    """
    elig = eligible_firms(firm)
    diag: dict[str, float] = {
        "n_firms_total": int(len(firm)),
        "n_eligible": int(len(elig)),
        "n_excluded_ineligible": int(len(firm) - len(elig)),
    }

    if deals is None or deals.empty or elig.empty:
        empty = pd.DataFrame(
            columns=["company_id", "green", "year_founded", "deal_id",
                     "deal_date", "deal_year", "rel", "stage_group",
                     "deal_size", "size_is_actual"]
        )
        diag.update({
            "n_deals_eligible_firms": 0,
            "n_impossible_deals": 0,
            "n_impossible_firms": 0,
            "n_after_horizon_deals": 0,
            "n_in_window_deals": 0,
        })
        return elig, empty, diag

    cols = ["company_id", "deal_id", "deal_date", "stage_group",
            "deal_size", "size_is_actual"]
    d = deals[[c for c in cols if c in deals.columns]].copy()
    d["deal_date"] = pd.to_datetime(d["deal_date"], errors="coerce")
    d["deal_year"] = d["deal_date"].dt.year

    d = d.merge(
        elig[["company_id", "green", "year_founded"]], on="company_id", how="inner"
    )
    diag["n_deals_eligible_firms"] = int(len(d))

    rel = _num(d["deal_year"]) - _num(d["year_founded"])
    d["rel"] = rel

    impossible = d[rel < 0]
    after = d[rel > config.WINDOW_YEARS]
    in_window = d[(rel >= 0) & (rel <= config.WINDOW_YEARS)].copy()
    in_window["rel"] = _num(in_window["rel"]).astype("Int64")

    diag.update({
        "n_impossible_deals": int(len(impossible)),
        "n_impossible_firms": int(impossible["company_id"].nunique()),
        "n_after_horizon_deals": int(len(after)),
        "n_in_window_deals": int(len(in_window)),
        "max_rel_in_window": (
            int(_num(in_window["rel"]).max()) if len(in_window) else 0
        ),
    })
    return elig, in_window, diag


def _firm_stage_flags(elig: pd.DataFrame, in_window: pd.DataFrame) -> pd.DataFrame:
    """One row per eligible firm with 0/1 in-window access flags."""
    base = elig[["company_id", "green"]].copy()
    if in_window.empty:
        for col in ("any_financing", "any_vc", "any_grant", "any_accelerator"):
            base[col] = 0
        return base

    iw = in_window
    fin = iw.groupby("company_id").size().rename("n_iw")
    vc = (
        iw[iw["stage_group"].isin(config.VC_STAGE_GROUPS)]
        .groupby("company_id").size().rename("n_vc")
    )
    grant = (
        iw[iw["stage_group"] == config.GRANT_STAGE_GROUP]
        .groupby("company_id").size().rename("n_grant")
    )
    acc = (
        iw[iw["stage_group"] == config.ACCELERATOR_STAGE_GROUP]
        .groupby("company_id").size().rename("n_acc")
    )
    base = base.join(fin, on="company_id").join(vc, on="company_id")
    base = base.join(grant, on="company_id").join(acc, on="company_id")
    base["any_financing"] = (base["n_iw"].fillna(0) > 0).astype(int)
    base["any_vc"] = (base["n_vc"].fillna(0) > 0).astype(int)
    base["any_grant"] = (base["n_grant"].fillna(0) > 0).astype(int)
    base["any_accelerator"] = (base["n_acc"].fillna(0) > 0).astype(int)
    return base[["company_id", "green", "any_financing", "any_vc",
                 "any_grant", "any_accelerator"]]


# --------------------------------------------------------------------------
# T_first5_access: extensive margin within the window (denominator = eligible)
# --------------------------------------------------------------------------
def build_access(elig: pd.DataFrame, in_window: pd.DataFrame) -> pd.DataFrame:
    flags = _firm_stage_flags(elig, in_window)
    g, o = _split(flags)
    rows = []
    for label, col in (
        ("any_financing", "any_financing"),
        ("any_vc", "any_vc"),
        ("any_grant", "any_grant"),
        ("any_accelerator", "any_accelerator"),
    ):
        g_hit = (g[col] == 1)
        o_hit = (o[col] == 1)
        gs = float(g_hit.mean()) if len(g) else float("nan")
        os_ = float(o_hit.mean()) if len(o) else float("nan")
        gn = int(g_hit.sum())
        on = int(o_hit.sum())
        rows.append({
            "financing_type": label,
            "green_pct": round(gs, config.DECIMALS),
            "other_pct": round(os_, config.DECIMALS),
            "pp_difference": _pp(gs, os_),
            "n_green": gn,
            "n_others": on,
            "n_startups": gn + on,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# T_first5_timing: years to first in-window event (over firms with the event)
# --------------------------------------------------------------------------
def _first_rel(in_window: pd.DataFrame, mask: pd.Series | None) -> pd.DataFrame:
    """Per-firm minimum rel (years to first event); optional stage mask."""
    iw = in_window if mask is None else in_window[mask]
    if iw.empty:
        return pd.DataFrame(columns=["company_id", "green", "rel"])
    grp = iw.groupby("company_id").agg(
        green=("green", "first"), rel=("rel", "min")
    ).reset_index()
    return grp


def build_timing(in_window: pd.DataFrame) -> pd.DataFrame:
    measures = [
        ("years_to_first_financing", None),
        ("years_to_first_vc",
         in_window["stage_group"].isin(config.VC_STAGE_GROUPS)
         if not in_window.empty else None),
        ("years_to_first_grant",
         (in_window["stage_group"] == config.GRANT_STAGE_GROUP)
         if not in_window.empty else None),
    ]
    rows = []
    for label, mask in measures:
        grp = _first_rel(in_window, mask)
        g, o = _split(grp)
        g_med, o_med = _median(g["rel"]), _median(o["rel"])
        rows.append({
            "measure": label,
            "green_median": g_med,
            "green_q25": _quantile(g["rel"], 0.25),
            "green_q75": _quantile(g["rel"], 0.75),
            "other_median": o_med,
            "other_q25": _quantile(o["rel"], 0.25),
            "other_q75": _quantile(o["rel"], 0.75),
            "difference": _diff(g_med, o_med),
            "n_green": int(len(g)),
            "n_others": int(len(o)),
            "n_startups": int(len(g) + len(o)),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# T_first5_capital: per-firm sum of disclosed in-window deal_size (never zeroed)
# --------------------------------------------------------------------------
def build_capital(elig: pd.DataFrame, in_window: pd.DataFrame) -> pd.DataFrame:
    rows = []
    g_all, o_all = _split(elig)
    # global observed trio (firms with >=1 disclosed in-window deal)
    if in_window.empty:
        disclosed = in_window.copy()
    else:
        disclosed = in_window[_num(in_window["deal_size"]).notna()].copy()

    def _group_stats(group_deals: pd.DataFrame, label: str) -> dict:
        iw = group_deals
        disc = iw[_num(iw["deal_size"]).notna()] if not iw.empty else iw
        n_financed = int(iw["company_id"].nunique()) if not iw.empty else 0
        n_deals_iw = int(len(iw))
        n_deals_disc = int(len(disc))
        if not disc.empty:
            per_firm = disc.groupby("company_id")["deal_size"].apply(
                lambda s: _num(s).sum()
            )
        else:
            per_firm = pd.Series(dtype=float)
        n_observed = int(len(per_firm))
        firm_cov = (
            round(n_observed / n_financed, config.DECIMALS) if n_financed else float("nan")
        )
        deal_cov = (
            round(n_deals_disc / n_deals_iw, config.DECIMALS) if n_deals_iw else float("nan")
        )
        return {
            "group": label,
            "sum_median": _median(per_firm),
            "sum_q25": _quantile(per_firm, 0.25),
            "sum_q75": _quantile(per_firm, 0.75),
            "n_firms_observed": n_observed,
            "n_firms_financed_window": n_financed,
            "firm_coverage": firm_cov,
            "deal_coverage": deal_cov,
        }

    if in_window.empty:
        g_iw = o_iw = in_window
    else:
        g_iw = in_window[in_window["green"] == 1]
        o_iw = in_window[in_window["green"] != 1]

    g_stats = _group_stats(g_iw, config.GREEN_LABEL)
    o_stats = _group_stats(o_iw, config.OTHER_LABEL)
    n_green_obs = g_stats["n_firms_observed"]
    n_other_obs = o_stats["n_firms_observed"]
    for stats in (g_stats, o_stats):
        stats.update({
            "n_green": n_green_obs,
            "n_others": n_other_obs,
            "n_startups": n_green_obs + n_other_obs,
        })
        rows.append(stats)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# T_first5_first_channel: first in-window deal per firm (stage + backing)
# --------------------------------------------------------------------------
def _first_in_window_deal(in_window: pd.DataFrame) -> pd.DataFrame:
    """Earliest in-window deal per firm; stable tie-break on deal_id."""
    if in_window.empty:
        return pd.DataFrame(
            columns=["company_id", "green", "deal_id", "stage_group"]
        )
    iw = in_window.sort_values(
        ["company_id", "deal_date", "deal_id"], kind="mergesort"
    )
    first = iw.groupby("company_id", as_index=False).first()
    return first[["company_id", "green", "deal_id", "stage_group"]]


def _deal_backing(
    deal_investors: pd.DataFrame, investors: pd.DataFrame
) -> pd.DataFrame:
    """Per deal_id: has_public / has_private flags from investor_type_grp."""
    if (deal_investors is None or deal_investors.empty
            or investors is None or investors.empty):
        return pd.DataFrame(columns=["deal_id", "has_public", "has_private"])
    di = deal_investors[["deal_id", "investor_id"]].copy()
    inv = investors[["investor_id", "investor_type_grp"]].copy()
    di = di.merge(inv, on="investor_id", how="left")
    di["is_public"] = di["investor_type_grp"].isin(config.PUBLIC_INVESTOR_GRPS)
    di["is_private"] = di["investor_type_grp"].isin(config.PRIVATE_INVESTOR_GRPS)
    agg = di.groupby("deal_id").agg(
        has_public=("is_public", "any"), has_private=("is_private", "any")
    ).reset_index()
    return agg


def _backing_category(has_public: bool, has_private: bool) -> str:
    if has_public and has_private:
        return "public_and_private"
    if has_public:
        return "public_only"
    if has_private:
        return "private_only"
    return "other_or_unknown"


def build_first_channel(
    in_window: pd.DataFrame,
    deal_investors: pd.DataFrame,
    investors: pd.DataFrame,
) -> pd.DataFrame:
    first = _first_in_window_deal(in_window)
    rows = []

    # --- first_stage: composition of the first in-window deal's stage_group ---
    g, o = _split(first)
    ng, no = int(len(g)), int(len(o))
    stages = _stage_sort(first["stage_group"].dropna().unique()) if len(first) else []
    for stage in stages:
        g_hit = (g["stage_group"] == stage)
        o_hit = (o["stage_group"] == stage)
        gs = float(g_hit.mean()) if ng else float("nan")
        os_ = float(o_hit.mean()) if no else float("nan")
        gn, on = int(g_hit.sum()), int(o_hit.sum())
        rows.append({
            "metric": "first_stage",
            "category": stage,
            "green_pct": round(gs, config.DECIMALS),
            "other_pct": round(os_, config.DECIMALS),
            "pp_difference": _pp(gs, os_),
            "n_green": gn,
            "n_others": on,
            "n_startups": gn + on,
        })

    # --- first_backing: investor-type mix of the first in-window deal ---
    backing = _deal_backing(deal_investors, investors)
    fb = first.merge(backing, on="deal_id", how="left")
    fb["has_public"] = fb["has_public"].fillna(False)
    fb["has_private"] = fb["has_private"].fillna(False)
    fb["backing"] = [
        _backing_category(bool(p), bool(v))
        for p, v in zip(fb["has_public"], fb["has_private"])
    ]
    gb, ob = _split(fb)
    for cat in ("public_and_private", "public_only",
                "private_only", "other_or_unknown"):
        g_hit = (gb["backing"] == cat)
        o_hit = (ob["backing"] == cat)
        gs = float(g_hit.mean()) if len(gb) else float("nan")
        os_ = float(o_hit.mean()) if len(ob) else float("nan")
        gn, on = int(g_hit.sum()), int(o_hit.sum())
        rows.append({
            "metric": "first_backing",
            "category": cat,
            "green_pct": round(gs, config.DECIMALS),
            "other_pct": round(os_, config.DECIMALS),
            "pp_difference": _pp(gs, os_),
            "n_green": gn,
            "n_others": on,
            "n_startups": gn + on,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# first5_analysis: canonical one-row-per-eligible-firm five-year dataset
# --------------------------------------------------------------------------
def _lag_series(in_window: pd.DataFrame, mask: pd.Series | None) -> pd.Series:
    """Per-company minimum in-window ``rel`` (years to first event).

    Returns a float Series indexed by ``company_id``; firms with no such
    in-window event are simply absent (never zero-filled -- the caller's join
    leaves them NaN).
    """
    grp = _first_rel(in_window, mask)
    if not len(grp):
        return pd.Series(dtype=float, name="rel")
    return grp.set_index("company_id")["rel"].astype(float)


def build_firm_panel(
    elig: pd.DataFrame, in_window: pd.DataFrame, firm: pd.DataFrame
) -> pd.DataFrame:
    """Canonical five-year firm-level analysis dataset: one row per eligible firm.

    Carries every ``_5yr`` variable needed by downstream common-horizon
    regressions (step13_regression) plus the audit fields
    (``eligible_first5``, ``window_start``, ``window_end``). Timing lags and
    ``disclosed_capital_5yr`` stay NaN when the underlying event/amount is
    unobserved in-window -- missing is never converted to zero.
    """
    extra_cols = [c for c in ("hq_country", "primary_industry_group") if c in firm.columns]
    firm_extra = (
        firm[["company_id", *extra_cols]].drop_duplicates("company_id").set_index("company_id")
    )
    panel = elig.join(firm_extra, on="company_id")

    # --- access flags (denominator = eligible; 0 when no in-window deal) ---
    flags = _firm_stage_flags(elig, in_window).set_index("company_id").rename(columns={
        "any_financing": "any_financing_5yr",
        "any_vc": "any_vc_5yr",
        "any_grant": "any_grant_5yr",
        "any_accelerator": "any_accelerator_5yr",
    })
    flag_cols = ["any_financing_5yr", "any_vc_5yr", "any_grant_5yr", "any_accelerator_5yr"]
    panel = panel.join(flags[flag_cols], on="company_id")
    for col in flag_cols:
        panel[col] = panel[col].fillna(0).astype(int)

    has_deals = in_window is not None and len(in_window) > 0

    # --- deal counts ---------------------------------------------------
    if has_deals:
        n_deals = in_window.groupby("company_id").size()
        disc_iw = in_window[_num(in_window["deal_size"]).notna()]
        n_deals_disc = disc_iw.groupby("company_id").size()
    else:
        n_deals = pd.Series(dtype=int)
        n_deals_disc = pd.Series(dtype=int)
    panel = panel.join(n_deals.rename("n_deals_5yr"), on="company_id")
    panel = panel.join(n_deals_disc.rename("n_deals_with_disclosed_size_5yr"), on="company_id")
    panel["n_deals_5yr"] = panel["n_deals_5yr"].fillna(0).astype(int)
    panel["n_deals_with_disclosed_size_5yr"] = (
        panel["n_deals_with_disclosed_size_5yr"].fillna(0).astype(int)
    )

    # --- timing lags (NaN when the event never occurs in-window) -------
    vc_mask = in_window["stage_group"].isin(config.VC_STAGE_GROUPS) if has_deals else None
    grant_mask = (in_window["stage_group"] == config.GRANT_STAGE_GROUP) if has_deals else None
    panel = panel.join(_lag_series(in_window, None).rename("first_financing_lag_5yr"), on="company_id")
    panel = panel.join(_lag_series(in_window, vc_mask).rename("first_vc_lag_5yr"), on="company_id")
    panel = panel.join(_lag_series(in_window, grant_mask).rename("first_grant_lag_5yr"), on="company_id")

    # --- capital (disclosed in-window amounts only; never zero-filled) --
    if has_deals:
        disc = in_window[_num(in_window["deal_size"]).notna()].copy()
        disc["deal_size"] = _num(disc["deal_size"])
        cap = disc.groupby("company_id")["deal_size"].sum()
    else:
        cap = pd.Series(dtype=float)
    panel = panel.join(cap.rename("disclosed_capital_5yr"), on="company_id")
    panel["has_disclosed_capital_5yr"] = panel["disclosed_capital_5yr"].notna().astype(int)

    # --- audit fields: eligibility flag + explicit window bounds -------
    panel["eligible_first5"] = 1
    panel["window_start"] = _num(panel["year_founded"]).astype("Int64")
    panel["window_end"] = (_num(panel["year_founded"]) + config.WINDOW_YEARS).astype("Int64")

    cols = [
        "company_id", "green", "year_founded", "cohort", "hq_country",
        "primary_industry_group",
        "any_financing_5yr", "any_vc_5yr", "any_grant_5yr", "any_accelerator_5yr",
        "n_deals_5yr", "n_deals_with_disclosed_size_5yr",
        "first_financing_lag_5yr", "first_vc_lag_5yr", "first_grant_lag_5yr",
        "disclosed_capital_5yr", "has_disclosed_capital_5yr",
        "eligible_first5", "window_start", "window_end",
    ]
    cols = [c for c in cols if c in panel.columns]
    return panel[cols].reset_index(drop=True)


def build_firm_audit(
    panel: pd.DataFrame, diag: dict, access: pd.DataFrame
) -> pd.DataFrame:
    """Reconciliation audit for ``first5_analysis``: totals, window integrity,
    excluded pre-founding deals, and exact flag reconciliation to
    ``T_first5_access.csv``.
    """
    g, o = _split(panel)
    access_idx = access.set_index("financing_type") if len(access) else pd.DataFrame()
    rows: list[dict] = [
        {"check": "n_eligible_total", "value": int(len(panel)), "expected": int(diag.get("n_eligible", 0)), "pass": len(panel) == int(diag.get("n_eligible", 0))},
        {"check": "n_eligible_green", "value": int(len(g)), "expected": None, "pass": True},
        {"check": "n_eligible_other", "value": int(len(o)), "expected": None, "pass": True},
        {"check": "max_window_rel_years_leq_5", "value": int(diag.get("max_rel_in_window", 0)), "expected": config.WINDOW_YEARS, "pass": int(diag.get("max_rel_in_window", 0)) <= config.WINDOW_YEARS},
        {"check": "n_impossible_deals_excluded_before_founding", "value": int(diag.get("n_impossible_deals", 0)), "expected": None, "pass": True},
        {"check": "n_impossible_firms_with_pre_founding_deal", "value": int(diag.get("n_impossible_firms", 0)), "expected": None, "pass": True},
        {"check": "deal_year_never_exceeds_year_founded_plus_5", "value": int(diag.get("n_after_horizon_deals", 0)), "expected": None, "pass": True},
    ]

    flag_map = {
        "any_financing_5yr": "any_financing", "any_vc_5yr": "any_vc",
        "any_grant_5yr": "any_grant", "any_accelerator_5yr": "any_accelerator",
    }
    for panel_col, access_key in flag_map.items():
        pg = int((g[panel_col] == 1).sum())
        po = int((o[panel_col] == 1).sum())
        if access_key in access_idx.index:
            ag = int(access_idx.loc[access_key, "n_green"])
            ao = int(access_idx.loc[access_key, "n_others"])
        else:
            ag = ao = None
        rows.append({
            "check": f"reconcile_{panel_col}_n_green_to_{config.OUT_ACCESS}",
            "value": pg, "expected": ag, "pass": (ag is not None and pg == ag),
        })
        rows.append({
            "check": f"reconcile_{panel_col}_n_others_to_{config.OUT_ACCESS}",
            "value": po, "expected": ao, "pass": (ao is not None and po == ao),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Captions
# --------------------------------------------------------------------------
def build_captions(elig: pd.DataFrame, diag: dict, result: Step5bResult) -> pd.DataFrame:
    g, o = _split(elig)
    n_elig, n_g, n_o = int(len(elig)), int(len(g)), int(len(o))
    cap = result.caption

    cap[config.OUT_ACCESS] = (
        f"Extensive margin within each firm's first five post-founding years. "
        f"Denominator = eligible firms ({config.ELIGIBILITY_RULE}); "
        f"total eligible={n_elig} (green={n_g}, other={n_o}). n_green / n_others "
        f"count firms carrying the flag; every share reports its n."
    )
    cap[config.OUT_TIMING] = (
        f"Years to the first in-window event = deal_year - year_founded, over the "
        f"eligible firms that have that event in-window (median primary, IQR shown). "
        f"Total eligible={n_elig} (green={n_g}, other={n_o})."
    )
    cap[config.OUT_CAPITAL] = (
        f"Per-firm sum of disclosed in-window deal_size (missing size never "
        f"zero-filled), over firms with >=1 disclosed in-window deal. "
        f"firm_coverage = observed / financed-in-window; deal_coverage = disclosed "
        f"/ all in-window deals. Total eligible={n_elig} (green={n_g}, other={n_o})."
    )
    cap[config.OUT_FIRST_CHANNEL] = (
        f"First in-window deal per firm (earliest in-window deal_date, deal_id "
        f"tie-break). first_stage: stage_group composition; first_backing uses "
        f"PUBLIC={sorted(config.PUBLIC_INVESTOR_GRPS)} / "
        f"PRIVATE={sorted(config.PRIVATE_INVESTOR_GRPS)}. Denominator = firms with a "
        f"first in-window deal. Total eligible={n_elig} (green={n_g}, other={n_o})."
    )
    cap[config.FIRM_PANEL] = (
        f"Canonical five-year firm-level analysis dataset: exactly one row per "
        f"eligible firm ({config.ELIGIBILITY_RULE}); total eligible={n_elig} "
        f"(green={n_g}, other={n_o}). Carries company_id, green, year_founded, "
        f"cohort, hq_country, primary_industry_group, the four any_*_5yr access "
        f"flags, n_deals_5yr, n_deals_with_disclosed_size_5yr, the three "
        f"first_*_lag_5yr timing lags, disclosed_capital_5yr, "
        f"has_disclosed_capital_5yr, eligible_first5=1, and window_start/"
        f"window_end. Missing lags/amounts stay NaN (never zero-filled); this is "
        f"the single input step13_regression uses for every common-horizon "
        f"regression."
    )
    cap[config.FIRM_AUDIT] = (
        f"Reconciliation audit for {config.FIRM_PANEL}: total eligible, window "
        f"integrity (max in-window rel <= {config.WINDOW_YEARS}), pre-founding "
        f"deals excluded and counted, and each any_*_5yr flag's n_green/n_others "
        f"reconciled exactly to {config.OUT_ACCESS}.csv. See the 'pass' column "
        f"for a per-check PASS/FAIL."
    )
    cap["_interpretation"] = (
        "This standardises the financing observation horizon within the existing "
        "2026 baseline sample. It does not address the separate cross-sectional "
        "survivor-selection issue; the two are distinct."
    )
    cap["_diagnostics"] = (
        f"impossible in-window deals excluded (deal_year<year_founded): "
        f"{int(diag.get('n_impossible_deals', 0))} across "
        f"{int(diag.get('n_impossible_firms', 0))} firms; deals after the horizon "
        f"excluded: {int(diag.get('n_after_horizon_deals', 0))}; "
        f"in-window deals: {int(diag.get('n_in_window_deals', 0))}."
    )
    rows = [{"output": k, "caption": v} for k, v in cap.items()]
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Figure
# --------------------------------------------------------------------------
def build_figure(access: pd.DataFrame, output_dir: Path) -> Path | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - environment-dependent
        print(f"[step5b] matplotlib unavailable, skipping figure: {exc}")
        return None

    labels = list(access["financing_type"])
    green = [v * 100 for v in access["green_pct"]]
    other = [v * 100 for v in access["other_pct"]]
    x = range(len(labels))
    w = 0.38
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.bar([i - w / 2 for i in x], green, width=w,
           label=config.GREEN_LABEL, color="#2e7d32")
    ax.bar([i + w / 2 for i in x], other, width=w,
           label=config.OTHER_LABEL, color="#9e9e9e")
    ax.set_ylabel("Share of eligible firms (%)")
    ax.set_title("Access to financing in the first five post-founding years")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = Path(output_dir) / f"{config.FIGURE_ACCESS}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def build_all(
    firm: pd.DataFrame,
    deals: pd.DataFrame,
    deal_investors: pd.DataFrame,
    investors: pd.DataFrame,
) -> Step5bResult:
    result = Step5bResult()
    elig, in_window, diag = prepare_window(firm, deals)
    result.diagnostics = diag

    result.tables[config.OUT_ACCESS] = build_access(elig, in_window)
    result.tables[config.OUT_TIMING] = build_timing(in_window)
    result.tables[config.OUT_CAPITAL] = build_capital(elig, in_window)
    result.tables[config.OUT_FIRST_CHANNEL] = build_first_channel(
        in_window, deal_investors, investors
    )
    result.firm_panel = build_firm_panel(elig, in_window, firm)
    result.firm_audit = build_firm_audit(
        result.firm_panel, diag, result.tables[config.OUT_ACCESS]
    )
    result.diagnostics["_elig"] = elig  # stashed for captions/acceptance
    result.diagnostics["_in_window"] = in_window
    return result


def write_outputs(result: Step5bResult, output_dir: Path | None = None) -> Path:
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    for name, df in result.tables.items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"[step5b] wrote {path}  ({len(df)} rows)")

    if len(result.firm_panel):
        panel_path = out / f"{config.FIRM_PANEL}.parquet"
        result.firm_panel.to_parquet(panel_path, index=False)
        print(f"[step5b] wrote {panel_path}  ({len(result.firm_panel)} rows)")

    if len(result.firm_audit):
        audit_path = out / f"{config.FIRM_AUDIT}.csv"
        result.firm_audit.to_csv(audit_path, index=False)
        print(f"[step5b] wrote {audit_path}  ({len(result.firm_audit)} rows)")

    elig = result.diagnostics.get("_elig")
    if elig is not None:
        cap_df = build_captions(elig, result.diagnostics, result)
        cap_path = out / f"{config.CAPTIONS_FILE}.csv"
        cap_df.to_csv(cap_path, index=False)
        print(f"[step5b] wrote {cap_path}  ({len(cap_df)} rows)")

    fig_path = build_figure(result.tables[config.OUT_ACCESS], out)
    if fig_path is not None:
        print(f"[step5b] wrote {fig_path}")
    return out


# --------------------------------------------------------------------------
# Acceptance report (printed by run.py)
# --------------------------------------------------------------------------
def acceptance_report(result: Step5bResult) -> list[str]:
    lines: list[str] = []
    diag = result.diagnostics
    elig = diag.get("_elig")
    in_window = diag.get("_in_window")

    # C1: no in-window deal exceeds the horizon.
    max_rel = int(diag.get("max_rel_in_window", 0))
    ok1 = max_rel <= config.WINDOW_YEARS
    lines.append(
        f"[C1] max(deal_year - year_founded) in-window = {max_rel} "
        f"(<= {config.WINDOW_YEARS}): {'PASS' if ok1 else 'FAIL'}"
    )

    # C2: every headline firm has a complete window (founding 2016-2020).
    if elig is not None and len(elig):
        yf = _num(elig["year_founded"])
        in_range = bool(
            ((yf >= config.ELIGIBLE_MIN_FOUNDED)
             & (yf <= config.ELIGIBLE_MAX_FOUNDED)).all()
        )
    else:
        in_range = True
    lines.append(
        f"[C2] all eligible year_founded in "
        f"[{config.ELIGIBLE_MIN_FOUNDED}, {config.ELIGIBLE_MAX_FOUNDED}]: "
        f"{'PASS' if in_range else 'FAIL'}; eligible={int(diag.get('n_eligible', 0))}, "
        f"excluded (missing/other founding year)={int(diag.get('n_excluded_ineligible', 0))}"
    )

    # C3: impossible observations counted and confirmed excluded.
    n_imp = int(diag.get("n_impossible_deals", 0))
    imp_absent = True
    if in_window is not None and len(in_window):
        imp_absent = bool((_num(in_window["rel"]) >= 0).all())
    lines.append(
        f"[C3] impossible deals (deal_year<year_founded) = {n_imp} across "
        f"{int(diag.get('n_impossible_firms', 0))} firms; none present in tables: "
        f"{'PASS' if imp_absent else 'FAIL'}"
    )

    # C4: no collision with Step 5 output names.
    produced = set(result.tables.keys()) | {
        config.CAPTIONS_FILE, config.FIGURE_ACCESS,
        config.FIRM_PANEL, config.FIRM_AUDIT,
    }
    collision = produced & config.STEP5_PROTECTED_NAMES
    only_first5 = all(
        n.startswith("T_first5_")
        or n in {config.CAPTIONS_FILE, config.FIGURE_ACCESS, config.FIRM_PANEL}
        for n in produced
    )
    ok4 = (not collision) and only_first5
    lines.append(
        f"[C4] outputs {sorted(produced)} disjoint from Step 5 names and all "
        f"first5-scoped: {'PASS' if ok4 else 'FAIL'}"
        + (f"  COLLISION={sorted(collision)}" if collision else "")
    )

    # C5: reconciliation across every table + access ceiling.
    recon_ok = True
    for name, df in result.tables.items():
        if {"n_green", "n_others", "n_startups"} <= set(df.columns):
            bad = df[df["n_green"] + df["n_others"] != df["n_startups"]]
            if len(bad):
                recon_ok = False
                lines.append(f"    [C5] {name}: {len(bad)} rows fail n_green+n_others==n_startups")
    n_elig = int(diag.get("n_eligible", 0))
    access = result.tables.get(config.OUT_ACCESS)
    ceil_ok = True
    if access is not None and len(access):
        af = access[access["financing_type"] == "any_financing"]
        if len(af):
            ceil_ok = int(af.iloc[0]["n_startups"]) <= n_elig
    lines.append(
        f"[C5] per-row n_green+n_others==n_startups: {'PASS' if recon_ok else 'FAIL'}; "
        f"access any_financing n_startups <= eligible ({n_elig}): "
        f"{'PASS' if ceil_ok else 'FAIL'}"
    )

    # C6: first5_analysis panel is one row per eligible firm and its access
    # flags reconcile exactly to T_first5_access.csv (audited in firm_audit).
    panel = result.firm_panel
    panel_ok = len(panel) == n_elig
    audit = result.firm_audit
    audit_ok = bool(len(audit)) and bool(audit["pass"].all())
    lines.append(
        f"[C6] first5_analysis rows == eligible ({n_elig}): "
        f"{'PASS' if panel_ok else 'FAIL'}; T_first5_firm_audit all checks pass: "
        f"{'PASS' if audit_ok else 'FAIL'}"
        + ("" if audit_ok else
           f"  FAILED={audit.loc[~audit['pass'], 'check'].tolist() if len(audit) else []}")
    )
    return lines
