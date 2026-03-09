#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]
ENGINE_DIR = ROOT_DIR / "engines"


@dataclass
class RunConfig:
    flow_mode: str
    rep: int
    proxy_on: int
    ccas: List[str]
    outdir: Path
    a_delay: int
    b_delay: int
    c_delay: int
    d_delay: int


def _require_keys(data: Dict[str, Any], keys: Sequence[str], ctx: str) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ValueError(f"Missing keys in {ctx}: {', '.join(missing)}")


def _to_int_list(values: Any, field_name: str) -> List[int]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{field_name} must be a non-empty list")
    out: List[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} entries must be numeric")
        out.append(int(value))
    return out


def _to_binary_int_list(values: Any, field_name: str) -> List[int]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{field_name} must be a non-empty list")
    out: List[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} entries must be integers (0 or 1)")
        if int(value) != value:
            raise ValueError(f"{field_name} entries must be integers (0 or 1)")
        int_value = int(value)
        if int_value not in (0, 1):
            raise ValueError(f"{field_name} must contain only 0 or 1")
        out.append(int_value)
    return out


def _validate_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    _require_keys(spec, ["experiment_name", "flow_mode", "ccas", "runtime", "network", "sweep"], "spec")

    experiment_name = spec["experiment_name"]
    flow_mode = spec["flow_mode"]
    ccas = spec["ccas"]

    if not isinstance(experiment_name, str) or not experiment_name.strip():
        raise ValueError("experiment_name must be a non-empty string")
    if flow_mode not in {"two_flow", "four_flow"}:
        raise ValueError("flow_mode must be 'two_flow' or 'four_flow'")
    if not isinstance(ccas, list) or not all(isinstance(x, str) and x.strip() for x in ccas):
        raise ValueError("ccas must be a non-empty list of algorithm names")

    if flow_mode == "two_flow" and len(ccas) != 2:
        raise ValueError("two_flow experiments require exactly 2 CCAs")
    if flow_mode == "four_flow" and len(ccas) != 4:
        raise ValueError("four_flow experiments require exactly 4 CCAs")

    runtime = spec["runtime"]
    network = spec["network"]
    sweep = spec["sweep"]

    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    if not isinstance(network, dict):
        raise ValueError("network must be an object")
    if not isinstance(sweep, dict):
        raise ValueError("sweep must be an object")

    _require_keys(runtime, ["duration_sec", "reps", "skip_existing"], "runtime")
    _require_keys(
        network,
        [
            "bw_mbit",
            "base_rtt_ms",
            "bdp_of_buf",
            "loss_pct",
            "flow_start_interval_sec",
            "qdisc",
            "pcap_bytes",
            "cmd",
        ],
        "network",
    )
    _require_keys(sweep, ["a_delay_ms", "b_delay_ms"], "sweep")

    duration_sec = int(runtime["duration_sec"])
    reps = int(runtime["reps"])
    if not isinstance(runtime["skip_existing"], bool):
        raise ValueError("runtime.skip_existing must be true or false")
    skip_existing = runtime["skip_existing"]
    if duration_sec <= 0:
        raise ValueError("runtime.duration_sec must be > 0")
    if reps <= 0:
        raise ValueError("runtime.reps must be > 0")

    a_delays = _to_int_list(sweep["a_delay_ms"], "sweep.a_delay_ms")
    b_delays = _to_int_list(sweep["b_delay_ms"], "sweep.b_delay_ms")

    if flow_mode == "four_flow":
        _require_keys(sweep, ["c_delay_ms", "d_delay_ms"], "sweep (four_flow)")
        c_delays = _to_int_list(sweep["c_delay_ms"], "sweep.c_delay_ms")
        d_delays = _to_int_list(sweep["d_delay_ms"], "sweep.d_delay_ms")
    else:
        c_delays = [0]
        d_delays = [0]

    proxy_cfg = spec.get("proxy")
    if flow_mode == "two_flow":
        if not isinstance(proxy_cfg, dict):
            raise ValueError("two_flow experiments require proxy configuration")
        _require_keys(proxy_cfg, ["proxy_on_values", "proxy_init_ms"], "proxy")
    else:
        if proxy_cfg is None:
            proxy_cfg = {"proxy_on_values": [0], "proxy_init_ms": 0}
        if not isinstance(proxy_cfg, dict):
            raise ValueError("proxy must be an object when provided")
        proxy_cfg.setdefault("proxy_on_values", [0])
        proxy_cfg.setdefault("proxy_init_ms", 0)

    proxy_values = _to_binary_int_list(proxy_cfg["proxy_on_values"], "proxy.proxy_on_values")

    normalized = {
        "experiment_name": experiment_name.strip(),
        "flow_mode": flow_mode,
        "ccas": [cca.strip() for cca in ccas],
        "runtime": {
            "duration_sec": duration_sec,
            "reps": reps,
            "skip_existing": skip_existing,
        },
        "network": {
            "bw_mbit": float(network["bw_mbit"]),
            "base_rtt_ms": float(network["base_rtt_ms"]),
            "bdp_of_buf": float(network["bdp_of_buf"]),
            "loss_pct": float(network["loss_pct"]),
            "flow_start_interval_sec": float(network["flow_start_interval_sec"]),
            "qdisc": str(network["qdisc"]),
            "pcap_bytes": int(network["pcap_bytes"]),
            "cmd": str(network["cmd"]),
        },
        "proxy": {
            "proxy_on_values": proxy_values,
            "proxy_init_ms": float(proxy_cfg["proxy_init_ms"]),
        },
        "sweep": {
            "a_delay_ms": a_delays,
            "b_delay_ms": b_delays,
            "c_delay_ms": c_delays,
            "d_delay_ms": d_delays,
        },
    }
    return normalized


def _cca_tag(ccas: Sequence[str]) -> str:
    return "_vs_".join(ccas)


def _compute_buffer_packets(bw_mbit: float, base_rtt_ms: float, bdp_of_buf: float) -> int:
    pkts = int(bw_mbit * 1_000_000 * base_rtt_ms / 1000.0 / (1514 * 8) * bdp_of_buf)
    return max(pkts, 1)


def _build_runs(spec: Dict[str, Any], output_root: Path) -> List[RunConfig]:
    runs: List[RunConfig] = []

    experiment_root = output_root / spec["experiment_name"]
    flow_mode = spec["flow_mode"]
    ccas = spec["ccas"]
    ccas_tag = _cca_tag(ccas)

    reps = spec["runtime"]["reps"]
    proxy_values = spec["proxy"]["proxy_on_values"]
    sweep = spec["sweep"]

    if flow_mode == "two_flow":
        for rep in range(1, reps + 1):
            for proxy_on in proxy_values:
                for a_delay in sweep["a_delay_ms"]:
                    for b_delay in sweep["b_delay_ms"]:
                        outdir = (
                            experiment_root
                            / "two_flow"
                            / ccas_tag
                            / f"proxy_{proxy_on}"
                            / f"rep_{rep}"
                            / f"a_{a_delay}_b_{b_delay}"
                        )
                        runs.append(
                            RunConfig(
                                flow_mode=flow_mode,
                                rep=rep,
                                proxy_on=proxy_on,
                                ccas=list(ccas),
                                outdir=outdir,
                                a_delay=int(a_delay),
                                b_delay=int(b_delay),
                                c_delay=0,
                                d_delay=0,
                            )
                        )
    else:
        for rep in range(1, reps + 1):
            for proxy_on in proxy_values:
                for a_delay in sweep["a_delay_ms"]:
                    for b_delay in sweep["b_delay_ms"]:
                        for c_delay in sweep["c_delay_ms"]:
                            for d_delay in sweep["d_delay_ms"]:
                                outdir = (
                                    experiment_root
                                    / "four_flow"
                                    / ccas_tag
                                    / f"proxy_{proxy_on}"
                                    / f"rep_{rep}"
                                    / f"a_{a_delay}_b_{b_delay}_c_{c_delay}_d_{d_delay}"
                                )
                                runs.append(
                                    RunConfig(
                                        flow_mode=flow_mode,
                                        rep=rep,
                                        proxy_on=proxy_on,
                                        ccas=list(ccas),
                                        outdir=outdir,
                                        a_delay=int(a_delay),
                                        b_delay=int(b_delay),
                                        c_delay=int(c_delay),
                                        d_delay=int(d_delay),
                                    )
                                )

    return runs


def _env_for_run(spec: Dict[str, Any], run: RunConfig, buf_pkts: int) -> Dict[str, str]:
    network = spec["network"]
    proxy = spec["proxy"]

    if run.flow_mode == "two_flow":
        cc_str = f"{run.ccas[0]}:1,{run.ccas[1]}:1"
    else:
        cc_str = ",".join(f"{cca}:1" for cca in run.ccas)

    env = {
        "cc": cc_str,
        "rep": str(run.rep),
        "bw": str(network["bw_mbit"]),
        "proxy_on": str(run.proxy_on),
        "proxy_init": str(proxy["proxy_init_ms"]),
        "rtt": str(network["base_rtt_ms"]),
        "a_delay": str(run.a_delay),
        "b_delay": str(run.b_delay),
        "buf": str(buf_pkts),
        "qdisc": str(network["qdisc"]),
        "loss": str(network["loss_pct"]),
        "dur": str(spec["runtime"]["duration_sec"]),
        "pcap": str(network["pcap_bytes"]),
        "cmd": str(network["cmd"]),
        "outdir": str(run.outdir),
        "interval": str(network["flow_start_interval_sec"]),
    }

    if run.flow_mode == "four_flow":
        env["c_delay"] = str(run.c_delay)
        env["d_delay"] = str(run.d_delay)
        env["extra_delay"] = "0"

    return env


def _run_subprocess(command: List[str], env: Dict[str, str], output_path: Path) -> int:
    parent_env = os.environ.copy()
    parent_env.update(env)

    with output_path.open("w", encoding="utf-8") as f:
        proc = subprocess.run(command, env=parent_env, stdout=f, stderr=subprocess.STDOUT)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run generalized emulated experiments from JSON spec")
    parser.add_argument("--spec", type=Path, required=True, help="Path to experiment spec JSON")
    parser.add_argument("--output-root", type=Path, default=Path("results"), help="Root output directory")
    parser.add_argument("--dry-run", action="store_true", help="Print run plan without executing")
    args = parser.parse_args()

    with args.spec.open("r", encoding="utf-8") as f:
        raw_spec = json.load(f)
    spec = _validate_spec(raw_spec)

    experiment_root = args.output_root / spec["experiment_name"]
    runs = _build_runs(spec, args.output_root)
    buf_pkts = _compute_buffer_packets(
        spec["network"]["bw_mbit"],
        spec["network"]["base_rtt_ms"],
        spec["network"]["bdp_of_buf"],
    )

    print(f"Experiment: {spec['experiment_name']}")
    print(f"Flow mode: {spec['flow_mode']}")
    print(f"Output root: {experiment_root}")
    print(f"Computed buffer (packets): {buf_pkts}")
    print(f"Planned runs: {len(runs)}")

    if args.dry_run:
        for run in runs[:5]:
            engine = "nsperf_two_flows.py" if run.flow_mode == "two_flow" else "nsperf_four_flows_het.py"
            print(
                "[dry-run] "
                f"rep={run.rep} proxy={run.proxy_on} delays=({run.a_delay},{run.b_delay},{run.c_delay},{run.d_delay}) "
                f"out={run.outdir} cmd=python3 {ENGINE_DIR / engine} stream"
            )
        if len(runs) > 5:
            print(f"[dry-run] ... {len(runs) - 5} additional runs omitted")
        return 0

    experiment_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.spec, experiment_root / "spec.used.json")

    completed = 0
    skipped = 0
    failed = 0

    for run in runs:
        test_params_path = run.outdir / "test_params.txt"
        if spec["runtime"]["skip_existing"] and test_params_path.exists():
            skipped += 1
            continue

        run.outdir.mkdir(parents=True, exist_ok=True)
        env = _env_for_run(spec, run, buf_pkts)

        if run.flow_mode == "two_flow":
            engine_path = ENGINE_DIR / "nsperf_two_flows.py"
        else:
            if len(run.ccas) != 4:
                raise ValueError("four_flow mode requires exactly 4 CCAs")
            engine_path = ENGINE_DIR / "nsperf_four_flows_het.py"

        print(
            f"[run] rep={run.rep} proxy={run.proxy_on} "
            f"delays=({run.a_delay},{run.b_delay},{run.c_delay},{run.d_delay})"
        )

        rc = _run_subprocess(
            [sys.executable, str(engine_path), "stream"],
            env,
            run.outdir / "nsperf.out.txt",
        )
        if rc != 0:
            print(f"[fail] nsperf exited with status {rc}: {run.outdir}", file=sys.stderr)
            failed += 1
            continue

        rc = _run_subprocess(
            [sys.executable, str(ENGINE_DIR / "save_params.py")],
            env,
            test_params_path,
        )
        if rc != 0:
            print(f"[fail] save_params exited with status {rc}: {run.outdir}", file=sys.stderr)
            failed += 1
            continue

        completed += 1

    print(f"Done. completed={completed} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
