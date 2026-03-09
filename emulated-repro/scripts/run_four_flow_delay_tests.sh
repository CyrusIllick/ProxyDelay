#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_DIR="${ROOT_DIR}/engines"

OUTPUT_ROOT="${OUTPUT_ROOT:-${ROOT_DIR}/results/four_flow_delay}"

REPS="${REPS:-4}"
BW_MBIT="${BW_MBIT:-100}"
BASE_RTT_MS="${BASE_RTT_MS:-10}"
BDP_OF_BUF="${BDP_OF_BUF:-0.2}"
PROXY_INIT_MS="${PROXY_INIT_MS:-200}"
PROXY_ON="${PROXY_ON:-0}"
FLOW_START_INTERVAL_SEC="${FLOW_START_INTERVAL_SEC:-0}"
LOSS_PCT="${LOSS_PCT:-0}"
DURATION_SEC="${DURATION_SEC:-100}"
PCAP_BYTES="${PCAP_BYTES:-0}"
QDISC="${QDISC:-}"
CMD="${CMD:-}"
EXTRA_DELAY_MS="${EXTRA_DELAY_MS:-0}"
SKIP_EXISTING="${SKIP_EXISTING:-1}"
TUNE_SOCKET_BUFFERS="${TUNE_SOCKET_BUFFERS:-1}"

if [[ "${TUNE_SOCKET_BUFFERS}" == "1" ]]; then
  MEM=$((2 * 512 * 1024 * 1024))
  set +e
  sysctl -w net.core.rmem_max="${MEM}" net.ipv4.tcp_rmem="4096 26240000 ${MEM}" >/dev/null
  sysctl -w net.core.wmem_max="${MEM}" net.ipv4.tcp_wmem="4096 16384 ${MEM}" >/dev/null
  set -e
fi

mkdir -p "${OUTPUT_ROOT}"

get_buf_pkts() {
  awk -v bw="${BW_MBIT}" -v rtt="${BASE_RTT_MS}" -v bdp_of_buf="${BDP_OF_BUF}" \
    'BEGIN { bdp_pkts = int(bw*1000*1000*rtt/1000.0 / (1514 * 8) * bdp_of_buf); print bdp_pkts; }'
}

BUF_PKTS="$(get_buf_pkts)"
echo "Using output root: ${OUTPUT_ROOT}"
echo "Using buffer (packets): ${BUF_PKTS}"

run_family() {
  local family_name="$1"
  local cc_param="$2"
  local delays_csv="$3"
  local -a delays
  IFS=',' read -r -a delays <<<"${delays_csv}"

  for ((rep = 1; rep <= REPS; rep++)); do
    for delay_a in "${delays[@]}"; do
      for delay_b in "${delays[@]}"; do
        for delay_c in "${delays[@]}"; do
          for delay_d in "${delays[@]}"; do
            local outdir="${OUTPUT_ROOT}/${family_name}/rep_${rep}/${delay_a}/${delay_b}/${delay_c}/${delay_d}"
            if [[ "${SKIP_EXISTING}" == "1" && -f "${outdir}/test_params.txt" ]]; then
              continue
            fi
            mkdir -p "${outdir}"
            echo "[four-flow] family=${family_name} rep=${rep} delays=${delay_a},${delay_b},${delay_c},${delay_d}"

            set +e
            cc="${cc_param}" bw="${BW_MBIT}" proxy_on="${PROXY_ON}" proxy_init="${PROXY_INIT_MS}" \
              rtt="${BASE_RTT_MS}" extra_delay="${EXTRA_DELAY_MS}" \
              a_delay="${delay_a}" b_delay="${delay_b}" c_delay="${delay_c}" d_delay="${delay_d}" \
              buf="${BUF_PKTS}" qdisc="${QDISC}" loss="${LOSS_PCT}" \
              dur="${DURATION_SEC}" pcap="${PCAP_BYTES}" cmd="${CMD}" outdir="${outdir}" \
              interval="${FLOW_START_INTERVAL_SEC}" \
              python3 "${ENGINE_DIR}/nsperf_four_flows_het.py" stream | tee "${outdir}/nsperf.out.txt"
            run_status=$?
            set -e
            if [[ ${run_status} -ne 0 ]]; then
              echo "Failed run in ${outdir}" >&2
              continue
            fi

            cc="${cc_param}" bw="${BW_MBIT}" proxy_on="${PROXY_ON}" proxy_init="${PROXY_INIT_MS}" \
              rtt="${BASE_RTT_MS}" extra_delay="${EXTRA_DELAY_MS}" \
              a_delay="${delay_a}" b_delay="${delay_b}" c_delay="${delay_c}" d_delay="${delay_d}" \
              buf="${BUF_PKTS}" qdisc="${QDISC}" loss="${LOSS_PCT}" \
              dur="${DURATION_SEC}" pcap="${PCAP_BYTES}" cmd="${CMD}" outdir="${outdir}" \
              interval="${FLOW_START_INTERVAL_SEC}" \
              python3 "${ENGINE_DIR}/save_params.py" | tee "${outdir}/test_params.txt"
          done
        done
      done
    done
  done
}

run_family "bbrhyblacubicreno_10_20_30" "bbr:1,hybla:1,cubic:1,reno:1" "10,20,30"
run_family "bbrhyblacubicreno_60_70_80" "bbr:1,hybla:1,cubic:1,reno:1" "60,70,80"
run_family "illinoiswestwoodcubicreno_5_15_30" "illinois:1,westwood:1,cubic:1,reno:1" "5,15,30"
run_family "illinoiswestwoodcubicreno_35_40_45" "illinois:1,westwood:1,cubic:1,reno:1" "35,40,45"

echo "Done: ${OUTPUT_ROOT}"
