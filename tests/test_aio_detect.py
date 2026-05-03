"""Tests for AIO v1/v2 board detection and rail-power helper."""

from unittest.mock import patch, MagicMock

import pytest

from tui import aio


def test_detect_v2_when_binary_present(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", None)
    monkeypatch.setattr(aio.os.path, "isfile", lambda p: p == aio.AIOV2_CTL)
    monkeypatch.setattr(aio.os, "access", lambda p, mode: p == aio.AIOV2_CTL)
    assert aio.detect() == "v2"


def test_detect_v1_when_binary_absent(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", None)
    monkeypatch.setattr(aio.os.path, "isfile", lambda p: False)
    assert aio.detect() == "v1"


def test_detect_is_cached(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", None)
    calls = []
    def fake_isfile(p):
        calls.append(p)
        return True
    monkeypatch.setattr(aio.os.path, "isfile", fake_isfile)
    monkeypatch.setattr(aio.os, "access", lambda p, mode: True)
    aio.detect()
    aio.detect()
    aio.detect()
    # isfile should have been called exactly once (first call); subsequent calls return cache
    assert len(calls) == 1


def test_ensure_rail_noop_on_v1(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", "v1")
    # Subprocess should never be invoked on v1
    called = []
    monkeypatch.setattr(aio.subprocess, "run", lambda *a, **kw: called.append(a))
    assert aio.ensure_rail("GPS") is True
    assert called == []


def test_ensure_rail_already_on(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", "v2")
    fake_status = "GPS   GPIO27: ON\nLORA  GPIO16: OFF\n"
    fake_run = MagicMock()
    fake_run.return_value = MagicMock(returncode=0, stdout=fake_status)
    monkeypatch.setattr(aio.subprocess, "run", fake_run)
    assert aio.ensure_rail("GPS") is True
    # Only the --status call, no toggle
    assert fake_run.call_count == 1


def test_ensure_rail_toggles_when_off(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", "v2")
    fake_status = "GPS   GPIO27: OFF\n"
    calls = []
    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "--status" in cmd:
            return MagicMock(returncode=0, stdout=fake_status)
        return MagicMock(returncode=0, stdout="")
    monkeypatch.setattr(aio.subprocess, "run", fake_run)
    assert aio.ensure_rail("GPS") is True
    # Status check + toggle
    assert len(calls) == 2
    assert calls[1] == [aio.AIOV2_CTL, "GPS", "on"]


def test_ensure_rail_returns_false_on_toggle_failure(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", "v2")
    def fake_run(cmd, **kw):
        if "--status" in cmd:
            return MagicMock(returncode=0, stdout="GPS   GPIO27: OFF\n")
        return MagicMock(returncode=1, stdout="")
    monkeypatch.setattr(aio.subprocess, "run", fake_run)
    assert aio.ensure_rail("GPS") is False


def test_ensure_rail_unknown_rail_returns_false(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", "v2")
    monkeypatch.setattr(aio.subprocess, "run", lambda *a, **kw: MagicMock(returncode=0, stdout=""))
    assert aio.ensure_rail("BOGUS") is False
