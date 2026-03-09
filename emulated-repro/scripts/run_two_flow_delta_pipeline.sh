#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_ROOT="${RESULTS_ROOT:-${ROOT_DIR}/results/two_flow_delta}"
RUN_TESTS="${RUN_TESTS:-1}"

if [[ "${RUN_TESTS}" == "1" ]]; then
  OUTPUT_ROOT="${RESULTS_ROOT}" "${ROOT_DIR}/scripts/run_two_flow_delta_tests.sh"
fi

python3 "${ROOT_DIR}/scripts/build_two_flow_delta_dataset.py" \
  --input-root "${RESULTS_ROOT}" \
  --output-dir "${ROOT_DIR}/data"

python3 "${ROOT_DIR}/scripts/plot_two_flow_delta_sensitivity.py" \
  --input-dir "${ROOT_DIR}/data" \
  --output-dir "${ROOT_DIR}/figures"
