"""Step 1 of the empirical pipeline: clean the raw PitchBook data.

Reads the raw extract in chunks, keeps only the study population and genuine
financing events, and writes clean per-grain Parquet tables plus two reference
enumerations and an integrity audit. No firm-level aggregation happens here:
that is Step 2.
"""
