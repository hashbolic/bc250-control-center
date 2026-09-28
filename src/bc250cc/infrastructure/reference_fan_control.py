"""Read-only state for the Hashbolic BC250 reference dual-fan layout."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

MAIN_STATUS_FILE = Path("/run/bc250-control-center/fan-control.json")
BACKPLATE_STATUS_FILE = Path("/run/bc250-control-center/backplate-fan.json")
BACKPLATE_UNIT_WANTS = Path(
    "/etc/systemd/system/multi-user.target.wants/bc250-backplate-fan.service"
)
HEARTBEAT_STALE_SECONDS = 8.0
MAX_BYTES = 8192

REFERENCE_FAN_CHANNELS = {
    "main": {"pwm": 2, "label": "CPU/GPU main fan"},
    "backplate": {"pwm": 3, "label": "GDDR6 backplate fan"},
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_BYTES:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _fresh_status(path: Path, current: float) -> tuple[bool, dict[str, Any]]:
    status = _read_json(path)
    try:
        heartbeat = float(status.get("heartbeat") or 0.0)
    except (TypeError, ValueError):
        heartbeat = 0.0
    running = bool(status) and 0 <= current - heartbeat <= HEARTBEAT_STALE_SECONDS
    return running, status if running else {}


def read_reference_fan_status(*, now: float | None = None) -> dict[str, Any]:
    current = time.time() if now is None else float(now)
    main_running, main = _fresh_status(MAIN_STATUS_FILE, current)
    backplate_running, backplate = _fresh_status(BACKPLATE_STATUS_FILE, current)
    enabled = BACKPLATE_UNIT_WANTS.exists() or BACKPLATE_UNIT_WANTS.is_symlink()
    return {
        "layout": REFERENCE_FAN_CHANNELS,
        "main_running": main_running,
        "main": main,
        "backplate_enabled": enabled,
        "backplate_running": backplate_running,
        "backplate": backplate,
    }
