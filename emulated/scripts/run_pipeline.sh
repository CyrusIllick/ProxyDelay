#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SPEC_PATH=""
OUTPUT_ROOT="${OUTPUT_ROOT:-${ROOT_DIR}/results}"
DATA_DIR="${DATA_DIR:-${ROOT_DIR}/data}"
FIGURES_DIR="${FIGURES_DIR:-${ROOT_DIR}/figures}"
RUN_TESTS="${RUN_TESTS:-1}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --spec)
      SPEC_PATH="$2"
      shift 2
      ;;
    --output-root)
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${SPEC_PATH}" ]]; then
  echo "Usage: ./scripts/run_pipeline.sh --spec <path/to/spec.json> [--output-root <path>]" >&2
  exit 1
fi

if [[ "${RUN_TESTS}" == "1" ]]; then
  python3 "${ROOT_DIR}/scripts/run_from_spec.py" \
    --spec "${SPEC_PATH}" \
    --output-root "${OUTPUT_ROOT}"
fi

EXPERIMENT_NAME="$(python3 - "${SPEC_PATH}" <<'PY'
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as f:
    spec = json.load(f)
print(spec['experiment_name'])
PY
)"

RESULTS_ROOT="${OUTPUT_ROOT}/${EXPERIMENT_NAME}"

python3 "${ROOT_DIR}/scripts/build_timeseries_dataset.py" \
  --input-root "${RESULTS_ROOT}" \
  --output-dir "${DATA_DIR}"

if [[ -n "${PLOT_RUN_DIR:-}" ]]; then
  python3 "${ROOT_DIR}/scripts/plot_single_run_timeseries.py" \
    --run-dir "${PLOT_RUN_DIR}" \
    --data-dir "${DATA_DIR}" \
    --output-dir "${FIGURES_DIR}"
else
  FIRST_RUN_ID="$(python3 - "${DATA_DIR}/runs_manifest.csv" <<'PY'
import csv, sys
path = sys.argv[1]
with open(path, 'r', encoding='utf-8', newline='') as f:
    reader = csv.DictReader(f)
    first = next(reader, None)
if first is None:
    raise SystemExit('No runs in manifest')
print(first['run_id'])
PY
)"

  python3 "${ROOT_DIR}/scripts/plot_single_run_timeseries.py" \
    --run-id "${FIRST_RUN_ID}" \
    --data-dir "${DATA_DIR}" \
    --output-dir "${FIGURES_DIR}"
fi

echo "Pipeline complete."
echo "Results: ${RESULTS_ROOT}"
echo "Data: ${DATA_DIR}"
echo "Figures: ${FIGURES_DIR}"
