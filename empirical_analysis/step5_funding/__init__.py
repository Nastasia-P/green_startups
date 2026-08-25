"""Step 5: funding.

Descriptive funding analysis of European green vs other start-ups, structured as
access -> amount -> timing/stage -> trajectory. Access is measured on the full
116,005 population; amounts, sizes, valuations, lags and trajectories are measured
only within the financed subsample (rule N1), because green firms are far better
documented and a raw amount comparison would measure coverage, not capital.

Reads the Step 2 firm table (`company_analysis.parquet`) and the Step 1
`deals_clean` table, and writes thesis outputs T4.9-T4.17 (incl. T4.12) and figure
data F4.4.

See `empirical_analysis/specs/step5_funding/design.md` for the spec.
"""
