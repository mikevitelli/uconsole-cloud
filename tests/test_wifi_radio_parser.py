"""Tests for iw dev and rfkill list parsers."""

import os
import pytest

from tui.wifi_radio import parse_iw_dev, parse_rfkill_list

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


def test_parse_iw_dev_returns_two_phys():
    radios = parse_iw_dev(_read("iw_dev.txt"))
    # Two phys, each with one wlan interface
    ifs = sorted(r["ifname"] for r in radios)
    assert ifs == ["wlan0", "wlan1"]


def test_parse_iw_dev_extracts_phy_and_ssid():
    radios = parse_iw_dev(_read("iw_dev.txt"))
    by_if = {r["ifname"]: r for r in radios}
    # phy field is "phy#0" / "phy#1" — implementation should normalize to int
    assert isinstance(by_if["wlan0"]["phy"], int)
    # At least one of the two should have an SSID populated (fixture-dependent)
    has_ssid = any(r.get("ssid") for r in radios)
    assert has_ssid, "expected at least one associated radio in fixture"


def test_parse_rfkill_list_blocked_status():
    entries = parse_rfkill_list(_read("rfkill_list.txt"))
    # Each phy entry has phy id and soft-blocked bool
    phys = [e for e in entries if e["kind"] == "phy"]
    assert len(phys) >= 1
    for p in phys:
        assert "id" in p
        assert isinstance(p["soft_blocked"], bool)


from unittest.mock import patch, MagicMock

from tui import wifi_radio


def test_label_for_driver():
    assert wifi_radio._label_for_driver("brcmfmac") == "CM5 onboard"
    assert wifi_radio._label_for_driver("mt7921u") == "AC1200 (WiFi 6)"
    assert wifi_radio._label_for_driver("zzz_unknown") == "zzz_unknown"


def test_load_mode_default_is_both(tmp_path, monkeypatch):
    monkeypatch.setattr(wifi_radio, "MODE_FILE", str(tmp_path / "absent"))
    assert wifi_radio.load_mode() == "both"


def test_save_and_load_mode_roundtrip(tmp_path, monkeypatch):
    f = tmp_path / "mode"
    monkeypatch.setattr(wifi_radio, "MODE_FILE", str(f))
    wifi_radio.save_mode("ac1200")
    assert wifi_radio.load_mode() == "ac1200"


def test_save_mode_rejects_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(wifi_radio, "MODE_FILE", str(tmp_path / "mode"))
    with pytest.raises(ValueError):
        wifi_radio.save_mode("bogus")


def test_find_radio_by_driver_first_match():
    radios = [
        {"phy": 0, "driver": "brcmfmac", "ifname": "wlan0"},
        {"phy": 2, "driver": "mt7921u",  "ifname": "wlan1"},
    ]
    found = wifi_radio.find_radio_by_driver(radios, "mt7921u")
    assert found["ifname"] == "wlan1"
    assert wifi_radio.find_radio_by_driver(radios, "missing") is None


def test_current_mode_label_mapping(tmp_path, monkeypatch):
    f = tmp_path / "mode"
    monkeypatch.setattr(wifi_radio, "MODE_FILE", str(f))
    cases = [
        ("both",    "Both active"),
        ("onboard", "CM5 onboard only"),
        ("ac1200",  "AC1200 only"),
    ]
    for mode_id, expected in cases:
        wifi_radio.save_mode(mode_id)
        assert wifi_radio.current_mode_label() == expected
    # Garbage in MODE_FILE → load_mode returns "both" → label is "Both active"
    f.write_text("garbage\n")
    assert wifi_radio.current_mode_label() == "Both active"


def test_brief_radio_summary_format(monkeypatch):
    fake_radios = [
        {"phy": 2, "ifname": "wlan1", "driver": "mt7921u", "label": "AC1200 (WiFi 6)",
         "ssid": "Big Parma", "soft_blocked": False},
        {"phy": 0, "ifname": "wlan0", "driver": "brcmfmac", "label": "CM5 onboard",
         "ssid": "Big Parma - 2.4GHz", "soft_blocked": False},
    ]
    monkeypatch.setattr(wifi_radio, "list_radios", lambda: fake_radios)
    # Two-space separator between entries
    assert wifi_radio.brief_radio_summary() == "wlan1=AC1200  wlan0=CM5"


def test_brief_radio_summary_unknown_driver_falls_through(monkeypatch):
    monkeypatch.setattr(wifi_radio, "list_radios", lambda: [
        {"phy": 0, "ifname": "wlan9", "driver": "exotic_driver",
         "label": "exotic_driver", "ssid": None, "soft_blocked": False},
    ])
    assert wifi_radio.brief_radio_summary() == "wlan9=exotic_driver"
