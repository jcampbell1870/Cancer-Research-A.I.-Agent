"""Command line entry point: ``python -m agent --output docs/data/results.json``."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .research import all_sources_failed, is_valid_results, run_research, save_results

DEFAULT_OUTPUT = "docs/data/results.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search for cutting-edge cancer research and cures.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="where to write the results JSON")
    parser.add_argument("--lookback-days", type=int, help="how many days back to search")
    parser.add_argument("--max-per-source", type=int, help="maximum items fetched per source")
    parser.add_argument("--validate", metavar="FILE",
                        help="only check that FILE contains valid results JSON and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.validate:
        try:
            with open(args.validate, encoding="utf-8") as handle:
                valid = is_valid_results(json.load(handle))
        except (OSError, ValueError):
            valid = False
        print("valid" if valid else "invalid")
        return 0 if valid else 1

    results = run_research(lookback_days=args.lookback_days, max_per_source=args.max_per_source)
    if all_sources_failed(results):
        logging.error("All sources failed (%s); not overwriting %s", results["errors"], args.output)
        return 1
    save_results(results, args.output)
    print(f"Saved {results['stats']['total']} findings to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
