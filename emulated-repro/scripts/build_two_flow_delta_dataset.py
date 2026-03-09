#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

from ss_utils import as_int, mean, parse_cc_value, parse_ss_log, parse_test_params, slice_window


def collect_delta_rows(
    input_root: Path,
    window_start: float,
    window_end: float,
) -> Dict[str, Dict[Tuple[int, int, int], List[Tuple[float, float, float, float, float]]]]:
    grouped: Dict[str, Dict[Tuple[int, int, int], List[Tuple[float, float, float, float, float]]]] = {
        "bbr1": defaultdict(list),
        "bbr": defaultdict(list),
    }

    param_files = sorted(input_root.rglob("test_params.txt"))
    for param_file in param_files:
        params = parse_test_params(param_file)
        cc_list = parse_cc_value(params.get("cc"))
        if not cc_list:
            continue
        cc_name = cc_list[0]
        if cc_name not in grouped:
            continue

        ss_file = param_file.with_name("ss.log")
        if not ss_file.exists():
            continue

        samples_by_port = parse_ss_log(ss_file, target_ports=[10000, 10001])
        if 10000 not in samples_by_port or 10001 not in samples_by_port:
            continue

        port_metrics = {}
        for port in (10000, 10001):
            window = slice_window(samples_by_port[port], window_start, window_end)
            rate = mean([s.delivery_mbps for s in window])
            cwnd = mean([s.cwnd for s in window])
            rtt = mean([s.rtt_ms for s in window])
            extra = mean([s.extra_acked for s in window])
            port_metrics[port] = {
                "rate": rate,
                "cwnd": cwnd,
                "rtt": rtt,
                "extra": extra,
            }

        if port_metrics[10000]["rate"] is None or port_metrics[10001]["rate"] is None:
            continue

        proxy_on = as_int(params.get("proxy_on"), 0)
        delay_a = as_int(params.get("a_delay"), 0)
        delay_b = as_int(params.get("b_delay"), 0)

        if delay_a >= delay_b:
            big_port, small_port = 10000, 10001
        else:
            big_port, small_port = 10001, 10000
        big_delay = max(delay_a, delay_b)
        small_delay = min(delay_a, delay_b)

        key = (proxy_on, big_delay, small_delay)
        grouped[cc_name][key].append(
            (
                float(port_metrics[big_port]["rate"]),
                float(port_metrics[small_port]["rate"]),
                float(port_metrics[big_port]["extra"] or 0.0),
                float(port_metrics[big_port]["cwnd"] or 0.0),
                float(port_metrics[big_port]["rtt"] or 0.0),
            )
        )
    return grouped


def write_delta_file(
    path: Path,
    grouped_rows: Dict[Tuple[int, int, int], List[Tuple[float, float, float, float, float]]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered_keys = sorted(grouped_rows.keys(), key=lambda x: (x[0], x[1], x[2]))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for proxy_on, big_delay, small_delay in ordered_keys:
            values = grouped_rows[(proxy_on, big_delay, small_delay)]
            big_rate = sum(v[0] for v in values) / len(values)
            small_rate = sum(v[1] for v in values) / len(values)
            extra_acked = sum(v[2] for v in values) / len(values)
            cwnd = sum(v[3] for v in values) / len(values)
            rtt = sum(v[4] for v in values) / len(values)
            writer.writerow(
                [
                    proxy_on,
                    round(big_rate, 3),
                    round(small_rate, 3),
                    big_delay,
                    small_delay,
                    round(extra_acked, 3),
                    round(cwnd, 6),
                    round(rtt, 6),
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build two-flow delta-sensitivity datasets from raw ss logs.")
    parser.add_argument("--input-root", type=Path, default=Path("results/two_flow_delta"))
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--window-start", type=float, default=0.45)
    parser.add_argument("--window-end", type=float, default=0.95)
    args = parser.parse_args()

    grouped = collect_delta_rows(args.input_root, args.window_start, args.window_end)

    out_bbr1 = args.output_dir / "bbrv1_proxy_noProxy_emulated.txt"
    out_bbr3 = args.output_dir / "bbrv3_proxy_noProxy_emulated.txt"
    write_delta_file(out_bbr1, grouped["bbr1"])
    write_delta_file(out_bbr3, grouped["bbr"])

    print(f"Wrote {out_bbr1} with {len(grouped['bbr1'])} unique (proxy, delay) settings")
    print(f"Wrote {out_bbr3} with {len(grouped['bbr'])} unique (proxy, delay) settings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
