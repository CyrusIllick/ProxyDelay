# Real-World Testing Framework 

This folder contains real-world test workflow that supports methodological replication and extension of results shown in *Making Congestion Control Algorithms Insensitive to Underlying Propagation Delays"*. 

## Included Modules

- `real_world_testing.py`: interactive test orchestration
- `real_world_helper.py`: remote command execution and test utilities
- `round_trip_time_stabilization_helper.py`: delay/qdisc setup and RTT stabilization
- `real_world_noise_helper.py`: optional background noise generation
- `compute_engine.py`: GCP instance lifecycle
- `ec2_helper.py`: AWS instance lifecycle
- `figure_parser.py`: parse ss output, generate graphs/statistics
- `plot_existing_results.py`: regenerate graphs/statistics from an existing timestamp
- `summary_helper.py`: write test summary
- `log.py`: lightweight logger
- `config_loader.py`: config loading/validation

## Prerequisites

- Python 3.10+
- `netperf`, `netserver`, `iperf3`, `tc`, `ss` available on target hosts
- SSH access from the controller machine to all participating hosts
- Cloud credentials configured on the controller machine:
  - GCP: Application Default Credentials (`gcloud auth application-default login`)
  - AWS: standard AWS credentials chain (env vars, shared credentials, or profile)

Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Controller Setup (Cloud Access)

Install and initialize Google Cloud CLI on the controller machine:

```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud init
gcloud auth application-default login
```

Also configure AWS credentials/profile on the same controller machine for `boto3`.

## Host/Image Preparation (Required Before Running)

`real_world_testing.py` assumes hosts (local and cloud images) are already prepared. It does not install system tooling after instance creation.

For each host/image used as `netserver` or `netperf`, ensure:

- SSH login works for the configured username.
- `netperf`, `netserver`, `iperf3`, `tc`, and `ss` are installed.
- Required qdisc/kernel features are available.

Minimum Ubuntu baseline:

```bash
apt update && \
yes | apt install openssh-server netperf iperf3 && \
service ssh restart
```

Important path assumption in current code:

- `real_world_helper.py` and `round_trip_time_stabilization_helper.py` call:
  - `/root/iproute2/iproute2/misc/ss`

Use the following approach: prepare images with the same Google BBR/iproute2 workflow used for emulated experiments.

## Config Setup

Create local config files from templates:

```bash
cp config/topology.example.json config/topology.json
cp config/cloud.example.json config/cloud.json
```

Then edit both files.

### `config/topology.json`

Define:

- `usernames`: SSH usernames offered in the interactive menu
- `gcp_zones`, `aws_zones`: cloud zones/regions available for test placement
- `local_servers`: your on-prem endpoints (roles `netserver` and/or `netperf`)
- `congestion_control_algorithms`: allowed CC options in menus
- interface names (`cloud_interface_name`, `aws_instance_interface_name`)
- optional `ssh_private_key_path`
- `report_root` output location

### `config/cloud.json`

Define:

- GCP project/image/machine type for auto-provisioned instances
- AWS region/image/instance type/key profile settings
- image IDs/names that point to your already-prepared images


## Topology Requirements

At minimum, you need:

1. One netserver endpoint (cloud or local)
2. One or more netperf endpoints (cloud, local, or mixed)
3. SSH reachability from controller to all endpoints
4. Network interface names in config matching actual host NICs

Optional:

- A local noise sender + cloud noise receiver for iperf3 cross-traffic

## Run One Test And Plot Results

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create local config files:

```bash
cp config/topology.example.json config/topology.json
cp config/cloud.example.json config/cloud.json
```

3. Fill in `config/topology.json` and `config/cloud.json` with your own environment details.
4. Ensure cloud credentials are available (`gcloud auth application-default login` and AWS credentials/profile).
5. Start a test run:

```bash
python3 real_world_testing.py
```

Equivalent wrapper command:

```bash
./run_real_world_tests.sh
```

6. Follow prompts in the terminal for:

1. selecting username, flow direction, and duration
2. choosing netserver/netperf placements
3. assigning congestion control and target RTTs
4. optional noise configuration
5. cloud provisioning and execution
6. report/graph/stat generation

7. After completion, outputs are under `report_root` (default `reports/`) in a timestamp directory:

- `<report_root>/<timestamp>/summary.txt`
- `<report_root>/<timestamp>/statistics.txt`
- `<report_root>/<timestamp>/graphs/*.png`
- `<report_root>/<timestamp>/<platform>/<zone>/*.txt` (raw parsed `ss` logs)

## Re-Plot Existing Results

If raw per-instance text logs already exist for a timestamp, you can regenerate graphs/statistics without rerunning tests:

```bash
python3 plot_existing_results.py --timestamp <timestamp>
```

Optional custom report root:

```bash
python3 plot_existing_results.py --timestamp <timestamp> --report-root /path/to/reports
```

## Optional Config Paths

To use non-default config paths:

```bash
REAL_WORLD_TOPOLOGY_CONFIG=/path/to/topology.json \
REAL_WORLD_CLOUD_CONFIG=/path/to/cloud.json \
python3 real_world_testing.py
```
