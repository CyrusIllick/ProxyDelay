#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np


def dsense(values: np.ndarray) -> float:
    return float(np.log2(np.max(values)) - np.log2(np.min(values)))


def load_delay_file(path: Path) -> Tuple[Tuple[str, str, str, str], np.ndarray]:
    rows: List[List[str]] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f, skipinitialspace=True)
        for row in reader:
            cleaned = [x.strip() for x in row if x.strip() != ""]
            if cleaned:
                rows.append(cleaned)
    if not rows:
        raise ValueError(f"No rows found in {path}")
    cc_tuple = tuple(rows[0][:4])  # type: ignore[assignment]
    numeric_rows = []
    for row in rows:
        numeric_rows.append([float(x) for x in row[4:12]])
    return cc_tuple, np.array(numeric_rows, dtype=float)


def average_by_delay(data: np.ndarray) -> np.ndarray:
    grouped: Dict[Tuple[float, float, float, float], List[np.ndarray]] = defaultdict(list)
    for row in data:
        key = tuple(row[:4])
        grouped[key].append(row[4:])
    averaged = []
    for key, values in grouped.items():
        averaged.append(list(key) + list(np.mean(values, axis=0)))
    return np.array(averaged, dtype=float)


def make_bar_plot(
    values: np.ndarray,
    experiments: List[str],
    labels: List[str],
    colors: List[str],
    output_path: Path,
) -> None:
    n_experiments = len(experiments)
    n_values = len(labels)
    x = np.arange(n_experiments)
    bar_width = 0.18
    spacing = 0.02
    hatches = ["/", "\\", "-", "+"]

    fig, ax = plt.subplots(figsize=(9, 6))
    for i in range(n_values):
        positions = x + i * (bar_width + spacing)
        ax.bar(
            positions,
            values[:, i],
            width=bar_width,
            color=colors[i],
            hatch=hatches[i],
            edgecolor="black",
            label=labels[i],
        )

    mid_positions = x + (n_values / 2 - 0.5) * (bar_width + spacing)
    ax.set_xticks(mid_positions)
    ax.set_xticklabels(experiments, fontsize=20)
    ax.set_ylabel(r"$\delta$-sensitivity", fontsize=20)
    ax.tick_params(axis="y", labelsize=20)
    ax.legend(fontsize=16, ncol=2)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate delay-sensitivity bar plots from processed four-flow datasets.")
    parser.add_argument("--input-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()

    bbr_base = args.input_dir / "het_data_bbrhyblacubicreno_veryshallow_multReps.txt"
    bbr_plus50 = args.input_dir / "het_data_bbrhyblacubicreno_veryshallow_multReps_plus_50ms.txt"
    ill_base = args.input_dir / "het_data_illinoiswestwoodcubicreno_veryshallow_multReps.txt"
    ill_small = args.input_dir / "het_data_illinoiswestwoodcubicreno_veryshallow_multReps_smallrange354045.txt"

    bbr_labels, bbr_data = load_delay_file(bbr_base)
    _, bbr_plus_data = load_delay_file(bbr_plus50)
    ill_labels, ill_data = load_delay_file(ill_base)
    _, ill_small_data = load_delay_file(ill_small)

    bbr_avg = average_by_delay(bbr_data)
    bbr_plus_avg = average_by_delay(bbr_plus_data)
    bbr_values = np.array(
        [
            [dsense(bbr_avg[:, 4]), dsense(bbr_avg[:, 5]), dsense(bbr_avg[:, 6]), dsense(bbr_avg[:, 7])],
            [dsense(bbr_plus_avg[:, 4]), dsense(bbr_plus_avg[:, 5]), dsense(bbr_plus_avg[:, 6]), dsense(bbr_plus_avg[:, 7])],
        ]
    )
    make_bar_plot(
        bbr_values,
        experiments=[r"$\lambda^{add}=0$ms", r"$\lambda^{add}=50$ms"],
        labels=[x.upper() if x == "bbr" else x.capitalize() for x in bbr_labels],
        colors=["#575AFF", "#36E0A2", "#FF9F40", "#E255A1"],
        output_path=args.output_dir / "delay_sensitivity_bbr_hybla_cubic_reno.png",
    )

    ill_avg = average_by_delay(ill_data)
    ill_small_avg = average_by_delay(ill_small_data)
    ill_values = np.array(
        [
            [dsense(ill_avg[:, 4]), dsense(ill_avg[:, 5]), dsense(ill_avg[:, 6]), dsense(ill_avg[:, 7])],
            [dsense(ill_small_avg[:, 4]), dsense(ill_small_avg[:, 5]), dsense(ill_small_avg[:, 6]), dsense(ill_small_avg[:, 7])],
        ]
    )
    make_bar_plot(
        ill_values,
        experiments=[r"$\mathcal{D}_1$", r"$\mathcal{D}_2$"],
        labels=[x.capitalize() for x in ill_labels],
        colors=["#57B8FF", "#7ED957", "#FF9F40", "#E255A1"],
        output_path=args.output_dir / "delay_sensitivity_illinois_westwood_cubic_reno.png",
    )

    print(f"Wrote figures to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

