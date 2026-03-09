#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_DIR="${ROOT_DIR}/engines"

OUTPUT_ROOT="${OUTPUT_ROOT:-${ROOT_DIR}/results/two_flow_delta}"
CC_LIST="${CC_LIST:-bbr1,bbr}"
PROXY_VALUES="${PROXY_VALUES:-0,1}"

DELAY_MIN="${DELAY_MIN:-6}"
DELAY_MAX="${DELAY_MAX:-54}"
DELAY_STEP="${DELAY_STEP:-1}"

BW_MBIT="${BW_MBIT:-200}"
BASE_RTT_MS="${BASE_RTT_MS:-10}"
BDP_OF_BUF="${BDP_OF_BUF:-50}"
PROXY_INIT_MS="${PROXY_INIT_MS:-100}"
FLOW_START_INTERVAL_SEC="${FLOW_START_INTERVAL_SEC:-0}"
LOSS_PCT="${LOSS_PCT:-0}"
DURATION_SEC="${DURATION_SEC:-120}"
PCAP_BYTES="${PCAP_BYTES:-0}"
QDISC="${QDISC:-}"
CMD="${CMD:-}"
SKIP_EXISTING="${SKIP_EXISTING:-1}"
TUNE_SOCKET_BUFFERS="${TUNE_SOCKET_BUFFERS:-1}"

if [[ "${TUNE_SOCKET_BUFFERS}" == "1" ]]; then
  MEM=$((2 * 512 * 1024 * 1024))
  set +e
  sysctl -w net.core.rmem_max="${MEM}" net.ipv4.tcp_rmem="4096 26240000 ${MEM}" >/dev/null
  sysctl -w net.core.wmem_max="${MEM}" net.ipv4.tcp_wmem="4096 16384 ${MEM}" >/dev/null
  set -e
fi

IFS=',' read -r -a CCS <<<"${CC_LIST}"
IFS=',' read -r -a PROXIES <<<"${PROXY_VALUES}"

mkdir -p "${OUTPUT_ROOT}"

get_buf_pkts() {
  awk -v bw="${BW_MBIT}" -v rtt="${BASE_RTT_MS}" -v bdp_of_buf="${BDP_OF_BUF}" \
    'BEGIN { bdp_pkts = int(bw*1000*1000*rtt/1000.0 / (1514 * 8) * bdp_of_buf); print bdp_pkts; }'
}

BUF_PKTS="$(get_buf_pkts)"
echo "Using output root: ${OUTPUT_ROOT}"
echo "Using buffer (packets): ${BUF_PKTS}"

for cc_name in "${CCS[@]}"; do
  cc_name="$(echo "${cc_name}" | xargs)"
  if [[ -z "${cc_name}" ]]; then
    continue
  fi
  cc_param="${cc_name}:1"
  for proxy in "${PROXIES[@]}"; do
    proxy="$(echo "${proxy}" | xargs)"
    for ((a_delay = DELAY_MIN; a_delay <= DELAY_MAX; a_delay += DELAY_STEP)); do
      for ((b_delay = DELAY_MIN; b_delay <= DELAY_MAX; b_delay += DELAY_STEP)); do
        outdir="${OUTPUT_ROOT}/${cc_name}/proxy_${proxy}/a_${a_delay}_b_${b_delay}"
        if [[ "${SKIP_EXISTING}" == "1" && -f "${outdir}/test_params.txt" ]]; then
          continue
        fi
        mkdir -p "${outdir}"
        echo "[two-flow] cc=${cc_name} proxy=${proxy} a=${a_delay} b=${b_delay}"

        set +e
        cc="${cc_param}" bw="${BW_MBIT}" proxy_on="${proxy}" proxy_init="${PROXY_INIT_MS}" \
          rtt="${BASE_RTT_MS}" a_delay="${a_delay}" b_delay="${b_delay}" \
          buf="${BUF_PKTS}" qdisc="${QDISC}" loss="${LOSS_PCT}" \
          dur="${DURATION_SEC}" pcap="${PCAP_BYTES}" cmd="${CMD}" outdir="${outdir}" \
          interval="${FLOW_START_INTERVAL_SEC}" \
          python3 "${ENGINE_DIR}/nsperf_two_flows.py" stream | tee "${outdir}/nsperf.out.txt"
        run_status=$?
        set -e
        if [[ ${run_status} -ne 0 ]]; then
          echo "Failed run in ${outdir}" >&2
          continue
        fi

        cc="${cc_param}" bw="${BW_MBIT}" proxy_on="${proxy}" proxy_init="${PROXY_INIT_MS}" \
          rtt="${BASE_RTT_MS}" a_delay="${a_delay}" b_delay="${b_delay}" \
          buf="${BUF_PKTS}" qdisc="${QDISC}" loss="${LOSS_PCT}" \
          dur="${DURATION_SEC}" pcap="${PCAP_BYTES}" cmd="${CMD}" outdir="${outdir}" \
          interval="${FLOW_START_INTERVAL_SEC}" \
          python3 "${ENGINE_DIR}/save_params.py" | tee "${outdir}/test_params.txt"
      done
    done
  done
done

echo "Done: ${OUTPUT_ROOT}"
