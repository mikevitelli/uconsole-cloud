"""Tests for aiov2_ctl --status text parser."""

import os

import pytest

from tui.aio import parse_status

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


def test_parse_status_mixed_ac():
    out = parse_status(_read("aiov2_status_mixed_ac.txt"))
    # Rails section
    assert out["rails"]["GPS"]["state"] is True
    assert out["rails"]["GPS"]["gpio"] == 27
    assert out["rails"]["LORA"]["state"] is False
    assert out["rails"]["SDR"]["state"] is False
    assert out["rails"]["USB"]["state"] is True
    # Power section (just verify keys exist; values may vary)
    for key in ("source", "status", "capacity", "mode", "voltage", "current", "power"):
        assert key in out["power"], f"missing {key}"
    # Capacity is an int 0..100
    assert isinstance(out["power"]["capacity"], int)
    assert 0 <= out["power"]["capacity"] <= 100


def test_parse_status_all_off():
    out = parse_status(_read("aiov2_status_all_off_bat.txt"))
    for rail in ("GPS", "LORA", "SDR", "USB"):
        assert out["rails"][rail]["state"] is False, f"{rail} should be off"


def test_parse_status_returns_floats_for_numeric_power_fields():
    out = parse_status(_read("aiov2_status_mixed_ac.txt"))
    assert isinstance(out["power"]["voltage"], float)
    assert isinstance(out["power"]["current"], float)
    assert isinstance(out["power"]["power"], float)


def test_parse_status_handles_unknown_rail_gracefully():
    # Unknown text returns empty rails dict — never raises
    out = parse_status("garbage input that has no rails")
    assert out["rails"] == {}
    assert out["power"] == {}
