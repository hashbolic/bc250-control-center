import json

from bc250cc.infrastructure import reference_fan_control


def test_reference_channel_map_is_pinned():
    assert reference_fan_control.REFERENCE_FAN_CHANNELS["main"]["pwm"] == 2
    assert reference_fan_control.REFERENCE_FAN_CHANNELS["backplate"]["pwm"] == 3


def test_backplate_status_requires_fresh_heartbeat(tmp_path, monkeypatch):
    status = tmp_path / "backplate-fan.json"
    wants = tmp_path / "backplate.service"
    status.write_text(json.dumps({
        "heartbeat": 100.0,
        "state": "active",
        "pwm": 3,
        "temperature": 76.0,
        "sensor": "gddr6_hotspot",
    }), encoding="utf-8")
    wants.symlink_to("/dev/null")
    monkeypatch.setattr(reference_fan_control, "BACKPLATE_STATUS_FILE", status)
    monkeypatch.setattr(reference_fan_control, "BACKPLATE_UNIT_WANTS", wants)

    fresh = reference_fan_control.read_reference_fan_status(now=105.0)
    stale = reference_fan_control.read_reference_fan_status(now=120.0)

    assert fresh["backplate_enabled"] is True
    assert fresh["backplate_running"] is True
    assert fresh["backplate"]["pwm"] == 3
    assert stale["backplate_running"] is False
    assert stale["backplate"] == {}
