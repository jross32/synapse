import csv
import io
import re


def read_rows(text, required):
    if not text or not text.strip():
        return [], []

    rows = []
    problems = []
    reader = csv.DictReader(io.StringIO(text))

    for i, row in enumerate(reader, start=2):
        missing = [col for col in required if col not in row or row[col].strip() == ""]
        if missing:
            for col in missing:
                if col not in row:
                    problems.append(f"line {i}: missing column '{col}'")
                else:
                    problems.append(f"line {i}: empty value for column '{col}'")
        else:
            rows.append(dict(row))

    return rows, problems


def parse_amount(value):
    original = value
    s = value.strip().lstrip("$").strip()

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()

    s = s.replace(",", "")

    try:
        result = float(s)
    except ValueError:
        raise ValueError(f"cannot parse amount: {original!r}")

    return -result if negative else result
