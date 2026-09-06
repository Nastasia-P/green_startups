"""Step 13: exploratory composition-adjusted regression analysis.

A supplementary, strictly read-only extension that checks whether green status
stays associated with the core financing outcomes (access, timing, first-five-year
capital) after adjusting for the observable composition the supervisor flagged:
founding cohort, country and primary industry. It uses sequential OLS
specifications (M0-M3) and reports the green coefficient across them.

Every estimated green coefficient is a CONDITIONAL ASSOCIATION, not a causal
effect. Binary access outcomes use a linear probability model (OLS) with robust
standard errors; logistic regression is documented as an alternative but is not
run here. Nothing is reclassified and no existing Step 1-11 output is rewritten.
"""
