#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FULL_RUNNER="${ROOT_DIR}/scripts/run_two_flow_delta_tests.sh"

OUTPUT_ROOT="${OUTPUT_ROOT:-${ROOT_DIR}/results/quickstart/two_flow_delta}"
QUICK_DELAYS="${QUICK_DELAYS:-6,20}"

CC_LIST="${CC_LIST:-bbr1,bbr}"
PROXY_VALUES="${PROXY_VALUES:-0,1}"
BW_MBIT="${BW_MBIT:-200}"
BASE_RTT_MS="${BASE_RTT_MS:-10}"
BDP_OF_BUF="${BDP_OF_BUF:-50}"
PROXY_INIT_MS="${PROXY_INIT_MS:-100}"
FLOW_START_INTERVAL_SEC="${FLOW_START_INTERVAL_SEC:-0}"
LOSS_PCT="${LOSS_PCT:-0}"
DURATION_SEC="${DURATION_SEC:-20}"
PCAP_BYTES="${PCAP_BYTES:-0}"
QDISC="${QDISC:-}"
CMD="${CMD:-}"
SKIP_EXISTING="${SKIP_EXISTING:-1}"
TUNE_SOCKET_BUFFERS="${TUNE_SOCKET_BUFFERS:-1}"

IFS=',' read -r -a DELAYS <<<"${QUICK_DELAYS}"
if [[ ${#DELAYS[@]} -eq 0 ]]; then
  echo "QUICK_DELAYS is empty." >&2
  exit 1
fi

mkdir -p "${OUTPUT_ROOT}"

for delay in "${DELAYS[@]}"; do
  delay="$(echo "${delay}" | xargs)"
  if [[ -z "${delay}" ]]; then
    continue
  fi
  if ! [[ "${delay}" =~ ^[0-9]+$ ]]; then
    echo "Invalid delay value in QUICK_DELAYS: ${delay}" >&2
    exit 1
  fi

  echo "[quick-two-flow] Running square-delay sweep at ${delay}ms"
  OUTPUT_ROOT="${OUTPUT_ROOT}" \
    CC_LIST="${CC_LIST}" \
    PROXY_VALUES="${PROXY_VALUES}" \
    DELAY_MIN="${delay}" \
    DELAY_MAX="${delay}" \
    DELAY_STEP="1" \
    BW_MBIT="${BW_MBIT}" \
    BASE_RTT_MS="${BASE_RTT_MS}" \
    BDP_OF_BUF="${BDP_OF_BUF}" \
    PROXY_INIT_MS="${PROXY_INIT_MS}" \
    FLOW_START_INTERVAL_SEC="${FLOW_START_INTERVAL_SEC}" \
    LOSS_PCT="${LOSS_PCT}" \
    DURATION_SEC="${DURATION_SEC}" \
    PCAP_BYTES="${PCAP_BYTES}" \
    QDISC="${QDISC}" \
    CMD="${CMD}" \
    SKIP_EXISTING="${SKIP_EXISTING}" \
    TUNE_SOCKET_BUFFERS="${TUNE_SOCKET_BUFFERS}" \
    "${FULL_RUNNER}"
done

echo "Done: ${OUTPUT_ROOT}"
