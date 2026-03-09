from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

PORT_RE = re.compile(r":(\d+)")
DELIVERY_RE = re.compile(r"\bdelivery_rate (\d+)bps\b")
CWND_RE = re.compile(r"\bcwnd:(\d+)")
RTT_RE = re.compile(r"\brtt:([0-9.]+)/")
EXTRA_ACKED_RE = re.compile(r"\bextra_acked:([-0-9.]+)")


@dataclass
class FlowSample:
    delivery_bps: Optional[float]
    cwnd: Optional[float]
    rtt_ms: Optional[float]
    extra_acked: Optional[float]

    @property
    def delivery_mbps(self) -> Optional[float]:
        if self.delivery_bps is None:
            return None
        return self.delivery_bps / 1_000_000.0


def parse_cc_param(cc_string: str) -> List[str]:
    cc_list: List[str] = []
    for group in cc_string.split(","):
        group = group.strip()
        if not group:
            continue
        if ":" in group:
            cc_name, count_str = group.split(":", 1)
            count = int(count_str)
        else:
            cc_name = group
            count = 1
        cc_list.extend([cc_name] * count)
    return cc_list


def parse_cc_value(raw_cc: Any) -> List[str]:
    if isinstance(raw_cc, list):
        return [str(x).strip() for x in raw_cc]
    if isinstance(raw_cc, tuple):
        return [str(x).strip() for x in raw_cc]
    if raw_cc is None:
        return []
    cc_str = str(raw_cc).strip()
    if not cc_str:
        return []
    if cc_str.startswith("[") and cc_str.endswith("]"):
        try:
            parsed = ast.literal_eval(cc_str)
            if isinstance(parsed, (list, tuple)):
                return [str(x).strip() for x in parsed]
        except (ValueError, SyntaxError):
            pass
    return parse_cc_param(cc_str)


def parse_param_value(raw_value: str) -> Any:
    value = raw_value.strip()
    if value == "":
        return ""
    if value in {"True", "False"}:
        return value == "True"
    if value.startswith("[") and value.endswith("]"):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def parse_test_params(path: Path) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            if not key:
                continue
            params[key] = parse_param_value(value)
    return params


def parse_ss_log(path: Path, target_ports: Optional[Sequence[int]] = None) -> Dict[int, List[FlowSample]]:
    target_set = set(target_ports) if target_ports else None
    samples: Dict[int, List[FlowSample]] = {}
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("ESTAB"):
            i += 1
            continue

        ports = [int(p) for p in PORT_RE.findall(line)]
        if not ports:
            i += 1
            continue

        port = None
        if target_set is None:
            port = ports[-1]
        else:
            for p in ports:
                if p in target_set:
                    port = p
                    break
        if port is None:
            i += 1
            continue

        stats_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        delivery_match = DELIVERY_RE.search(stats_line)
        cwnd_match = CWND_RE.search(stats_line)
        rtt_match = RTT_RE.search(stats_line)
        extra_match = EXTRA_ACKED_RE.search(stats_line)

        delivery_bps = float(delivery_match.group(1)) if delivery_match else None
        cwnd = float(cwnd_match.group(1)) if cwnd_match else None
        rtt_ms = float(rtt_match.group(1)) if rtt_match else None
        extra_acked = float(extra_match.group(1)) if extra_match else None

        samples.setdefault(port, []).append(
            FlowSample(
                delivery_bps=delivery_bps,
                cwnd=cwnd,
                rtt_ms=rtt_ms,
                extra_acked=extra_acked,
            )
        )
        i += 2
    return samples


def slice_window(values: Sequence[Any], start_frac: float, end_frac: float) -> List[Any]:
    if not values:
        return []
    n = len(values)
    start = int(max(0.0, min(1.0, start_frac)) * n)
    end = int(max(0.0, min(1.0, end_frac)) * n)
    if end <= start:
        end = n
    return list(values[start:end])


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    cleaned = [float(v) for v in values if v is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default

