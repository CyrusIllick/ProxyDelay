# Emulated Exploration Framework

This folder provides a generalized emulated experimentation framework for extending the work from
*Making Congestion Control Algorithms Insensitive to Underlying Propagation Delays*.

Use this when you want to run new emulated studies (custom CCA sets, custom sweeps, custom durations).
For paper-result reproduction, use `../emulated-repro/`.

## Layout

- `engines/`
  - `nsperf_two_flows.py`
  - `nsperf_four_flows_het.py`
  - `save_params.py`
- `scripts/`
  - `run_from_spec.py`
  - `build_timeseries_dataset.py`
  - `plot_single_run_timeseries.py`
  - `run_pipeline.sh`
  - `ss_utils.py`
- `specs/examples/`
  - `quickstart_two_flow.json`
  - `two_flow_custom_ccas.json`
  - `four_flow_custom_ccas.json`
- `results/`, `data/`, `figures/` (generated outputs)

## Prerequisites

- Linux host with root privileges.
- Namespace + traffic control tooling: `ip netns`, `tc`, `ss`, `sysctl`, `netperf`, `netserver`.
- Python 3.10+.
- Python packages from `requirements.txt`.

Install Python dependencies:

```bash
pip install -r requirements.txt
```

### External Binary Paths (Important)

The emulation engines expect iproute2 binaries at:

- `/root/iproute2/iproute2/ip/ip`
- `/root/iproute2/iproute2/misc/ss`
- `/root/iproute2/iproute2/tc/tc`

These paths follow the Google BBR workflow (`google/bbr`) used in the original setup.
If your environment uses different paths, update `IP_PATH`, `SS_PATH`, and `TC_PATH` in:

- `engines/nsperf_two_flows.py`
- `engines/nsperf_four_flows_het.py`

## JSON Spec Contract (v1)

Required top-level fields:

- `experiment_name: str`
- `flow_mode: "two_flow" | "four_flow"`
- `ccas: list[str]`
- `runtime: {duration_sec:int, reps:int, skip_existing:bool}`
- `network: {bw_mbit:float, base_rtt_ms:float, bdp_of_buf:float, loss_pct:float, flow_start_interval_sec:float, qdisc:str, pcap_bytes:int, cmd:str}`
- `sweep: {a_delay_ms:list[int], b_delay_ms:list[int], c_delay_ms:list[int], d_delay_ms:list[int]}`
- `proxy: {proxy_on_values:list[int], proxy_init_ms:float}`

Validation rules:

- `flow_mode=two_flow` requires exactly 2 CCAs.
- `flow_mode=four_flow` requires exactly 4 CCAs.
- `proxy_on_values` entries must be `0` or `1`.
- `c_delay_ms`/`d_delay_ms` are required only for four-flow mode.
- For four-flow specs, proxy defaults to `[0]` if omitted.

## Commands

Run plan only (no side effects):

```bash
python3 scripts/run_from_spec.py --spec specs/examples/quickstart_two_flow.json --dry-run
```

Run experiments from spec:

```bash
python3 scripts/run_from_spec.py --spec specs/examples/quickstart_two_flow.json
```

Build dataset from raw results:

```bash
python3 scripts/build_timeseries_dataset.py --input-root results/quickstart_two_flow --output-dir data
```

Plot a single run (by run id):

```bash
python3 scripts/plot_single_run_timeseries.py --run-id <run_id> --data-dir data --output-dir figures
```

Plot a single run (by run directory):

```bash
python3 scripts/plot_single_run_timeseries.py --run-dir <absolute_run_dir> --data-dir data --output-dir figures
```

End-to-end pipeline:

```bash
./scripts/run_pipeline.sh --spec specs/examples/quickstart_two_flow.json
```

Optional pipeline controls:

- `RUN_TESTS=0`: skip execution, rebuild dataset/plots from existing results.
- `PLOT_RUN_DIR=/abs/path/to/run`: choose plot target run directory.
- `OUTPUT_ROOT=/abs/path`: override results root.
- `DATA_DIR=/abs/path`, `FIGURES_DIR=/abs/path`: override output locations.

## Output Files

`build_timeseries_dataset.py` writes:

- `data/runs_manifest.csv`
  - `run_id, run_dir, flow_mode, rep, proxy_on, a_delay, b_delay, c_delay, d_delay, ccas`
- `data/timeseries.csv`
  - `run_id, t_sec, flow_index, port, cca, delivery_mbps, cwnd, rtt_ms, extra_acked`

`plot_single_run_timeseries.py` writes:

- `<run_id>_delivery_rate.png`
- `<run_id>_summary.txt`

The summary includes per-flow mean throughput, aggregate mean throughput, and Jain fairness index.

## Extension Notes

- Two-flow engine supports heterogeneous CCA competition directly:
  - flow A (`srv`) uses `ccas[0]`
  - flow B (`srvb`) uses `ccas[1]`
- Four-flow engine remains fixed to four senders/flows (one CCA per flow).
