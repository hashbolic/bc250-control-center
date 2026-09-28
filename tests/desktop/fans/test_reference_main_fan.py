from __future__ import annotations

import runpy
from pathlib import Path

from bc250cc.domain.fan.persistence import select_fan_control_temperature

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "privileged" / "helpers" / "bc250-fan-pwm-helper"


def test_reference_main_fan_curve_uses_cpu_gpu_only():
    temperature, sensor = select_fan_control_temperature({
        "cpu_temp": 62.0,
        "gpu_temp": 68.0,
        "vrm_temp": 90.0,
        "board_temp": 80.0,
    })

    assert temperature == 68.0
    assert sensor == "gpu"


def test_reference_main_fan_still_treats_vrm_as_critical_safety_sensor():
    module = runpy.run_path(str(HELPER))
    controller = module["FanController"](clock=lambda: 100.0)
    controller.policy = {
        "schema": 1,
        "mode": "curve",
        "pwm": 2,
        "points": [[40, 30], [60, 60], [80, 100]],
        "failsafe_percent": 100,
        "hysteresis_c": 1.0,
        "deadband_percent": 2,
        "max_down_step_percent": 10,
        "sensor_timeout_seconds": 15.0,
        "critical_c": {"gpu": 95.0, "cpu": 95.0, "vrm": 105.0, "board": 90.0},
        "offsets_c": {"gpu": 0.0, "cpu": 0.0, "vrm": 0.0, "board": 0.0},
    }

    percent, source, temperature, sensor = controller.plan(
        {"cpu": 60.0, "gpu": 65.0, "vrm": 106.0, "board": 70.0},
        100.0,
    )

    assert percent == 100
    assert source == "critical"
    assert temperature == 106.0
    assert sensor == "vrm"
