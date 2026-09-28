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
    g = data["read_gddr6_hotspot"].__globals__
    monkeypatch.setitem(g, "TELEMETRY_PATH", tmp_path / "apu_telemetry.json")
    monkeypatch.setitem(g, "STATUS_PATH", tmp_path / "backplate-fan.json")
    return data, g


def _snapshot(path: Path, codes: list[int]) -> None:
    path.write_text(json.dumps({
        "memory": {
            "status": "ok",
            "valid": True,
            "raw": list(codes),
        }
    }), encoding="utf-8")
    os.utime(path, None)


def test_reads_hottest_gddr6_chip(module):
    data, g = module
    path = g["TELEMETRY_PATH"]
    _snapshot(path, [45, 46, 47, 48, 49, 50, 51, 52])

    hotspot, chip = data["read_gddr6_hotspot"](path)

    assert hotspot == 64.0
    assert chip == 7


@pytest.mark.parametrize("temperature, expected", [
    (40, 25),
    (54, 25),
    (55, 35),
    (65, 50),
    (75, 70),
    (85, 90),
    (90, 100),
])
def test_reference_curve(temperature, expected, module):
    data, _g = module
    assert data["curve_percent"](temperature) == expected


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
