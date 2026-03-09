#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from ss_utils import as_int, mean, parse_cc_value, parse_ss_log, parse_test_params


@dataclass
class DatasetSpec:
    output_name: str
    cc_tuple: Tuple[str, str, str, str]
    delay_values: Tuple[int, int, int]
    rows: List[Tuple[Tuple[int, int, int, int], Tuple[float, float, float, float]]] = field(default_factory=list)

    def matches(self, cc_tuple: Tuple[str, ...], delays: Tuple[int, int, int, int]) -> bool:
        if tuple(cc_tuple) != self.cc_tuple:
            return False
        allowed = set(self.delay_values)
        return all(d in allowed for d in delays)


def collect_delay_rows(input_root: Path) -> List[DatasetSpec]:
    specs = [
        DatasetSpec(
            output_name="het_data_bbrhyblacubicreno_veryshallow_multReps.txt",
            cc_tuple=("bbr", "hybla", "cubic", "reno"),
            delay_values=(10, 20, 30),
        ),
        DatasetSpec(
            output_name="het_data_bbrhyblacubicreno_veryshallow_multReps_plus_50ms.txt",
            cc_tuple=("bbr", "hybla", "cubic", "reno"),
            delay_values=(60, 70, 80),
        ),
        DatasetSpec(
            output_name="het_data_illinoiswestwoodcubicreno_veryshallow_multReps.txt",
            cc_tuple=("illinois", "westwood", "cubic", "reno"),
            delay_values=(5, 15, 30),
        ),
        DatasetSpec(
            output_name="het_data_illinoiswestwoodcubicreno_veryshallow_multReps_smallrange354045.txt",
            cc_tuple=("illinois", "westwood", "cubic", "reno"),
            delay_values=(35, 40, 45),
        ),
    ]

    for param_file in sorted(input_root.rglob("test_params.txt")):
        params = parse_test_params(param_file)
        cc_list = tuple(parse_cc_value(params.get("cc")))
        if len(cc_list) != 4:
            continue

        delays = (
            as_int(params.get("a_delay"), 0),
            as_int(params.get("b_delay"), 0),
            as_int(params.get("c_delay"), 0),
            as_int(params.get("d_delay"), 0),
        )

        ss_file = param_file.with_name("ss.log")
        if not ss_file.exists():
            continue
        samples_by_port = parse_ss_log(ss_file, target_ports=[10000, 10001, 10002, 10003])

        if any(port not in samples_by_port for port in (10000, 10001, 10002, 10003)):
            continue

        rate_tuple = (
            mean([s.delivery_bps for s in samples_by_port[10000]]),
            mean([s.delivery_bps for s in samples_by_port[10001]]),
            mean([s.delivery_bps for s in samples_by_port[10002]]),
            mean([s.delivery_bps for s in samples_by_port[10003]]),
        )
        if any(v is None for v in rate_tuple):
            continue
        rates = tuple(float(v) for v in rate_tuple)  # type: ignore[arg-type]

        for spec in specs:
            if spec.matches(cc_list, delays):
                spec.rows.append((delays, rates))
                break
    return specs


def write_delay_file(path: Path, spec: DatasetSpec) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered_rows = sorted(spec.rows, key=lambda row: row[0])
    with path.open("w", encoding="utf-8") as f:
        for delays, rates in ordered_rows:
            fields = [
                *spec.cc_tuple,
                str(delays[0]),
                str(delays[1]),
                str(delays[2]),
                str(delays[3]),
                f"{rates[0]:.2f}",
                f"{rates[1]:.2f}",
                f"{rates[2]:.2f}",
                f"{rates[3]:.2f}",
            ]
            f.write(", ".join(fields) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build four-flow delay-sensitivity datasets from raw ss logs.")
    parser.add_argument("--input-root", type=Path, default=Path("results/four_flow_delay"))
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    specs = collect_delay_rows(args.input_root)
    for spec in specs:
        out_path = args.output_dir / spec.output_name
        write_delay_file(out_path, spec)
        print(f"Wrote {out_path} with {len(spec.rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

