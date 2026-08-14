"""Entry point: the CLI, runnable as `python report.py --help`."""
import sys

from cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
