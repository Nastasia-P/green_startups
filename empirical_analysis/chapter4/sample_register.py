"""Sample-size register for Chapter 4 outputs.

Produces one row per analysis statistic documenting which population was used,
the effective n, and why. Written alongside the analytical tables so every
output carries an auditable sample definition (Output_Register convention:
every table reports its own n).
"""

from __future__ import annotations

import pandas as pd


def _present(series: pd.Series) -> pd.Series:
    s = series
    if s.dtype == object or str(s.dtype) == "string":
        stripped = s.astype("string").str.strip()
        return (stripped.notna() & (stripped != "")).fillna(False).astype(bool)
    return s.notna()


def _split(firm: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    green = firm[firm["green"] == 1]
    other = firm[firm["green"] != 1]
    return green, other


def _counts(df: pd.DataFrame) -> tuple[int, int, int]:
    g = int((df["green"] == 1).sum()) if len(df) else 0
    o = int((df["green"] != 1).sum()) if len(df) else 0
    return len(df), g, o


def _col_nonnull_counts(
    firm: pd.DataFrame, g: pd.DataFrame, o: pd.DataFrame, col: str
) -> tuple[int | None, int | None, int | None]:
    if col not in firm.columns:
        return None, None, None
    ng = int(g[col].notna().sum())
    no = int(o[col].notna().sum())
    return ng + no, ng, no


def _col_mask_counts(
    firm: pd.DataFrame, col: str, value
) -> tuple[int | None, int | None, int | None]:
    if col not in firm.columns:
        return None, None, None
    sub = firm[firm[col] == value]
    return _counts(sub)


def _row(
    *,
    section: str,
    output_id: str,
    output_file: str,
    statistic: str,
    population: str,
    n_total: int | None,
    n_green: int | None,
    n_other: int | None,
    sample_definition: str,
    rationale: str,
    rule_refs: str = "",
    step: str = "",
    status: str = "computed",
) -> dict:
    return {
        "section": section,
        "output_id": output_id,
        "output_file": output_file,
        "statistic": statistic,
        "population": population,
        "n_total": n_total,
        "n_green": n_green,
        "n_other": n_other,
        "sample_definition": sample_definition,
        "rationale": rationale,
        "rule_refs": rule_refs,
        "step": step,
        "status": status,
    }


def build_sample_register(
    firm: pd.DataFrame,
    industries: pd.DataFrame | None = None,
    verticals: pd.DataFrame | None = None,
    deals: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the Chapter 4 sample-size register from the firm table and clean inputs."""
    rows: list[dict] = []
    g, o = _split(firm)
    nt, ng, no = _counts(firm)
    fin = firm[firm["financed"] == 1]
    ft, fg, fo = _counts(fin)

    # --- Master populations ------------------------------------------------
    rows.append(_row(
        section="master", output_id="—", output_file="—", statistic="full_population",
        population="Full", n_total=nt, n_green=ng, n_other=no,
        sample_definition="All firms in company_analysis (one row per firm)",
        rationale="Fixed Chapter 3 study population; denominator for access and geography.",
        rule_refs="N9", step="2", status="computed",
    ))
    rows.append(_row(
        section="master", output_id="—", output_file="—", statistic="financed_subsample",
        population="Financed", n_total=ft, n_green=fg, n_other=fo,
        sample_definition="financed == 1 (>=1 qualifying deal after Step 1 filters F1-F4)",
        rationale="Verified deal-record evidence; required for amount and timing comparisons.",
        rule_refs="N1,N2", step="2", status="computed",
    ))
    rows.append(_row(
        section="master", output_id="—", output_file="—", statistic="not_financed",
        population="Full", n_total=nt - ft, n_green=ng - fg, n_other=no - fo,
        sample_definition="financed == 0 (no qualifying deal record)",
        rationale="Funding unobserved, not zero; retained in full-population access tables.",
        rule_refs="N1,N2", step="2", status="computed",
    ))
    rows.append(_row(
        section="master", output_id="—", output_file="—", statistic="green_only",
        population="Green only", n_total=ng, n_green=ng, n_other=0,
        sample_definition="green == 1",
        rationale="Green subsegment decomposition; not a green-vs-other comparison.",
        step="3", status="computed",
    ))

    # --- 4.0 Coverage ------------------------------------------------------
    rows.append(_row(
        section="4.0", output_id="T4.0", output_file="T4_00_field_completeness.csv",
        statistic="field_completeness", population="Full",
        n_total=nt, n_green=ng, n_other=no,
        sample_definition="Every firm; non-null counts per field by group",
        rationale="Blocking audit: documents differential PitchBook coverage before comparisons.",
        rule_refs="M3", step="T4.0", status="built",
    ))

    # --- 4.1 Firm characteristics (Step 3) ---------------------------------
    emp_g, emp_o = int(_present(g["employees"]).sum()), int(_present(o["employees"]).sum())
    rows.append(_row(
        section="4.1", output_id="T4.1", output_file="T4_01_master_descriptive.csv",
        statistic="n_firms", population="Full",
        n_total=nt, n_green=ng, n_other=no,
        sample_definition="All firms",
        rationale="Headline population count before geography or funding interpretation.",
        step="3", status="built",
    ))
    rows.append(_row(
        section="4.1", output_id="T4.1", output_file="T4_01_master_descriptive.csv",
        statistic="median_age_and_cohort_shares", population="Full",
        n_total=nt, n_green=ng, n_other=no,
        sample_definition="Firms with year_founded / cohort present (100% in current data)",
        rationale="Age and cohort are fully populated derived scalars.",
        step="3", status="built",
    ))
    rows.append(_row(
        section="4.1", output_id="T4.1", output_file="T4_01_master_descriptive.csv",
        statistic="median_employees_and_bands", population="Full",
        n_total=emp_g + emp_o, n_green=emp_g, n_other=emp_o,
        sample_definition="Firms with non-null employees / employee_band",
        rationale="Missing employee count is unknown, not zero; n disclosed per statistic.",
        rule_refs="N6", step="3", status="built",
    ))
    bs_g, bs_o = int(_present(g["business_status"]).sum()), int(_present(o["business_status"]).sum())
    rows.append(_row(
        section="4.1", output_id="T4.1", output_file="T4_01_master_descriptive.csv",
        statistic="share_financed", population="Full",
        n_total=nt, n_green=ng, n_other=no,
        sample_definition="All firms; financed flag defined for every row",
        rationale="Access measure runs on full population by construction.",
        rule_refs="N1,N2", step="3", status="built",
    ))
    rows.append(_row(
        section="4.1", output_id="T4.2", output_file="T4_02_business_status.csv",
        statistic="status_distribution", population="Full",
        n_total=bs_g + bs_o, n_green=bs_g, n_other=bs_o,
        sample_definition="Firms with known business_status only",
        rationale="Percentages require a defined status; missing firms omitted from shares only.",
        step="3", status="built",
    ))
    rows.append(_row(
        section="4.1", output_id="F4.1", output_file="F4_01_green_share_by_cohort.csv",
        statistic="green_share_by_cohort", population="Full",
        n_total=nt, n_green=ng, n_other=no,
        sample_definition="All firms split by founding cohort",
        rationale="Cohort composition of current eligible firms, not a historical time series.",
        step="3", status="built",
    ))

    if industries is not None and not industries.empty:
        ind_g = industries[industries["company_id"].isin(g["company_id"])]["company_id"].nunique()
        ind_o = industries[industries["company_id"].isin(o["company_id"])]["company_id"].nunique()
        rows.append(_row(
            section="4.1", output_id="T4.3", output_file="T4_03_industry_composition.csv",
            statistic="industry_tags", population="Full",
            n_total=ind_g + ind_o, n_green=int(ind_g), n_other=int(ind_o),
            sample_definition="Firms with >=1 row in industries_clean",
            rationale="Multi-tag firms appear in multiple sector rows; percentages can sum >100%.",
            step="3", status="built",
        ))

    if verticals is not None and not verticals.empty:
        vert_g = verticals[verticals["company_id"].isin(g["company_id"])]["company_id"].nunique()
        tr_g = int(g["total_raised"].notna().sum())
        rows.append(_row(
            section="4.1", output_id="T4.4", output_file="T4_04_green_subsegments.csv",
            statistic="vertical_decomposition", population="Green only",
            n_total=int(vert_g), n_green=int(vert_g), n_other=0,
            sample_definition="Green firms with >=1 vertical tag",
            rationale="Decomposes green population; other firms excluded by design.",
            step="3", status="built",
        ))
        rows.append(_row(
            section="4.1", output_id="T4.4", output_file="T4_04_green_subsegments.csv",
            statistic="median_total_raised", population="Green only",
            n_total=tr_g, n_green=tr_g, n_other=0,
            sample_definition="Green firms with non-null total_raised",
            rationale="Descriptive amount within green subsegments; reports its own n.",
            step="3", status="built",
        ))
        rows.append(_row(
            section="4.1", output_id="T4.4", output_file="T4_04_green_subsegments.csv",
            statistic="n_with_funding", population="Green only",
            n_total=fg, n_green=fg, n_other=0,
            sample_definition="Green firms with financed == 1",
            rationale="Access count within each vertical.",
            rule_refs="N2", step="3", status="built",
        ))

    rows.append(_row(
        section="4.1", output_id="T4.5", output_file="T4_05_employment_by_cohort.csv",
        statistic="median_employees_by_cohort", population="Full",
        n_total=emp_g + emp_o, n_green=emp_g, n_other=emp_o,
        sample_definition="Within each cohort: firms with non-null employees",
        rationale="Compare size at comparable age (robustness R2), not across cohorts.",
        rule_refs="R2,N6", step="3", status="built",
    ))
    rows.append(_row(
        section="4.1", output_id="T4.5b", output_file="T4_05b_classification_validation.csv",
        statistic="hand_coded_precision", population="Hand-coded sample",
        n_total=200, n_green=100, n_other=100,
        sample_definition="100 green (stratified by green_stage) + 100 not-identified",
        rationale="Tests classification accuracy; independent of pipeline population.",
        step="manual", status="planned",
    ))

    # --- 4.2 Geography (Step 4) --------------------------------------------
    if "hq_country" in firm.columns:
        cc = firm["hq_country"].value_counts()
        geo_firms = int(cc[cc >= 500].sum()) if len(cc) else 0
        n_countries = int((cc >= 500).sum())
    else:
        geo_firms = None
        n_countries = None
    rows.append(_row(
        section="4.2", output_id="T4.6", output_file="T4_06_country_specialisation.csv",
        statistic="country_lq", population="Full",
        n_total=geo_firms, n_green=None, n_other=None,
        sample_definition=(
            f"Start-ups in countries with >=500 firms ({n_countries} countries)"
            if n_countries is not None else
            "Start-ups in countries with >=500 firms"
        ),
        rationale="Country denominators use the 116,005 population, not PitchBook global universe.",
        rule_refs="N9,D4", step="4", status="planned",
    ))
    rows.append(_row(
        section="4.2", output_id="T4.7", output_file="T4_07_per_capita_crosscheck.csv",
        statistic="startups_per_million", population="Full",
        n_total=geo_firms, n_green=None, n_other=None,
        sample_definition="Same country set as T4.6 + Eurostat populations",
        rationale="Tests whether uneven PitchBook coverage drives LQ rankings.",
        rule_refs="N9", step="4", status="planned",
    ))

    # --- 4.3 Funding access (Step 5) ---------------------------------------
    rows.append(_row(
        section="4.3A", output_id="T4.9", output_file="T4_09_funding_access.csv",
        statistic="any_financing_flags", population="Full",
        n_total=nt, n_green=ng, n_other=no,
        sample_definition="All firms; binary access flags (financed, any_vc, any_grant, ...)",
        rationale="Extensive margin: absence of deal record is the measurement, not zero funding.",
        rule_refs="N1,N2,N8", step="5", status="planned",
    ))

    # --- 4.3 Funding amounts (Step 5) --------------------------------------
    tr_fg = int(fin[fin["green"] == 1]["total_raised"].notna().sum()) if "total_raised" in fin.columns else 0
    tr_fo = int(fin[fin["green"] != 1]["total_raised"].notna().sum()) if "total_raised" in fin.columns else 0
    rows.append(_row(
        section="4.3B", output_id="T4.10", output_file="T4_10_total_raised_by_cohort.csv",
        statistic="total_raised", population="Financed",
        n_total=tr_fg + tr_fo, n_green=tr_fg, n_other=tr_fo,
        sample_definition="Financed firms with non-null total_raised, within founding cohort",
        rationale="Amount comparisons only within financed subsample; cohort controls exposure time.",
        rule_refs="N1,N4,R2", step="5", status="planned",
    ))
    fds, fds_g, fds_o = _col_nonnull_counts(firm, g, o, "first_deal_size")
    rows.append(_row(
        section="4.3B", output_id="T4.11", output_file="T4_11_first_financing_size_by_stage.csv",
        statistic="first_deal_size", population="Financed",
        n_total=fds, n_green=fds_g, n_other=fds_o,
        sample_definition="Financed firms with non-null first_deal_size",
        rationale="Deal size often missing even when a qualifying deal exists.",
        rule_refs="N1", step="5", status="planned",
    ))

    if deals is not None and not deals.empty and "deal_size" in deals.columns:
        dg = deals[deals["company_id"].isin(g["company_id"])]
        do = deals[deals["company_id"].isin(o["company_id"])]
        ds_g = int(dg["deal_size"].notna().sum())
        ds_o = int(do["deal_size"].notna().sum())
        rows.append(_row(
            section="4.3B", output_id="T4.16", output_file="T4_16_median_deal_size_by_stage.csv",
            statistic="deal_size_by_stage", population="Deals with size",
            n_total=ds_g + ds_o, n_green=ds_g, n_other=ds_o,
            sample_definition="Qualifying deals in deals_clean with non-null deal_size",
            rationale="Deal-level grain; one firm may contribute multiple deal rows.",
            rule_refs="N1", step="5", status="planned",
        ))

    # --- 4.3 Timing (Step 5) -----------------------------------------------
    lag_t, lag_g, lag_o = _col_nonnull_counts(firm, g, o, "first_funding_lag")
    rows.append(_row(
        section="4.3C", output_id="T4.13", output_file="T4_13_time_to_financing.csv",
        statistic="first_funding_lag", population="Financed",
        n_total=lag_t, n_green=lag_g, n_other=lag_o,
        sample_definition="Financed firms with valid first_funding_lag (negative lags excluded)",
        rationale="Requires founding year and first deal date; year-only precision.",
        rule_refs="N1,R4", step="5", status="planned",
    ))
    vcl_t, vcl_g, vcl_o = _col_nonnull_counts(firm, g, o, "first_vc_lag")
    rows.append(_row(
        section="4.3C", output_id="T4.13", output_file="T4_13_time_to_financing.csv",
        statistic="first_vc_lag", population="Financed with VC",
        n_total=vcl_t, n_green=vcl_g, n_other=vcl_o,
        sample_definition="Financed firms with at least one VC-stage deal and valid lag",
        rationale="First VC is a distinct measure from first financing of any type.",
        rule_refs="N1", step="5", status="planned",
    ))

    # --- 4.3 Investors (Step 6) --------------------------------------------
    if "n_investors_lifetime" in firm.columns:
        inv = firm[firm["n_investors_lifetime"] > 0]
        it, ig, io = _counts(inv)
    else:
        it = ig = io = None
    rows.append(_row(
        section="4.3E", output_id="T4.18", output_file="T4_18_investor_type_distribution.csv",
        statistic="investor_type_mix", population="Firms with investors",
        n_total=it, n_green=ig, n_other=io,
        sample_definition="n_investors_lifetime >= 1",
        rationale="Investor tables require a company-investor link in PitchBook.",
        step="6", status="planned",
    ))
    if "share_investors_domestic" in firm.columns:
        geo_inv = firm[firm["share_investors_domestic"].notna()]
        gt, gg, go = _counts(geo_inv)
    else:
        gt = gg = go = None
    rows.append(_row(
        section="4.3G", output_id="T4.23", output_file="T4_23_investor_origin.csv",
        statistic="investor_origin_shares", population="Firms with located investors",
        n_total=gt, n_green=gg, n_other=go,
        sample_definition="At least one investor with known country (share_investors_domestic not null)",
        rationale="Origin shares undefined when no investor country is known.",
        step="6", status="planned",
    ))
    if "any_grant" in firm.columns and "any_vc" in firm.columns:
        both = firm[(firm["any_grant"] == 1) & (firm["any_vc"] == 1)]
        bt, bg, bo = _counts(both)
    else:
        bt = bg = bo = None
    rows.append(_row(
        section="4.3F", output_id="T4.22", output_file="T4_22_grant_to_vc.csv",
        statistic="grant_then_vc_sequence", population="Firms with grant and VC",
        n_total=bt, n_green=bg, n_other=bo,
        sample_definition="any_grant == 1 AND any_vc == 1",
        rationale="Sequencing only defined when both event types are observed.",
        step="6", status="planned",
    ))

    out = pd.DataFrame(rows)
    # Stable column order for thesis appendix.
    cols = [
        "section", "output_id", "output_file", "statistic", "population",
        "n_total", "n_green", "n_other", "sample_definition", "rationale",
        "rule_refs", "step", "status",
    ]
    return out[cols]
