"""Step 9: keyword-recovery robustness diagnostic.

A strictly additive, read-only exercise that answers a supervisor's question:
of the 6,636 firms flagged green *only* via PitchBook's CleanTech / Climate Tech
verticals (Stage 1), how many can be independently recovered by applying the
thesis's own environmental vocabulary (standalone tokens + multi-word phrases) to
the Keywords and Description text alone?

It never runs the vertical stage as a search signal, never modifies the existing
green classification, and writes only new files. See this package's README.md for
the interpretation boundary and thesis-usage note.
"""
