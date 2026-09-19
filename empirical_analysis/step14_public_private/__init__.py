"""Step 14: public/private investor participation (common horizon).

A self-contained, strictly read-only extension addressing the supervisor's
public/private request. It starts from an explicit investor classification
audit (`investor_type_mapping.csv`), builds common-horizon (Step 5b five-year
window) public/private participation variables, runs composition-adjusted
linear probability regressions with a deal-count sensitivity column, describes
grant->VC and public/private sequencing within the window, and -- because no
investor-level contributed amount exists in the data -- reports disclosed deal
sizes by investor composition rather than fabricating per-investor capital.

It reuses the baseline green classification, the Step 5b eligible population and
firm-relative window, and the Step 1 investor tables. It never rewrites any
existing Step 1-13 output; every file it writes has a distinct name.
"""
