#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RESULTS_ROOT="${RESULTS_ROOT:-${ROOT_DIR}/results/quickstart}"
TWO_FLOW_RESULTS="${TWO_FLOW_RESULTS:-${RESULTS_ROOT}/two_flow_delta}"
FOUR_FLOW_RESULTS="${FOUR_FLOW_RESULTS:-${RESULTS_ROOT}/four_flow_delay}"

DATA_DIR="${DATA_DIR:-${ROOT_DIR}/data/quickstart}"
FIGURES_DIR="${FIGURES_DIR:-${ROOT_DIR}/figures/quickstart}"
RUN_TESTS="${RUN_TESTS:-1}"

if [[ "${RUN_TESTS}" == "1" ]]; then
  OUTPUT_ROOT="${TWO_FLOW_RESULTS}" "${ROOT_DIR}/scripts/run_two_flow_delta_quick_tests.sh"
  OUTPUT_ROOT="${FOUR_FLOW_RESULTS}" "${ROOT_DIR}/scripts/run_four_flow_delay_quick_tests.sh"
fi

python3 "${ROOT_DIR}/scripts/build_two_flow_delta_dataset.py" \
  --input-root "${TWO_FLOW_RESULTS}" \
  --output-dir "${DATA_DIR}"

python3 "${ROOT_DIR}/scripts/build_delay_dataset.py" \
  --input-root "${FOUR_FLOW_RESULTS}" \
  --output-dir "${DATA_DIR}"

python3 "${ROOT_DIR}/scripts/plot_two_flow_delta_sensitivity.py" \
  --input-dir "${DATA_DIR}" \
  --output-dir "${FIGURES_DIR}"

python3 "${ROOT_DIR}/scripts/plot_delay_sensitivity.py" \
  --input-dir "${DATA_DIR}" \
  --output-dir "${FIGURES_DIR}"

echo "Quickstart complete."
echo "Data: ${DATA_DIR}"
echo "Figures: ${FIGURES_DIR}"
