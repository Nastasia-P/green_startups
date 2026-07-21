"""Clean the malformed startups_filtered.csv.

The source file is double-encoded:
  - The header has a trailing ";;;;;;" glued to the last column ("Age;;;;;;").
  - Every data row is wrapped in one extra pair of quotes (internal quotes
    doubled) and followed by ";;;;;;", so naive readers collapse each row into
    a single field.
  - Some records contain embedded newlines inside a quoted field, so a single
    logical record spans multiple physical lines. Such a record is terminated
    only by the trailing ";;;;;;".

This script streams the file record by record (memory-safe for ~348k rows),
reassembles multi-line records using the ";;;;;;" terminator, unwraps the
outer quote layer, and writes a standard RFC-4180 CSV where fields containing
commas/quotes/newlines are properly quoted.
"""

import csv
import sys

INPUT_PATH = "startups_filtered.csv"
OUTPUT_PATH = "startups_cleaned.csv"
ERROR_PATH = "startups_cleaned_errors.txt"
ARTIFACT = ";;;;;;"


def strip_artifact(text: str) -> str:
    text = text.rstrip("\r\n")
    if text.endswith(ARTIFACT):
        text = text[: -len(ARTIFACT)]
    return text


def iter_records(fin):
    """Yield complete logical records, joining lines split by embedded newlines.

    A record is complete once the accumulated text (ignoring the trailing
    line break) ends with the ";;;;;;" terminator.
    """
    buffer = ""
    for raw in fin:
        buffer += raw
        if buffer.rstrip("\r\n").endswith(ARTIFACT):
            yield buffer
            buffer = ""
    if buffer.strip():
        yield buffer


def main() -> None:
    with open(INPUT_PATH, "r", encoding="utf-8", newline="") as fin, open(
        OUTPUT_PATH, "w", encoding="utf-8", newline=""
    ) as fout, open(ERROR_PATH, "w", encoding="utf-8", newline="") as ferr:
        writer = csv.writer(fout)

        header = strip_artifact(fin.readline())
        columns = next(csv.reader([header]))
        expected = len(columns)
        writer.writerow(columns)

        written = 0
        bad = 0
        for recno, raw_record in enumerate(iter_records(fin), start=2):
            record = strip_artifact(raw_record)
            if not record.strip():
                continue
            # Outer layer: the whole real row is a single quoted field, which
            # may itself contain embedded newlines.
            outer = next(csv.reader(record.splitlines(keepends=True)))
            inner = outer[0] if len(outer) == 1 else record
            row = next(csv.reader(inner.splitlines(keepends=True)))
            if len(row) != expected:
                # Source-level corruption (inconsistent quote escaping). Keep the
                # main output rectangular and route the raw record for review.
                bad += 1
                ferr.write(f"# source record {recno}: parsed {len(row)} cols\n")
                ferr.write(raw_record if raw_record.endswith("\n") else raw_record + "\n")
                continue
            writer.writerow(row)
            written += 1

    print(f"Columns: {expected}")
    print(f"Clean rows written: {written}")
    print(f"Corrupted rows skipped (see {ERROR_PATH}): {bad}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
