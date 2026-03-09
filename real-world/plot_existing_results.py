#!/usr/bin/env python3

"""Rebuild graphs/statistics from already-collected real-world raw logs."""

from __future__ import annotations

import argparse

import figure_parser
from config_loader import get_report_root


def main() -> int:
    """CLI entrypoint for offline plotting/stat generation."""
    parser = argparse.ArgumentParser(
        description="Generate graphs/statistics from an existing real-world test timestamp directory."
    )
    parser.add_argument("--timestamp", required=True, help="Timestamp folder name, e.g. 2026-03-07--14:20:30")
    parser.add_argument(
        "--report-root",
        default=get_report_root(),
        help="Base report directory (default from config/topology.json report_root)",
    )
    args = parser.parse_args()

    data_array = figure_parser.generate_data_array(args.timestamp, report_root=args.report_root)
    if not data_array:
        raise RuntimeError(
            f"No parsed ss data found for timestamp '{args.timestamp}' under '{args.report_root}'."
        )

    figure_parser.create_graphs_directory(args.timestamp, report_root=args.report_root)
    figure_parser.generate_graphs(args.timestamp, data_array, report_root=args.report_root)
    figure_parser.generate_statistics(args.timestamp, data_array, report_root=args.report_root)
    print(f"Plots/statistics generated in {args.report_root}/{args.timestamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
