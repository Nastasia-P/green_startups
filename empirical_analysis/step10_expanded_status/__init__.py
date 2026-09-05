"""Step 10: expanded start-up-status population (supplementary sensitivity).

A strictly additive, read-only exercise that reconstructs a broader observable
population of young European firms - including those that have since been
acquired/merged, gone public, or ceased operating - so the 2026 baseline's
"surviving start-ups only" limitation can be assessed.

It keeps the baseline's Europe + valid founding year + age<=10 criteria, but
drops the current-ownership restriction, the operating-status restriction, and
broadens the Universe rule to also admit M&A and Publicly Listed (excluding only
Other Private Companies). Every firm receives a transparent, traceable reason for
being inside or outside the 2026 baseline, and the existing green methodology is
applied for a green/other comparison.

It modifies nothing else: it only reads prior outputs and the raw source, and
writes its own new files. See this package's README.md for the definitions and
the interpretation boundary.
"""
