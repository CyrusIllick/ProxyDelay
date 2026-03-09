#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Sequence

from ss_utils import TimedFlowSample, as_int, parse_cc_value, parse_ss_log_timed, parse_test_params


MANIFEST_COLUMNS = [
    "run_id",
    "run_dir",
    "flow_mode",
    "rep",
    "proxy_on",
    "a_delay",
    "b_delay",
    "c_delay",
    "d_delay",
    "ccas",
]

TIMESERIES_COLUMNS = [
    "run_id",
    "t_sec",
    "flow_index",
    "port",
    "cca",
    "delivery_mbps",
    "cwnd",
    "rtt_ms",
    "extra_acked",
]

REP_DIR_RE = re.compile(r"^rep_(\d+)$")


def make_run_id(input_root: Path, run_dir: Path) -> str:
    try:
        rel = run_dir.resolve().relative_to(input_root.resolve())
        return rel.as_posix().replace("/", "__")
    except ValueError:
        return run_dir.resolve().as_posix().replace("/", "__")


def infer_flow_mode(run_dir: Path, ccas: Sequence[str]) -> str:
    parts = set(run_dir.parts)
    if "two_flow" in parts:
        return "two_flow"
    if "four_flow" in parts:
        return "four_flow"
    if len(ccas) >= 4:
        return "four_flow"
    return "two_flow"


def normalize_ccas(ccas: Sequence[str], flow_mode: str) -> List[str]:
    if flow_mode == "four_flow":
        if len(ccas) >= 4:
            return list(ccas[:4])
        out = list(ccas)
        while len(out) < 4:
            out.append("unknown")
        return out

    # two_flow
    if len(ccas) >= 2:
        return list(ccas[:2])
    if len(ccas) == 1:
        return [ccas[0], ccas[0]]
    return ["unknown", "unknown"]


def target_ports_for_mode(flow_mode: str) -> List[int]:
    return [10000, 10001, 10002, 10003] if flow_mode == "four_flow" else [10000, 10001]


def infer_rep(run_dir: Path, params: Dict[str, object]) -> int:
    rep_from_params = as_int(params.get("rep"), 0)
    if rep_from_params > 0:
        return rep_from_params

    for part in run_dir.parts:
        match = REP_DIR_RE.match(part)
        if match:
            return int(match.group(1))

    return 1


def timed_rows(run_id: str, ccas: Sequence[str], samples: Sequence[TimedFlowSample]) -> List[Dict[str, str]]:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Build generalized emulated timeseries datasets from raw ss logs")
    parser.add_argument("--input-root", type=Path, default=Path("results"))
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "runs_manifest.csv"
    timeseries_path = args.output_dir / "timeseries.csv"

    manifest_rows: List[Dict[str, str]] = []
    series_rows: List[Dict[str, str]] = []

    for param_file in sorted(args.input_root.rglob("test_params.txt")):
        run_dir = param_file.parent
        run_id = make_run_id(args.input_root, run_dir)

        params = parse_test_params(param_file)
        raw_ccas = parse_cc_value(params.get("cc"))
        flow_mode = infer_flow_mode(run_dir, raw_ccas)
        ccas = normalize_ccas(raw_ccas, flow_mode)
        rep = infer_rep(run_dir, params)

        manifest_rows.append(
            {
                "run_id": run_id,
                "run_dir": str(run_dir.resolve()),
                "flow_mode": flow_mode,
                "rep": str(rep),
                "proxy_on": str(as_int(params.get("proxy_on"), 0)),
                "a_delay": str(as_int(params.get("a_delay"), 0)),
                "b_delay": str(as_int(params.get("b_delay"), 0)),
                "c_delay": str(as_int(params.get("c_delay"), 0)),
                "d_delay": str(as_int(params.get("d_delay"), 0)),
                "ccas": json.dumps(ccas),
            }
        )

        ss_file = run_dir / "ss.log"
        if not ss_file.exists():
            continue

        samples = parse_ss_log_timed(ss_file, target_ports=target_ports_for_mode(flow_mode))
        if not samples:
            continue

        series_rows.extend(timed_rows(run_id, ccas, samples))

    with manifest_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    with timeseries_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TIMESERIES_COLUMNS)
        writer.writeheader()
        writer.writerows(series_rows)

    print(f"Wrote {manifest_path} with {len(manifest_rows)} runs")
    print(f"Wrote {timeseries_path} with {len(series_rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
