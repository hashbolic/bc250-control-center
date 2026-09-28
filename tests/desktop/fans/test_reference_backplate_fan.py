from __future__ import annotations

import json
import os
import runpy
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "privileged" / "helpers" / "bc250-backplate-fan-controller"


@pytest.fixture
def module(tmp_path, monkeypatch):
    data = runpy.run_path(str(HELPER))
    g = data["read_backplate_source"].__globals__
    monkeypatch.setitem(g, "TELEMETRY_PATH", tmp_path / "apu_telemetry.json")
    monkeypatch.setitem(g, "STATUS_PATH", tmp_path / "backplate-fan.json")
    monkeypatch.setitem(g, "POLICY_PATH", tmp_path / "backplate-fan-policy.json")
    return data, g


def _snapshot(path: Path, codes: list[int], *, gpu_vrm: float = 40.0) -> None:
    path.write_text(json.dumps({
        "memory": {
            "status": "ok",
            "valid": True,
            "raw": list(codes),
        },
        "hardware": {
            "gpu": {"valid": True, "temp": gpu_vrm},
        },
    }), encoding="utf-8")
    os.utime(path, None)


def test_reads_hottest_gddr6_chip(module):
    data, g = module
    path = g["TELEMETRY_PATH"]
    _snapshot(path, [45, 46, 47, 48, 49, 50, 51, 52])

    hotspot, source, chip = data["read_backplate_source"](path)

    assert hotspot == 64.0
    assert source == "gddr6_hotspot"
    assert chip == 7


@pytest.mark.parametrize("temperature, expected", [
    (40, 25),
    (49, 25),
    (50, 35),
    (55, 45),
    (60, 60),
    (65, 75),
    (70, 90),
    (75, 100),
])
def test_reference_curve(temperature, expected, module):
    data, _g = module
    assert data["curve_percent"](temperature) == expected


def test_gpu_vrm_can_raise_backplate_target(module):
    data, g = module
    path = g["TELEMETRY_PATH"]
    _snapshot(path, [45] * 8, gpu_vrm=72.0)

    temperature, source, chip = data["read_backplate_source"](path)

    assert temperature == 72.0
    assert source == "gpu_vrm"
    assert chip is None


def test_missing_gddr6_does_not_fall_back_to_gpu_vrm(module):
    data, g = module
    path = g["TELEMETRY_PATH"]
    path.write_text(json.dumps({
        "memory": {"status": "unavailable", "valid": False, "raw": []},
        "hardware": {"gpu": {"valid": True, "temp": 70.0}},
    }), encoding="utf-8")
    os.utime(path, None)

    assert data["read_backplate_source"](path) == (None, None, None)


def test_reloadable_backplate_policy_changes_curve_without_restart(module):
    data, g = module
    policy_path = g["POLICY_PATH"]
    policy_path.write_text(json.dumps({
        "schema": 1,
        "pwm": 3,
        "points": [[0, 20], [50, 40], [60, 80], [75, 100]],
        "failsafe_percent": 100,
        "hysteresis_c": 1.5,
        "deadband_percent": 2,
        "max_down_step_percent": 10,
        "sensor_timeout_seconds": 15.0,
        "critical_c": 95.0,
    }), encoding="utf-8")

    policy = data["load_policy"](policy_path)

    assert policy["points"] == [[0, 20], [50, 40], [60, 80], [75, 100]]
    assert data["curve_percent"](60.0, policy["points"]) == 80


def test_backplate_policy_refuses_wrong_channel(module):
    data, _g = module

    with pytest.raises(ValueError, match="PWM3"):
        data["validate_policy"]({
            "schema": 1,
            "pwm": 2,
            "points": [[0, 20], [50, 40], [75, 100]],
        })


def test_missing_telemetry_goes_startup_safe_then_failsafe(module):
    data, g = module

    @contextmanager
    def lock():
        yield

    class Sensor:
        def __truediv__(self, _name):
            return Path("/nonexistent")

    writes = []
    backend = {
        "find_sensor": lambda: Sensor(),
        "fan_operation_lock": lock,
        "apply_pwm": lambda channel, raw: writes.append((channel, raw)) or "OK",
        "restore_automatic": lambda channel: "OK",
    }
    ticks = iter([0.0, 20.0])
    controller = data["BackplateController"](backend, clock=lambda: next(ticks), wall=lambda: 100.0)

    controller.step()
    assert controller.last_percent == 70
    controller.step()
    assert controller.last_percent == 100
    assert writes[-1] == (3, 255)
