"""Smoke tests for Step 1.

The committed sample has almost no overlap of CompanyIDs across tables, so it
proves the pipeline runs and the schemas are right, not that the counts are.
A small synthetic source covers the filter behaviour, which the sample cannot.
"""

from __future__ import annotations

import pandas as pd
import pytest

from empirical_analysis.step1_clean_raw_data import config
from empirical_analysis.step1_clean_raw_data.clean import build_all, write_outputs
from empirical_analysis.step1_clean_raw_data.sources import (
    FixtureSource,
    RawSource,
    load_population_key,
    parse_deal_dates,
)

EXPECTED_TABLES = [
    "population_key",
    "deals_clean",
    "deal_investors_clean",
    "company_investors_clean",
    "investors_clean",
    "industries_clean",
    "verticals_clean",
    "employee_history_clean",
]


class DictSource(RawSource):
    """A RawSource backed by in-memory frames, for filter tests."""

    def __init__(self, tables: dict[str, pd.DataFrame]):
        self._tables = tables

    def table(self, name: str, keep_ids: set[str] | None = None) -> pd.DataFrame:
        df = self._tables.get(name, pd.DataFrame(columns=config.USECOLS.get(name, []))).copy()
        filter_col = config.FILTER_COL.get(name)
        if keep_ids is not None and filter_col and filter_col in df.columns:
            df = df[df[filter_col].isin(keep_ids)]
        return df.reset_index(drop=True)

    def raw_row_count(self, name: str) -> int:
        return len(self._tables.get(name, []))


@pytest.fixture(scope="module")
def population():
    return load_population_key()


def test_pipeline_runs_on_sample_and_has_expected_tables(population):
    result = build_all(FixtureSource(), population)
    assert set(EXPECTED_TABLES) == set(result.tables)
    pop = result.tables["population_key"]
    assert {"company_id", "green", "green_stage", "green_signal_group"} <= set(pop.columns)
    assert pop["company_id"].is_unique


def test_outputs_are_written_as_parquet(tmp_path, population):
    result = build_all(FixtureSource(), population)
    out = write_outputs(result, output_dir=tmp_path)
    for name in EXPECTED_TABLES:
        assert (out / f"{name}.parquet").exists()
    for name in ("deal_types_seen.csv", "investor_types_seen.csv", "cleaning_audit.csv"):
        assert (out / name).exists()
    reloaded = pd.read_parquet(out / "population_key.parquet")
    assert len(reloaded) == len(result.tables["population_key"])


def _synthetic_tables(company_ids: list[str]) -> dict[str, pd.DataFrame]:
    a, b, c = company_ids[:3]
    deals = pd.DataFrame(
        [
            # kept: completed, dated, real financing
            {"CompanyID": a, "DealID": "D1", "DealDate": "01/15/2020", "DealType": "Early Stage VC",
             "DealStatus": "Completed", "DealSize": "10", "DealSizeStatus": "Actual"},
            # dropped by the completed filter
            {"CompanyID": a, "DealID": "D2", "DealDate": "02/15/2021", "DealType": "Seed Round",
             "DealStatus": "Announced/In Progress", "DealSize": "5", "DealSizeStatus": "Estimated"},
            # dropped by the real-financing filter
            {"CompanyID": b, "DealID": "D3", "DealDate": "03/15/2019", "DealType": "IPO",
             "DealStatus": "Completed", "DealSize": "50", "DealSizeStatus": "Actual"},
            # dropped by the date filter (unparseable)
            {"CompanyID": b, "DealID": "D4", "DealDate": "", "DealType": "Grant",
             "DealStatus": "Completed", "DealSize": "1", "DealSizeStatus": "Actual"},
            # kept, and it is this firm's first deal
            {"CompanyID": c, "DealID": "D5", "DealDate": "05/01/2018", "DealType": "Grant",
             "DealStatus": "Completed", "DealSize": "", "DealSizeStatus": "Estimated"},
        ]
    )
    deal_investors = pd.DataFrame(
        [
            {"DealID": "D1", "InvestorID": "I1", "InvestorStatus": "New Investor", "IsLeadInvestor": "Yes"},
            {"DealID": "D1", "InvestorID": "I2", "InvestorStatus": "Acquirer", "IsLeadInvestor": "No"},
            {"DealID": "D3", "InvestorID": "I3", "InvestorStatus": "New Investor", "IsLeadInvestor": "No"},
        ]
    )
    company_investors = pd.DataFrame(
        [
            {"CompanyID": a, "InvestorID": "I1", "InvestorStatus": "Active"},
            {"CompanyID": a, "InvestorID": "I4", "InvestorStatus": "Add-on Sponsor"},
        ]
    )
    investors = pd.DataFrame(
        [
            {"InvestorID": "I1", "PrimaryInvestorType": "Venture Capital", "HQCountry": "France"},
            {"InvestorID": "I3", "PrimaryInvestorType": "Wholly Made Up Type", "HQCountry": "Spain"},
        ]
    )
    return {
        "Deal": deals,
        "DealInvestorRelation": deal_investors,
        "CompanyInvestorRelation": company_investors,
        "Investor": investors,
    }


def test_filters_and_derived_columns(population):
    ids = population["company_id"].head(3).tolist()
    result = build_all(DictSource(_synthetic_tables(ids)), population)

    deals = result.tables["deals_clean"]
    # Only D1 and D5 survive all four filters.
    assert set(deals["deal_id"]) == {"D1", "D5"}
    assert result.deal_funnel["after_population"] == 5
    assert result.deal_funnel["after_completed"] == 4
    assert result.deal_funnel["after_valid_date"] == 3
    assert result.deal_funnel["after_real_financing"] == 2

    # Derived columns.
    d1 = deals.set_index("deal_id").loc["D1"]
    assert d1["stage_group"] == "Early-stage VC"
    assert d1["size_is_actual"] == 1
    assert d1["is_first_deal"] == 1

    # Deal investors: only financing roles, only surviving deals.
    di = result.tables["deal_investors_clean"]
    assert set(di["investor_id"]) == {"I1"}

    # Company investors: Add-on Sponsor dropped.
    ci = result.tables["company_investors_clean"]
    assert set(ci["investor_id"]) == {"I1"}

    # Investors: only those referenced, with the type group mapped.
    inv = result.tables["investors_clean"].set_index("investor_id")
    assert set(inv.index) == {"I1"}
    assert inv.loc["I1", "investor_type_grp"] == "Independent VC"


def test_unmapped_types_are_flagged(population):
    ids = population["company_id"].head(3).tolist()
    tables = _synthetic_tables(ids)
    tables["Deal"].loc[len(tables["Deal"])] = {
        "CompanyID": ids[0], "DealID": "D9", "DealDate": "06/01/2022",
        "DealType": "Brand New Deal Type", "DealStatus": "Completed",
        "DealSize": "3", "DealSizeStatus": "Actual",
    }
    result = build_all(DictSource(tables), population)
    seen = result.deal_types_seen.set_index("deal_type")
    assert seen.loc["Brand New Deal Type", "stage_group"] == config.UNMAPPED_STAGE_GROUP
    assert not seen.loc["Brand New Deal Type", "is_mapped"]
    assert seen.loc["IPO", "excluded_by_filter"]


def test_dates_parse_in_either_format():
    parsed = parse_deal_dates(pd.Series(["01/15/2020", "2020-01-15", "not a date", None]))
    assert parsed.iloc[0] == pd.Timestamp("2020-01-15")
    assert parsed.iloc[1] == pd.Timestamp("2020-01-15")
    assert pd.isna(parsed.iloc[2])
    assert pd.isna(parsed.iloc[3])
