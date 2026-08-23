"""Step 2: build the firm-level analysis table.

Collapses the Step 1 clean relational tables to one row per firm and joins the
company spine scalars, producing `company_analysis.parquet` (116,005 rows). This
is the single table every Chapter 4 analysis step reads.

See `empirical_analysis/specs/step2_firm_table/design.md` for the full spec.
"""
