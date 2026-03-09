"""Helpers for loading and validating real-world test configuration.

The framework uses two JSON files:
  - config/topology.json
  - config/cloud.json
Environment variables can override these default paths.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_CC_ALGORITHMS = [
    "reno",
    "bbr",
    "bbr1",
    "bic",
    "cdg",
    "cubic",
    "dctcp",
    "westwood",
    "highspeed",
    "hybla",
    "htcp",
    "vegas",
    "nv",
    "veno",
    "scalable",
    "lp",
    "yeah",
    "illinois",
]


def _base_dir() -> Path:
    """Return the directory containing this module."""
    return Path(__file__).resolve().parent


def _load_json(path: Path) -> Dict[str, Any]:
    """Load a JSON file and raise a clear message if it is missing."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing config file: {path}. Copy config/*.example.json to config/*.json and fill placeholders."
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _require_keys(data: Dict[str, Any], required_keys: List[str], source_name: str) -> None:
    """Validate that required top-level keys are present."""
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise ValueError(f"Missing keys in {source_name}: {', '.join(missing)}")


@lru_cache(maxsize=1)
def load_configs() -> Dict[str, Dict[str, Any]]:
    """Load topology/cloud configs once and apply defaults."""
    base_dir = _base_dir()
    topology_path = Path(
        os.getenv("REAL_WORLD_TOPOLOGY_CONFIG", str(base_dir / "config" / "topology.json"))
    )
    cloud_path = Path(os.getenv("REAL_WORLD_CLOUD_CONFIG", str(base_dir / "config" / "cloud.json")))

    topology = _load_json(topology_path)
    cloud = _load_json(cloud_path)

    _require_keys(topology, ["usernames", "gcp_zones", "aws_zones", "local_servers"], "topology")
    _require_keys(cloud, ["gcp", "aws"], "cloud")

    topology.setdefault("congestion_control_algorithms", DEFAULT_CC_ALGORITHMS)
    topology.setdefault("report_root", "reports")
    topology.setdefault("cloud_interface_name", "enp0s4")
    topology.setdefault("ssh_private_key_path", "")
    topology.setdefault("aws_instance_interface_name", "eth0")

    cloud["gcp"].setdefault("machine_type", "e2-medium")
    cloud["aws"].setdefault("instance_type", "t3.micro")
    cloud["aws"].setdefault("region", "us-east-1")
    cloud["aws"].setdefault("profile", "")
    cloud["aws"].setdefault("key_name", "")

    return {"topology": topology, "cloud": cloud}


def get_topology_config() -> Dict[str, Any]:
    """Return parsed topology config."""
    return load_configs()["topology"]


def get_cloud_config() -> Dict[str, Any]:
    """Return parsed cloud config."""
    return load_configs()["cloud"]


def get_report_root() -> str:
    """Return report output root directory from topology config."""
    topology = get_topology_config()
    return str(topology.get("report_root", "reports"))
