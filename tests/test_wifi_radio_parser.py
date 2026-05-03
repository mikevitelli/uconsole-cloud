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
