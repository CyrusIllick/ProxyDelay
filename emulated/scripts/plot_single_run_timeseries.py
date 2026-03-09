#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np

from ss_utils import TimedFlowSample, parse_cc_value, parse_ss_log_timed, parse_test_params


PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]
LINE_STYLES = ["-", "--", ":", "-."]


def _load_manifest(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_timeseries(path: Path, run_id: str) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    out: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("run_id") == run_id:
                out.append(row)
    return out


def _run_id_from_path(run_dir: Path) -> str:
    return run_dir.resolve().as_posix().replace("/", "__")


def _normalize_ccas(ccas: Sequence[str], flow_count: int) -> List[str]:
    if not ccas:
        return ["unknown"] * flow_count
    out = list(ccas)
    while len(out) < flow_count:
        out.append(out[-1])
    return out[:flow_count]


def _rows_from_samples(run_id: str, ccas: Sequence[str], samples: Sequence[TimedFlowSample]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    t_base = next((sample.t_sec for sample in samples if sample.t_sec is not None), None)

    for idx, sample in enumerate(samples):
        flow_index = max(0, sample.port - 10000)
        cca = ccas[flow_index] if flow_index < len(ccas) else "unknown"

        if sample.t_sec is None:
            t_rel = float(idx) * 0.1 if t_base is None else 0.0
        else:
            t_rel = sample.t_sec - (t_base if t_base is not None else sample.t_sec)

        rows.append(
            {
                "run_id": run_id,
                "t_sec": f"{t_rel:.6f}",
                "flow_index": str(flow_index),
                "port": str(sample.port),
                "cca": cca,
                "delivery_mbps": "" if sample.delivery_mbps is None else f"{sample.delivery_mbps:.6f}",
                "cwnd": "" if sample.cwnd is None else f"{sample.cwnd:.6f}",
                "rtt_ms": "" if sample.rtt_ms is None else f"{sample.rtt_ms:.6f}",
                "extra_acked": "" if sample.extra_acked is None else f"{sample.extra_acked:.6f}",
            }
        )

    return rows


def _load_direct_from_run_dir(run_dir: Path) -> Tuple[str, List[Dict[str, str]]]:
    params_path = run_dir / "test_params.txt"
    ss_path = run_dir / "ss.log"
    if not params_path.exists() or not ss_path.exists():
        raise FileNotFoundError(f"Missing test_params.txt or ss.log in {run_dir}")

    params = parse_test_params(params_path)
    ccas = parse_cc_value(params.get("cc"))

    max_port = 10003 if len(ccas) >= 4 else 10001
    target_ports = list(range(10000, max_port + 1))

    samples = parse_ss_log_timed(ss_path, target_ports=target_ports)
    if not samples:
        raise ValueError(f"No usable ss samples found in {ss_path}")

    flow_count = max(2, max(sample.port for sample in samples) - 10000 + 1)
    ccas = _normalize_ccas(ccas, flow_count)

    run_id = _run_id_from_path(run_dir)
    return run_id, _rows_from_samples(run_id, ccas, samples)


def _float_or_nan(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _compute_summary(rows: Sequence[Dict[str, str]]) -> Tuple[Dict[int, float], float, float]:
    grouped: Dict[int, List[float]] = defaultdict(list)
    for row in rows:
        flow_index = int(row["flow_index"])
        rate = _float_or_nan(row["delivery_mbps"])
        if not np.isnan(rate):
            grouped[flow_index].append(rate)

    per_flow_mean: Dict[int, float] = {}
    for flow_index, values in grouped.items():
        per_flow_mean[flow_index] = float(np.mean(values)) if values else 0.0

    means = np.array(list(per_flow_mean.values()), dtype=float)
    aggregate = float(np.sum(means)) if means.size else 0.0
    if means.size == 0 or float(np.sum(means * means)) == 0.0:
        fairness = float("nan")
    else:
        fairness = float((np.sum(means) ** 2) / (means.size * np.sum(means * means)))

    return per_flow_mean, aggregate, fairness


def _plot_rows(rows: Sequence[Dict[str, str]], output_path: Path) -> None:
    grouped: Dict[int, List[Tuple[float, float, str, int]]] = defaultdict(list)
    ccas = sorted({row["cca"] for row in rows})
    color_map = {cca: PALETTE[idx % len(PALETTE)] for idx, cca in enumerate(ccas)}

    for row in rows:
        t_sec = _float_or_nan(row["t_sec"])
        rate = _float_or_nan(row["delivery_mbps"])
        if np.isnan(t_sec) or np.isnan(rate):
            continue
        flow_index = int(row["flow_index"])
        port = int(row["port"])
        grouped[flow_index].append((t_sec, rate, row["cca"], port))

    if not grouped:
        raise ValueError("No plottable delivery-rate rows found")

    fig, ax = plt.subplots(figsize=(10, 6))
    for flow_index in sorted(grouped.keys()):
        points = sorted(grouped[flow_index], key=lambda x: x[0])
        t = np.array([point[0] for point in points], dtype=float)
        y = np.array([point[1] for point in points], dtype=float)
        cca = points[0][2]
        port = points[0][3]
        label = f"flow {flow_index + 1} ({cca}, port {port})"
        ax.plot(
            t,
            y,
            label=label,
            color=color_map[cca],
            linestyle=LINE_STYLES[flow_index % len(LINE_STYLES)],
            linewidth=2,
        )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Delivery Rate (Mbps)")
    ax.set_title("Per-Flow Delivery Rate Over Time")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def _write_summary(
    summary_path: Path,
    run_id: str,
    run_dir: Optional[Path],
    rows: Sequence[Dict[str, str]],
) -> None:
    per_flow_mean, aggregate_mean, fairness = _compute_summary(rows)

    cc_by_flow: Dict[int, str] = {}
    for row in rows:
        flow_index = int(row["flow_index"])
        cc_by_flow.setdefault(flow_index, row["cca"])

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        f.write(f"run_id: {run_id}\n")
        if run_dir is not None:
            f.write(f"run_dir: {run_dir.resolve()}\n")
        f.write("\n")
        for flow_index in sorted(per_flow_mean.keys()):
            cca = cc_by_flow.get(flow_index, "unknown")
            f.write(
                f"flow_{flow_index + 1}_mean_mbps ({cca}): {per_flow_mean[flow_index]:.6f}\n"
            )
        f.write(f"aggregate_mean_mbps: {aggregate_mean:.6f}\n")
        if np.isnan(fairness):
            f.write("jain_fairness: nan\n")
        else:
            f.write(f"jain_fairness: {fairness:.6f}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plot delivery-rate time series for one emulated run")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-dir", type=Path, help="Run directory containing test_params.txt and ss.log")
    group.add_argument("--run-id", type=str, help="run_id from runs_manifest.csv")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Directory containing dataset CSV files")
    parser.add_argument("--output-dir", type=Path, default=Path("figures"), help="Output directory for figure/summary")
    args = parser.parse_args()

    manifest_path = args.data_dir / "runs_manifest.csv"
    timeseries_path = args.data_dir / "timeseries.csv"

    manifest_rows = _load_manifest(manifest_path)
    run_dir: Optional[Path] = None

    if args.run_id:
        run_id = args.run_id
        rows = _load_timeseries(timeseries_path, run_id)
        if not rows:
            raise ValueError(f"No rows for run_id={run_id} in {timeseries_path}")
        for row in manifest_rows:
            if row.get("run_id") == run_id:
                run_dir = Path(row["run_dir"])
                break
    else:
        run_dir = args.run_dir.resolve()
        run_id = ""
        for row in manifest_rows:
            if Path(row["run_dir"]).resolve() == run_dir:
                run_id = row["run_id"]
                break

        if run_id:
            rows = _load_timeseries(timeseries_path, run_id)
            if not rows:
                run_id, rows = _load_direct_from_run_dir(run_dir)
        else:
            run_id, rows = _load_direct_from_run_dir(run_dir)

    figure_path = args.output_dir / f"{run_id}_delivery_rate.png"
    summary_path = args.output_dir / f"{run_id}_summary.txt"

    _plot_rows(rows, figure_path)
    _write_summary(summary_path, run_id, run_dir, rows)

    print(f"Wrote {figure_path}")
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
