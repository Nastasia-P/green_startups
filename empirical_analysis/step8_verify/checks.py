"""Step 8 structural checks.

Each function returns a list of check rows (dicts). A row is
`{check_id, category, description, expected, observed, status, detail}` with `status`
in PASS / WARN / FAIL (STALE is a WARN sub-status used by the stale-file guard). The
checks run over the in-memory re-run tables (`tables`) and the Step 1/2 source frames.
"""

from __future__ import annotations

import pandas as pd

from . import config

TRIO = ["n_green", "n_others", "n_startups"]


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _row(check_id, category, description, expected, observed, status, detail="") -> dict:
    return {
        "check_id": check_id,
        "category": category,
        "description": description,
        "expected": expected,
        "observed": observed,
        "status": status,
        "detail": detail,
    }


def _status_eq(observed, expected) -> str:
    return "PASS" if observed == expected else "FAIL"


# --------------------------------------------------------------------------
# population and subsamples (5.1)
# --------------------------------------------------------------------------
def check_population(firm: pd.DataFrame) -> list[dict]:
    rows = []
    n = len(firm)
    n_green = int((firm["green"] == 1).sum())
    n_other = n - n_green
    rows.append(_row("population.firm_rows", "population",
                     "firm table row count", config.POP_TOTAL, n,
                     _status_eq(n, config.POP_TOTAL)))
    rows.append(_row("population.green", "population",
                     "green firms", config.GREEN_TOTAL, n_green,
                     _status_eq(n_green, config.GREEN_TOTAL)))
    rows.append(_row("population.other", "population",
                     "other European firms", config.OTHER_TOTAL, n_other,
                     _status_eq(n_other, config.OTHER_TOTAL)))

    if "green_stage" in firm.columns:
        # green_stage is categorical (e.g. vertical / phrase / token); check the
        # multiset of category counts, not a specific 1/2/3 encoding.
        vc = firm.loc[firm["green"] == 1, "green_stage"].value_counts(dropna=True)
        counts = tuple(int(v) for v in vc.tolist())
        total = int(vc.sum())
        ok = (total == config.GREEN_TOTAL
              and sorted(counts) == sorted(config.GREEN_STAGES))
        rows.append(_row("population.green_by_stage", "population",
                         "green_stage category counts sum to green total",
                         f"{sorted(config.GREEN_STAGES)} (sum {config.GREEN_TOTAL})",
                         f"{sorted(counts)} (sum {total})",
                         "PASS" if ok else "FAIL"))
    else:
        rows.append(_row("population.green_by_stage", "population",
                         "green_stage 1/2/3 present", "green_stage column",
                         "absent", "WARN", "green_stage not in firm table"))

    fin = int((_num(firm.get("financed")) == 1).sum())
    rows.append(_row("population.financed", "population", "financed subsample",
                     config.FINANCED_TOTAL, fin, _status_eq(fin, config.FINANCED_TOTAL)))
    inv = int((_num(firm.get(config.N_INVESTORS_FIELD)).fillna(0) >= 1).sum())
    rows.append(_row("population.invested", "population", "INVESTED subsample",
                     config.INVESTED_TOTAL, inv, _status_eq(inv, config.INVESTED_TOTAL)))
    gv = int(((_num(firm.get("any_grant")) == 1) & (_num(firm.get("any_vc")) == 1)).sum())
    rows.append(_row("population.grant_and_vc", "population", "grant-and-VC firms",
                     config.GRANT_AND_VC_TOTAL, gv,
                     _status_eq(gv, config.GRANT_AND_VC_TOTAL)))
    return rows


# --------------------------------------------------------------------------
# trio identity (5.1)
# --------------------------------------------------------------------------
def check_trio_identity(tables: dict[str, pd.DataFrame]) -> list[dict]:
    rows = []
    for name, df in tables.items():
        if not set(TRIO).issubset(df.columns) or df.empty:
            continue
        g, o, s = (_num(df["n_green"]), _num(df["n_others"]), _num(df["n_startups"]))
        bad = (g + o) != s
        n_bad = int(bad.sum())
        status = "PASS" if n_bad == 0 else "FAIL"
        detail = "" if n_bad == 0 else f"{n_bad} row(s) where n_green+n_others != n_startups"
        rows.append(_row(f"trio_identity.{name}", "trio_identity",
                         f"{name}: n_green + n_others == n_startups", "0 violations",
                         f"{n_bad} violations", status, detail))
    return rows


# --------------------------------------------------------------------------
# shares sum to 1 (5.2)
# --------------------------------------------------------------------------
def _sum_close(series: pd.Series, target: float = 1.0) -> bool:
    s = _num(series).dropna()
    return len(s) > 0 and abs(float(s.sum()) - target) <= config.SHARE_TOL


def check_shares_sum(tables: dict[str, pd.DataFrame]) -> list[dict]:
    rows = []

    def _pair(name, gcol, ocol, cid):
        df = tables.get(name)
        if df is None or df.empty:
            return
        for role, col in (("green", gcol), ("other", ocol)):
            if col in df.columns:
                ok = _sum_close(df[col])
                total = round(float(_num(df[col]).sum()), 4)
                rows.append(_row(f"shares_sum.{cid}_{role}", "shares_sum",
                                 f"{name}: {col} sums to 1", "1.0", total,
                                 "PASS" if ok else "FAIL"))

    _pair("T4_14_first_financing_type", "green_pct", "other_pct", "t4_14")
    _pair("T4_15_stage_composition", "green_pct", "other_pct", "t4_15")
    _pair("T4_18_investor_type_distribution", "green_pct_relations",
          "other_pct_relations", "t4_18")
    _pair("T4_23_investor_origin", "green_pct_relations", "other_pct_relations", "t4_23")

    # T4.28 per-country origin shares.
    t28 = tables.get("T4_28_investor_origin_by_country")
    if t28 is not None and not t28.empty:
        for role, cols in (
            ("green", ["green_domestic", "green_eu_cross_border", "green_non_european"]),
            ("other", ["other_domestic", "other_eu_cross_border", "other_non_european"]),
        ):
            if all(c in t28.columns for c in cols):
                vals = t28[cols].apply(_num)
                # Countries with no known-origin relations of this cohort have NaN
                # shares (no data); they cannot and need not sum to 1 -> skip them.
                has_data = vals.notna().any(axis=1)
                s = vals.sum(axis=1)
                bad = int((has_data & (s.sub(1).abs() > config.SHARE_TOL)).sum())
                rows.append(_row(f"shares_sum.t4_28_{role}", "shares_sum",
                                 f"T4.28: {role} origin shares sum to 1 per country "
                                 "(rows with data)",
                                 "0 off-by-one rows", f"{bad} rows",
                                 "PASS" if bad == 0 else "FAIL"))

    # T4.29 amount identity and share range.
    t29 = tables.get("T4_29_country_funding_by_type")
    if t29 is not None and not t29.empty:
        ident = (_num(t29["green_amount"]) + _num(t29["other_amount"])
                 - _num(t29["total_amount"])).abs()
        bad_id = int((ident > 1e-2).sum())
        rows.append(_row("shares_sum.t4_29_identity", "shares_sum",
                         "T4.29: green_amount + other_amount == total_amount",
                         "0 violations", f"{bad_id} violations",
                         "PASS" if bad_id == 0 else "FAIL"))
        sh = _num(t29["green_amount_share"]).dropna()
        bad_rng = int(((sh < 0) | (sh > 1)).sum())
        rows.append(_row("shares_sum.t4_29_range", "shares_sum",
                         "T4.29: green_amount_share in [0,1]", "0 out of range",
                         f"{bad_rng} out of range", "PASS" if bad_rng == 0 else "FAIL"))
    return rows


# --------------------------------------------------------------------------
# medians inside quartiles (5.2)
# --------------------------------------------------------------------------
def check_median_in_iqr(tables: dict[str, pd.DataFrame]) -> list[dict]:
    rows = []
    specs = [
        ("T4_10_total_raised_by_cohort",
         [("green_q25", "green_median", "green_q75"),
          ("other_q25", "other_median", "other_q75")]),
        ("T4_11_first_financing_size_by_stage",
         [("green_q25", "green_median", "green_q75"),
          ("other_q25", "other_median", "other_q75")]),
        ("T4_13_time_to_financing",
         [("green_q25", "green_median", "green_q75"),
          ("other_q25", "other_median", "other_q75")]),
    ]
    for name, triples in specs:
        df = tables.get(name)
        if df is None or df.empty:
            continue
        bad = 0
        for q25, med, q75 in triples:
            if not all(c in df.columns for c in (q25, med, q75)):
                continue
            a, m, b = _num(df[q25]), _num(df[med]), _num(df[q75])
            mask = a.notna() & m.notna() & b.notna()
            bad += int((mask & ~((a <= m) & (m <= b))).sum())
        rows.append(_row(f"median_in_iqr.{name}", "median_in_iqr",
                         f"{name}: q25 <= median <= q75", "0 violations",
                         f"{bad} violations", "PASS" if bad == 0 else "FAIL"))
    return rows


# --------------------------------------------------------------------------
# low-n flag integrity (5.5)
# --------------------------------------------------------------------------
def check_low_n_flag(tables: dict[str, pd.DataFrame]) -> list[dict]:
    rows = []
    for name, df in tables.items():
        if df.empty or "low_n_flag" not in df.columns or "n_green" not in df.columns:
            continue
        expected_flag = (_num(df["n_green"]) < config.LOW_N_FLAG).astype(int)
        got = _num(df["low_n_flag"]).astype(int)
        bad = int((expected_flag != got).sum())
        rows.append(_row(f"low_n_flag.{name}", "low_n_flag",
                         f"{name}: (n_green < {config.LOW_N_FLAG}) == low_n_flag",
                         "0 mismatches", f"{bad} mismatches",
                         "PASS" if bad == 0 else "FAIL"))
    # Headline / country tables must carry a low_n_flag column.
    for name in ("T4_06_country_specialisation", "T4_26_green_share_firms_vs_capital",
                 "T4_28_investor_origin_by_country", "T4_29_country_funding_by_type"):
        df = tables.get(name)
        if df is None:
            continue
        present = "low_n_flag" in df.columns
        rows.append(_row(f"low_n_flag.present.{name}", "low_n_flag",
                         f"{name} carries a low_n_flag column", "present",
                         "present" if present else "absent",
                         "PASS" if present else "FAIL"))
    return rows


# --------------------------------------------------------------------------
# source totals (5.1 / 5.4)
# --------------------------------------------------------------------------
def check_source_totals(
    tables: dict[str, pd.DataFrame],
    firm: pd.DataFrame,
    deals: pd.DataFrame,
    company_investors: pd.DataFrame,
) -> list[dict]:
    rows = []

    t15 = tables.get("T4_15_stage_composition")
    if t15 is not None and not t15.empty:
        got = int(_num(t15["n_startups"]).sum())
        exp = len(deals)
        rows.append(_row("source_totals.t4_15_deals", "source_totals",
                         "T4.15 n_startups sum == deals_clean rows", exp, got,
                         _status_eq(got, exp)))

    t18 = tables.get("T4_18_investor_type_distribution")
    if t18 is not None and not t18.empty and not company_investors.empty:
        inv_ids = set(firm.loc[_num(firm[config.N_INVESTORS_FIELD]).fillna(0) >= 1,
                               "company_id"].astype("string"))
        ci = company_investors.copy()
        ci["company_id"] = ci["company_id"].astype("string")
        exp = int(ci["company_id"].isin(inv_ids).sum())
        got = int(_num(t18["n_startups"]).sum())
        # T4.18 tallies relations by investor_type_grp, so relations to investors
        # with no known type are dropped; the table total must not exceed all links.
        ok = got <= exp
        rows.append(_row("source_totals.t4_18_relations", "source_totals",
                         "T4.18 relation total <= links on INVESTED firms "
                         "(untyped investor relations dropped)", f"<= {exp}", got,
                         "PASS" if ok else "FAIL",
                         "" if ok else "typed relations exceed total INVESTED links"))

    t29 = tables.get("T4_29_country_funding_by_type")
    if t29 is not None and not t29.empty and "deal_size" in deals.columns:
        exp = round(float(_num(deals["deal_size"]).dropna().sum()), 2)
        got = round(float(_num(t29["total_amount"]).sum()), 2)
        # Deals for firms with no known hq_country are dropped from T4.29, so the
        # table total can be <= the raw disclosed total; a small positive slack
        # absorbs per-row 2dp rounding accumulated over hundreds of country x stage
        # cells.
        ok = got <= exp + 1.0
        rows.append(_row("source_totals.t4_29_amount", "source_totals",
                         "T4.29 total_amount sum <= disclosed deal_size sum", exp, got,
                         "PASS" if ok else "FAIL",
                         "" if ok else "table total exceeds source disclosed capital"))

    t6 = tables.get("T4_06_country_specialisation")
    if t6 is not None and not t6.empty:
        got_s = int(_num(t6["n_startups"]).sum())
        got_g = int(_num(t6["n_green"]).sum())
        rows.append(_row("source_totals.t4_06_startups", "source_totals",
                         "T4.6 n_startups sum == population", config.POP_TOTAL, got_s,
                         _status_eq(got_s, config.POP_TOTAL)))
        rows.append(_row("source_totals.t4_06_green", "source_totals",
                         "T4.6 n_green sum == green total", config.GREEN_TOTAL, got_g,
                         _status_eq(got_g, config.GREEN_TOTAL)))

    t26 = tables.get("T4_26_green_share_firms_vs_capital")
    if t26 is not None and not t26.empty:
        got_s = int(_num(t26["n_startups"]).sum())
        rows.append(_row("source_totals.t4_26_startups", "source_totals",
                         "T4.26 n_startups sum == population", config.POP_TOTAL, got_s,
                         _status_eq(got_s, config.POP_TOTAL)))
        recomputed = (_num(t26["n_green"]) / _num(t26["n_startups"])).round(4)
        bad = int((recomputed != _num(t26["green_firm_share"])).sum())
        rows.append(_row("source_totals.t4_26_firm_share", "source_totals",
                         "T4.26 green_firm_share == round(n_green/n_startups, 4)",
                         "0 mismatches", f"{bad} mismatches",
                         "PASS" if bad == 0 else "FAIL"))
    return rows


# --------------------------------------------------------------------------
# double counting (5.7 / A3)
# --------------------------------------------------------------------------
def check_double_counting(
    tables: dict[str, pd.DataFrame],
    firm: pd.DataFrame,
    company_investors: pd.DataFrame,
) -> list[dict]:
    rows = []
    inv_firm = int((_num(firm.get(config.N_INVESTORS_FIELD)).fillna(0) >= 1).sum())

    t18 = tables.get("T4_18_investor_type_distribution")
    if t18 is not None and not t18.empty:
        rel_total = int(_num(t18["n_startups"]).sum())
        ok = rel_total >= inv_firm
        rows.append(_row("double_counting.relations_ge_firms", "double_counting",
                         "T4.18 relation total >= INVESTED firm count (grain kept)",
                         f">= {inv_firm}", rel_total, "PASS" if ok else "FAIL",
                         "" if ok else "relations fewer than firms suggests a grain mix-up"))

    if not company_investors.empty:
        ci = company_investors.copy()
        ci["company_id"] = ci["company_id"].astype("string")
        inv_ids = set(firm.loc[_num(firm[config.N_INVESTORS_FIELD]).fillna(0) >= 1,
                               "company_id"].astype("string"))
        ci_firms = int(ci.loc[ci["company_id"].isin(inv_ids), "company_id"].nunique())
        ok = ci_firms == inv_firm
        rows.append(_row("double_counting.invested_firm_grain", "double_counting",
                         "INVESTED firm count == distinct linked firms in relations",
                         inv_firm, ci_firms, "PASS" if ok else "WARN",
                         "" if ok else "n_investors_lifetime provenance differs from "
                         "company_investors links (firm-grain, not a double count)"))
    return rows


# --------------------------------------------------------------------------
# stale-file guard
# --------------------------------------------------------------------------
def _frames_match(disk: pd.DataFrame, rerun: pd.DataFrame) -> tuple[bool, str]:
    if len(disk) != len(rerun):
        return False, f"row count {len(disk)} vs {len(rerun)}"
    missing = [c for c in rerun.columns if c not in disk.columns]
    if missing:
        return False, f"columns missing on disk: {missing[:3]}"
    for c in rerun.columns:
        a = disk[c].reset_index(drop=True)
        b = rerun[c].reset_index(drop=True)
        an, bn = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
        if bool(an.notna().any()) or bool(bn.notna().any()):
            both_nan = an.isna() & bn.isna()
            mism = (~both_nan) & (((an - bn).abs() > config.STALE_TOL)
                                  | (an.isna() != bn.isna()))
            if bool(mism.any()):
                i = int(mism.idxmax())
                return False, f"col {c} row {i}: {a.iloc[i]} vs {b.iloc[i]}"
        else:
            sa = a.astype("string").fillna("")
            sb = b.astype("string").fillna("")
            mism = sa != sb
            if bool(mism.any()):
                i = int(mism.idxmax())
                return False, f"col {c} row {i}: {a.iloc[i]!r} vs {b.iloc[i]!r}"
    return True, ""


def check_stale_files(tables: dict[str, pd.DataFrame], read_csv) -> list[dict]:
    rows = []
    present = stale = missing = 0
    for name, rerun in tables.items():
        disk = read_csv(name)
        if disk is None:
            missing += 1
            continue
        present += 1
        ok, detail = _frames_match(disk, rerun)
        if ok:
            rows.append(_row(f"stale_files.{name}", "stale_files",
                             f"{name}.csv matches the re-run", "match", "match", "PASS"))
        else:
            stale += 1
            rows.append(_row(f"stale_files.{name}", "stale_files",
                             f"{name}.csv differs from the re-run", "match",
                             "differs", "WARN", detail))
    rows.append(_row("stale_files.summary", "stale_files",
                     "on-disk outputs compared to the re-run",
                     "all present files match",
                     f"{present} present, {stale} stale, {missing} missing",
                     "WARN" if stale else "PASS"))
    return rows


def run_all_checks(
    tables: dict[str, pd.DataFrame],
    firm: pd.DataFrame,
    deals: pd.DataFrame,
    company_investors: pd.DataFrame,
    read_csv=None,
) -> list[dict]:
    rows: list[dict] = []
    rows += check_population(firm)
    rows += check_trio_identity(tables)
    rows += check_shares_sum(tables)
    rows += check_median_in_iqr(tables)
    rows += check_low_n_flag(tables)
    rows += check_source_totals(tables, firm, deals, company_investors)
    rows += check_double_counting(tables, firm, company_investors)
    if read_csv is not None:
        rows += check_stale_files(tables, read_csv)
    return rows
