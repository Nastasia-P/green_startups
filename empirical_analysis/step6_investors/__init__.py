"""Step 6: investors and grants.

Descriptive analysis of *who* finances European green vs other start-ups: the
distribution of investor types, company-level investor flags, public/private
combination, grant -> VC sequencing, investor geography, and syndication.

The master population is the INVESTED subsample (firms with at least one recorded
investor, `n_investors_lifetime >= 1`), because green firms are far better
documented and a full-population composition comparison would measure coverage.
Most per-firm variables (flags, distinct-investor count, public/private indicators,
origin shares) are already carried by the Step 2 firm table; Step 6 groups and joins
the Step 1 clean tables and summarises.

Reads `company_analysis.parquet` (Step 2) and the Step 1 clean tables
(`deals_clean`, `company_investors_clean`, `investors_clean`, `deal_investors_clean`),
and writes thesis outputs T4.18, T4.19, T4.21, T4.22, T4.23, T4.25 and figure data
F4.5.

See `empirical_analysis/specs/step6_investors/design.md` for the spec.
"""
