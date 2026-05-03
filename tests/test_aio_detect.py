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
