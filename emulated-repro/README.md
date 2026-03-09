# Emulated Reproduction 

This folder contains emulated-only workflow to:

1. Run the emulated tests.
2. Convert raw logs into `.txt` datasets used by the figures.
3. Generate the figures from Python scripts.

It is the workflow used to reproduce the emulated experiments from
*"Making Congestion Control Algorithms Insensitive to Underlying Propagation Delays"*.

## Layout

- `engines/`
  - `nsperf_two_flows.py`
  - `nsperf_four_flows_het.py`
  - `save_params.py`
- `scripts/`
  - `run_two_flow_delta_tests.sh`
  - `run_two_flow_delta_quick_tests.sh`
  - `run_four_flow_delay_tests.sh`
  - `run_four_flow_delay_quick_tests.sh`
  - `build_two_flow_delta_dataset.py`
  - `build_delay_dataset.py`
  - `plot_two_flow_delta_sensitivity.py`
  - `plot_delay_sensitivity.py`
  - `run_two_flow_delta_pipeline.sh`
  - `run_delay_pipeline.sh`
  - `run_quickstart_pipeline.sh`
  - `ss_utils.py`
- `data/` generated `.txt` files
- `figures/` generated plots
- `results/` raw test outputs (created by run scripts)

## Prerequisites

- Linux host with root privileges.
- `ip netns`, `tc`, `ss`, `sysctl`, `netperf`, `netserver`.
- Python 3.10+.
- Python packages from `requirements.txt`.

## Note

The setup documented below provides one validated procedure for preparing a Linux kernel with BBRv3 support.
If installation issues arise, follow the official instructions in the Google BBR repository:
https://github.com/google/bbr/tree/v3.
Experiments must be run as `root`.

## Environment Setup (Required)

The emulation engines expect `ip`, `ss`, and `tc` binaries from the Google BBR/iproute2 workflow.

### 1) Prepare an Ubuntu host

Use Ubuntu 22.04 (or equivalent Linux) with root privileges.

Install baseline packages:

```bash
apt update && \
yes | apt install openssh-server netperf iperf3 && \
service ssh restart
```

Optional (for long setup sessions):

```bash
yes Y | apt update && apt install screen && screen -R kernel
```

### 2) Build/install Google BBR kernel tree (v3 branch)

```bash
yes Y | apt-get install git fakeroot build-essential ncurses-dev xz-utils libssl-dev bc flex libelf-dev bison dwarves plocate pcmemtest && \
updatedb && \
git clone --branch v3 --single-branch https://github.com/google/bbr && \
cd bbr && \
cp -v /boot/config-$(uname -r) .config
```

In `make menuconfig`:

- `Networking support -> Networking Options -> TCP: advanced congestion control`
- Enable the congestion control algorithms you want available.

Then:

```bash
scripts/config --disable SYSTEM_TRUSTED_KEYS && \
scripts/config --disable SYSTEM_REVOCATION_KEYS
```

Set `CONFIG_DEBUG_INFO_BTF=n` in `.config`, then:

```bash
make && \
make modules_install && \
make install
```

Set the new kernel as default boot entry and reboot (example):

```bash
KERNELVER=6.4.0+
MID=$(awk '/Advanced options for Ubuntu/{print $(NF-1)}' /boot/grub/grub.cfg | cut -d\' -f2)
KID=$(awk "/with Linux $KERNELVER/"'{print $(NF-1)}' /boot/grub/grub.cfg | cut -d\' -f2 | head -n1)

cat > /etc/default/grub.d/95-savedef.cfg <<EOF
GRUB_DEFAULT=saved
GRUB_SAVEDEFAULT=true
EOF
grub-editenv /boot/grub/grubenv set saved_entry="${MID}>${KID}"
update-grub
reboot
```

### 3) Verify emulation binary paths

The engines use these default paths:

- `/root/iproute2/iproute2/ip/ip`
- `/root/iproute2/iproute2/misc/ss`
- `/root/iproute2/iproute2/tc/tc`

These are set in:

- `engines/nsperf_two_flows.py`
- `engines/nsperf_four_flows_het.py`

If your binaries are in different locations, update `IP_PATH`, `SS_PATH`, and `TC_PATH` in both files.

### 4) Install Python dependencies

```bash
pip install -r requirements.txt
```

## Quick Start 

Before running the full experiments, run a short end-to-end check that ensures both emulated engines, parameter capture,
dataset builders, and plotting scripts are working properly:

```bash
./scripts/run_quickstart_pipeline.sh
```

Default behavior:

- Runs a reduced two-flow delta-sensitivity sweep at `6ms` and `20ms`.
- Runs one representative four-flow test for each delay family.
- Builds all `.txt` datasets and writes quickstart figures.
- Uses output paths:
  - `results/quickstart/`
  - `data/quickstart/`
  - `figures/quickstart/`

Useful overrides:

- `RUN_TESTS=0 ./scripts/run_quickstart_pipeline.sh`
  - Skip emulation runs and only rebuild datasets/figures from existing quickstart results.
- `QUICK_DELAYS=6,12,20 ./scripts/run_two_flow_delta_quick_tests.sh`
  - Change the reduced two-flow delay set.
- `REPS=2 ./scripts/run_four_flow_delay_quick_tests.sh`
  - Repeat each quick four-flow case more than once.

## Delay-Sensitivity (Two-Flow) experiments 

Run tests (long-running):

```bash
./scripts/run_two_flow_delta_tests.sh
```

Build datasets:

```bash
python3 scripts/build_two_flow_delta_dataset.py \
  --input-root results/two_flow_delta \
  --output-dir data
```

Generate plots:

```bash
python3 scripts/plot_two_flow_delta_sensitivity.py \
  --input-dir data \
  --output-dir figures
```

Or run all three:

```bash
./scripts/run_two_flow_delta_pipeline.sh
```

This will run for hours and will produce figure 4 in *"Making Congestion Control Algorithms Insensitive to Underlying Propagation Delays"*

## Delay-Sensitivity (Four-Flow) experiments 

Run tests (long-running):

```bash
./scripts/run_four_flow_delay_tests.sh
```

Build datasets:

```bash
python3 scripts/build_delay_dataset.py \
  --input-root results/four_flow_delay \
  --output-dir data
```

Generate plots:

```bash
python3 scripts/plot_delay_sensitivity.py \
  --input-dir data \
  --output-dir figures
```

Or run all three:

```bash
./scripts/run_delay_pipeline.sh
```

This will run for hours and will produce figure 7 in *"Making Congestion Control Algorithms Insensitive to Underlying Propagation Delays"*
