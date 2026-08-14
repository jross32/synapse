import argparse
import json
import sys

from reader import read_rows, parse_amount
from summary import format_table, summarize, top_n


def main(argv):
    parser = argparse.ArgumentParser(prog="report")
    parser.add_argument("file", nargs="?", default="-", metavar="FILE")
    parser.add_argument("--group-by", required=True, metavar="COLUMN")
    parser.add_argument("--amount", required=True, metavar="COLUMN")
    parser.add_argument("--top", type=int, default=None, metavar="N")
    parser.add_argument("--json", action="store_true")

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 1

    if args.file == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(args.file, "r") as fh:
                text = fh.read()
        except FileNotFoundError:
            print(f"error: file not found: {args.file}", file=sys.stderr)
            return 2
        except OSError as exc:
            print(f"error: cannot read file: {exc}", file=sys.stderr)
            return 1

    required = {args.group_by, args.amount}
    rows, rejected = read_rows(text, required)

    for msg in rejected:
        print(msg, file=sys.stderr)

    parsed_rows = []
    for row in rows:
        try:
            row = dict(row)
            row[args.amount] = parse_amount(row[args.amount])
            parsed_rows.append(row)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
    rows = parsed_rows

    if not rows:
        print("error: no valid rows to summarize", file=sys.stderr)
        return 1

    try:
        summaries = summarize(rows, args.group_by, args.amount)
        if args.top is not None:
            summaries = top_n(summaries, args.top)
        if args.json:
            print(json.dumps(summaries))
        else:
            print(format_table(summaries))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
