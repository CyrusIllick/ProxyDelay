#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np


def delta_sensitivity_summary(data: np.ndarray) -> Tuple[float, float, float, float]:
    rates_big = data[:, 1]
    rates_small = data[:, 2]
    d_big = np.log2(np.max(rates_big)) - np.log2(np.min(rates_big))
    d_small = np.log2(np.max(rates_small)) - np.log2(np.min(rates_small))
    d_all = np.log2(np.max(rates_big)) - np.log2(np.min(rates_small))
    d_peak = np.max(np.log2(rates_big) - np.log2(rates_small))
    return d_big, d_small, d_all, d_peak


def load_optional_dataset(path: Path) -> Optional[np.ndarray]:
    if not path.exists():
        return None
    if path.stat().st_size == 0:
        return None
    data = np.loadtxt(path, delimiter=",", dtype=float)
    data = np.atleast_2d(data)
    if data.shape[1] < 5:
        return None
    return data


def delta_range_score(data: np.ndarray, dmin: int, dmax: int) -> float:
    delays_big = data[:, 3]
    delays_small = data[:, 4]
    rates_big = data[:, 1]
    rates_small = data[:, 2]
    mask = (delays_big <= dmax) & (delays_small >= dmin)
    if not np.any(mask):
        return np.nan
    return float(np.max(np.log2(rates_big[mask]) - np.log2(rates_small[mask])))


def build_heatmap_grid(data: np.ndarray, x_vals: np.ndarray, y_vals: np.ndarray) -> np.ndarray:
    grid = np.full((len(y_vals), len(x_vals)), np.nan, dtype=float)
    for yi, dmax in enumerate(y_vals):
        for xi, dmin in enumerate(x_vals):
            if dmax < dmin:
                continue
            grid[yi, xi] = delta_range_score(data, int(dmin), int(dmax))
    return grid


def plot_heatmap(
    data: np.ndarray,
    label: str,
    cmap: str,
    vmin: float,
    vmax: float,
    output_path: Path,
) -> None:
    x_vals = np.arange(6, 21)
    y_vals = np.arange(6, 55)
    grid = build_heatmap_grid(data, x_vals, y_vals)

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(
        grid,
        extent=(x_vals[0], x_vals[-1], y_vals[0], y_vals[-1]),
        origin="lower",
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        aspect="auto",
    )
    ax.plot([6, 20], [6, 20], color="black", linewidth=4)
    ax.set_xlim(6, 20)
    ax.set_ylim(6, 54)
    ax.set_xticks([6, 20])
    ax.set_yticks([6, 54])
    ax.set_xlabel(r"$d_{min}$")
    ax.set_ylabel(r"$d_{max}$")
    ax.text(12.0, 8.0, label, fontsize=18)
    fig.colorbar(im, ax=ax, pad=0.01)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def print_summary(label: str, data: np.ndarray) -> None:
    d_big, d_small, d_all, d_peak = delta_sensitivity_summary(data)
    delta = np.log2(data[:, 1]) - np.log2(data[:, 2])
    peak_idx = int(np.argmax(delta))
    print(
        f"{label}: "
        f"d_big={d_big:.4f}, d_small={d_small:.4f}, d_all={d_all:.4f}, d_peak={d_peak:.4f}, "
        f"peak_delays=({int(data[peak_idx, 3])}ms,{int(data[peak_idx, 4])}ms)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate two-flow delta-sensitivity plots from emulated datasets.")
    parser.add_argument("--input-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()

    bbr1_path = args.input_dir / "bbrv1_proxy_noProxy_emulated.txt"
    bbr3_path = args.input_dir / "bbrv3_proxy_noProxy_emulated.txt"
    bbr1 = load_optional_dataset(bbr1_path)
    bbr3 = load_optional_dataset(bbr3_path)

    plotted_any = False

    if bbr1 is not None:
        bbr1_proxy = bbr1[bbr1[:, 0] == 1]
        bbr1_no_proxy = bbr1[bbr1[:, 0] == 0]

        if len(bbr1_no_proxy) > 0:
            print_summary("BBRv1 no proxy", bbr1_no_proxy)
            plot_heatmap(
                bbr1_no_proxy,
                label="BBRv1",
                cmap="magma",
                vmin=0.0,
                vmax=4.5,
                output_path=args.output_dir / "delta_two_flow_bbrv1_no_proxy.png",
            )
            plotted_any = True
        if len(bbr1_proxy) > 0:
            print_summary("BBRv1 proxy", bbr1_proxy)
            plot_heatmap(
                bbr1_proxy,
                label="BBRv1+Proxy",
                cmap="bone",
                vmin=0.0,
                vmax=0.5,
                output_path=args.output_dir / "delta_two_flow_bbrv1_proxy.png",
            )
            plotted_any = True

    if bbr3 is not None:
        bbr3_proxy = bbr3[bbr3[:, 0] == 1]
        bbr3_no_proxy = bbr3[bbr3[:, 0] == 0]

        if len(bbr3_no_proxy) > 0:
            print_summary("BBRv3 no proxy", bbr3_no_proxy)
            plot_heatmap(
                bbr3_no_proxy,
                label="BBRv3",
                cmap="magma",
                vmin=0.0,
                vmax=4.5,
                output_path=args.output_dir / "delta_two_flow_bbrv3_no_proxy.png",
            )
            plotted_any = True
        if len(bbr3_proxy) > 0:
            print_summary("BBRv3 proxy", bbr3_proxy)
            plot_heatmap(
                bbr3_proxy,
                label="BBRv3+Proxy",
                cmap="bone",
                vmin=0.0,
                vmax=0.5,
                output_path=args.output_dir / "delta_two_flow_bbrv3_proxy.png",
            )
            plotted_any = True

    if not plotted_any:
        raise ValueError(
            f"No usable two-flow dataset rows found in {bbr1_path} or {bbr3_path}"
        )

    print(f"Wrote figures to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
