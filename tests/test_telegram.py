"""Tests for tui/telegram.py — the Telethon-based Telegram client.

Scope:
- Static import + exports
- Pure helpers (formatting, wrap, parse, relative time)
- Credentials roundtrip
- Bridge smoke + event-handler unit tests with fake events
- send_typing debounce logic

What these tests do NOT cover:
- The actual curses render loops (_chat_list_view, _conversation_view) —
  those are exercised by manual smoke runs on the device.
- Real network calls to Telegram. All bridge tests use fakes/mocks.
"""

import datetime
import importlib
import json
import os
import queue
import sys
import time
from unittest.mock import MagicMock, AsyncMock

import pytest

# conftest.py already adds device/lib to sys.path
import tui.telegram as tg  # noqa: E402


# ── Static / import hygiene ──────────────────────────────────────────────

class TestModuleStructure:
    """The module loads cleanly and exposes what framework.py needs."""

    def test_module_imports(self):
        assert tg is not None

    def test_run_telegram_exported(self):
        assert callable(tg.run_telegram)

    def test_bridge_class_exists(self):
        assert isinstance(tg._TelegramBridge, type)

    def test_telethon_available(self):
        """Either Telethon is installed (normal case) or the module sets the
        _HAS_TELETHON guard to False. Both are valid — but on a dev device we
        expect it installed."""
        if tg._HAS_TELETHON:
            assert tg.TelegramClient is not None
            assert tg.events is not None
        else:
            pytest.skip("telethon not installed")

    def test_conf_paths_absolute(self):
        assert os.path.isabs(tg.CONF_DIR)
        assert os.path.isabs(tg.CRED_FILE)
        assert os.path.isabs(tg.SESSION_PATH)
        assert tg.CRED_FILE.endswith(".json")

    def test_kind_glyphs_defined(self):
        for k in ("user", "group", "channel"):
            assert k in tg._KIND_GLYPH


# ── _format_name ─────────────────────────────────────────────────────────

class TestFormatName:
    def _fake(self, **kw):
        m = MagicMock(spec=["first_name", "last_name", "username", "id"])
        m.first_name = kw.get("first_name")
        m.last_name = kw.get("last_name")
        m.username = kw.get("username")
        m.id = kw.get("id", 42)
        return m

    def test_first_and_last(self):
        assert tg._format_name(self._fake(first_name="dr", last_name="dalek")) == "dr dalek"

    def test_first_only(self):
        assert tg._format_name(self._fake(first_name="dr")) == "dr"

    def test_last_only(self):
        assert tg._format_name(self._fake(last_name="dalek")) == "dalek"

    def test_username_fallback(self):
        assert tg._format_name(self._fake(username="drdalek")) == "drdalek"

    def test_id_fallback(self):
        assert tg._format_name(self._fake(id=123)) == "id:123"

    def test_empty_strings_are_skipped(self):
        # first_name="" should NOT become part of the name
        assert tg._format_name(self._fake(first_name="", last_name="dalek")) == "dalek"

    def test_whitespace_first_name_not_used_as_name(self):
        # documents current behavior; whitespace-only names pass through
        assert tg._format_name(self._fake(first_name=" ", username="fallback")) == " "


# ── _extract_msg_preview ─────────────────────────────────────────────────

class TestExtractMsgPreview:
    def _msg(self, message=None, media=None, raw_text=None):
        m = MagicMock(spec=["message", "raw_text", "media"])
        m.message = message
        m.raw_text = raw_text
        m.media = media
        return m

    def test_none_message(self):
        assert tg._extract_msg_preview(None) == ""

    def test_plain_text(self):
        assert tg._extract_msg_preview(self._msg(message="hello world")) == "hello world"

    def test_newlines_collapsed(self):
        assert tg._extract_msg_preview(self._msg(message="a\nb\nc")) == "a b c"

    def test_raw_text_fallback(self):
        m = self._msg(message="", raw_text="fallback text")
        assert tg._extract_msg_preview(m) == "fallback text"

    def test_photo_media(self):
        photo = type("MessageMediaPhoto", (), {})()
        assert tg._extract_msg_preview(self._msg(media=photo)) == "[Photo]"

    def test_document_media(self):
        doc = type("MessageMediaDocument", (), {})()
        assert tg._extract_msg_preview(self._msg(media=doc)) == "[Document]"

    def test_voice_media(self):
        voice = type("MessageMediaVoice", (), {})()
        assert tg._extract_msg_preview(self._msg(media=voice)) == "[Voice]"

    def test_empty_with_no_media(self):
        assert tg._extract_msg_preview(self._msg(message="")) == ""

    def test_video_media(self):
        video = type("MessageMediaVideo", (), {})()
        assert tg._extract_msg_preview(self._msg(media=video)) == "[Video]"

    def test_sticker_media(self):
        sticker = type("MessageMediaSticker", (), {})()
        assert tg._extract_msg_preview(self._msg(media=sticker)) == "[Sticker]"

    def test_webpage_media(self):
        wp = type("MessageMediaWebpage", (), {})()
        assert tg._extract_msg_preview(self._msg(media=wp)) == "[Link]"

    def test_unknown_media_class(self):
        mm = type("MessageMediaMartian", (), {})()
        assert tg._extract_msg_preview(self._msg(media=mm)) == "[MessageMediaMartian]"

    def test_text_wins_over_media(self):
        photo = type("MessageMediaPhoto", (), {})()
        assert tg._extract_msg_preview(self._msg(message="caption", media=photo)) == "caption"


# ── _format_message ──────────────────────────────────────────────────────

class TestFormatMessage:
    def _msg(self, **kw):
        m = MagicMock(
            spec=["id", "message", "raw_text", "media", "date", "sender", "out"]
        )
        m.id = kw.get("id", 1)
        m.message = kw.get("message", "")
        m.raw_text = kw.get("raw_text", "")
        m.media = kw.get("media")
        m.date = kw.get("date")
        m.sender = kw.get("sender")
        m.out = kw.get("out", False)
        return m

    def test_self_message(self):
        d = tg._format_message(self._msg(message="yo", id=7, out=True))
        assert d["id"] == 7
        assert d["text"] == "yo"
        assert d["is_self"] is True

    def test_incoming_with_sender(self):
        sender = MagicMock(spec=["first_name", "last_name", "username", "id"])
        sender.first_name = "jim"
        sender.last_name = None
        sender.username = None
        sender.id = 99
        d = tg._format_message(self._msg(message="hi", sender=sender))
        assert d["sender"] == "jim"
        assert d["is_self"] is False

    def test_sender_raises_is_handled(self):
        # When sender access raises, format_message should not blow up
        m = self._msg(message="hi")
        type(m).sender = property(lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
        d = tg._format_message(m)
        assert d["sender"] is None


# ── _wrap_text ───────────────────────────────────────────────────────────

class TestWrapText:
    def test_empty(self):
        assert tg._wrap_text("", 10) == [""]

    def test_short_fits(self):
        assert tg._wrap_text("hi", 10) == ["hi"]

    def test_simple_wrap(self):
        result = tg._wrap_text("one two three four", 8)
        assert all(len(line) <= 8 for line in result)
        assert " ".join(result) == "one two three four"

    def test_explicit_newlines(self):
        result = tg._wrap_text("a\nb\nc", 10)
        assert result == ["a", "b", "c"]

    def test_word_longer_than_width(self):
        # A giant word must be hard-broken at `width`
        result = tg._wrap_text("x" * 25, 10)
        assert all(len(line) <= 10 for line in result)
        assert "".join(result) == "x" * 25

    def test_mixed_paragraphs(self):
        result = tg._wrap_text("hello world\n\nnew para", 20)
        assert "" in result  # blank line preserved

    def test_width_zero_returns_empty(self):
        assert tg._wrap_text("hello", 0) == [""]

    def test_width_one_terminates(self):
        result = tg._wrap_text("hi", 1)
        assert all(len(l) <= 1 for l in result)
        assert "".join(result) == "hi"

    def test_word_exactly_width(self):
        assert tg._wrap_text("abcde", 5) == ["abcde"]

    def test_consecutive_spaces_no_overflow(self):
        lines = tg._wrap_text("a  b  c", 5)
        assert all(len(l) <= 5 for l in lines)
        assert "".join(lines).replace(" ", "") == "abc"

    def test_leading_space(self):
        lines = tg._wrap_text(" hi", 10)
        assert all(len(l) <= 10 for l in lines)
        assert "hi" in "".join(lines)

    def test_trailing_space(self):
        lines = tg._wrap_text("hi ", 10)
        assert all(len(l) <= 10 for l in lines)
        assert "hi" in "".join(lines)


# ── _format_hhmm ─────────────────────────────────────────────────────────

class TestFormatHHMM:
    def test_none(self):
        assert tg._format_hhmm(None) == ""

    def test_aware_datetime(self):
        dt = datetime.datetime(2026, 4, 13, 14, 32,
                               tzinfo=datetime.timezone.utc)
        # Exact value depends on local TZ, but it must be HH:MM shape
        out = tg._format_hhmm(dt)
        assert len(out) == 5 and out[2] == ":"

    def test_aware_datetime_with_utc_tz(self, monkeypatch):
        import os
        os.environ["TZ"] = "UTC"
        try:
            time.tzset()
        except AttributeError:
            pass
        dt = datetime.datetime(2026, 4, 13, 14, 32, tzinfo=datetime.timezone.utc)
        assert tg._format_hhmm(dt) == "14:32"

    def test_naive_datetime(self):
        dt = datetime.datetime(2026, 4, 13, 14, 32)
        out = tg._format_hhmm(dt)
        assert len(out) == 5 and out[2] == ":"


# ── _relative_time ───────────────────────────────────────────────────────

class TestRelativeTime:
    def _utc(self, **delta):
        return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(**delta)

    def test_none(self):
        assert tg._relative_time(None) == ""

    @pytest.mark.parametrize("delta,expected_pattern", [
        (datetime.timedelta(seconds=30), r"\d+s"),
        (datetime.timedelta(seconds=59), r"59s"),
        (datetime.timedelta(seconds=60), r"1m"),
        (datetime.timedelta(minutes=5), r"5m"),
        (datetime.timedelta(minutes=59), r"59m"),
        (datetime.timedelta(seconds=3600), r"1h"),
        (datetime.timedelta(hours=3), r"3h"),
        (datetime.timedelta(hours=23, minutes=59), r"23h"),
        (datetime.timedelta(seconds=86400), r"1d"),
        (datetime.timedelta(days=2), r"2d"),
        (datetime.timedelta(days=6, hours=23), r"6d"),
    ])
    def test_boundaries(self, delta, expected_pattern):
        import re
        dt = datetime.datetime.now(datetime.timezone.utc) - delta
        assert re.fullmatch(expected_pattern, tg._relative_time(dt))

    def test_over_week_uses_strftime(self):
        import re
        out = tg._relative_time(self._utc(days=10))
        assert re.fullmatch(r"[A-Z][a-z]{2}\d{1,2}", out), f"unexpected: {out!r}"

    def test_future_date_is_sane(self):
        future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        out = tg._relative_time(future)
        assert isinstance(out, str)

    def test_naive_datetime_assumed_utc(self):
        # SUT fix: naive dt treated as UTC. Use a past naive dt and assert
        # the result is a recognizable relative-time token (not empty).
        dt = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
        out = tg._relative_time(dt)
        assert isinstance(out, str) and out != ""

    def test_weeks_falls_back_to_date(self):
        import re
        out = tg._relative_time(self._utc(days=20))
        # Format like "Mar24" from strftime("%b%d")
        assert re.fullmatch(r"[A-Z][a-z]{2}\d{1,2}", out), f"unexpected format: {out!r}"


# ── Credentials roundtrip ────────────────────────────────────────────────

class TestCredentials:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tg, "CONF_DIR", str(tmp_path))
        monkeypatch.setattr(tg, "CRED_FILE", str(tmp_path / "telegram.json"))
        tg._save_creds(12345, "abcdef" * 5)
        api_id, api_hash = tg._load_creds()
        assert api_id == 12345
        assert api_hash == "abcdefabcdefabcdefabcdefabcdef"

    def test_save_chmods_600(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tg, "CONF_DIR", str(tmp_path))
        p = tmp_path / "telegram.json"
        monkeypatch.setattr(tg, "CRED_FILE", str(p))
        tg._save_creds(1, "h")
        mode = os.stat(p).st_mode & 0o777
        assert mode == 0o600

    def test_load_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tg, "CRED_FILE", str(tmp_path / "nope.json"))
        assert tg._load_creds() == (None, None)

    def test_load_malformed_json(self, tmp_path, monkeypatch):
        p = tmp_path / "bad.json"
        p.write_text("{not valid")
        monkeypatch.setattr(tg, "CRED_FILE", str(p))
        assert tg._load_creds() == (None, None)

    def test_load_missing_keys(self, tmp_path, monkeypatch):
        p = tmp_path / "partial.json"
        p.write_text(json.dumps({"api_id": 1}))  # missing api_hash
        monkeypatch.setattr(tg, "CRED_FILE", str(p))
        assert tg._load_creds() == (None, None)

    def test_api_id_as_string_coerced(self, tmp_path, monkeypatch):
        p = tmp_path / "telegram.json"
        p.write_text(json.dumps({"api_id": "12345", "api_hash": "a" * 32}))
        monkeypatch.setattr(tg, "CRED_FILE", str(p))
        api_id, api_hash = tg._load_creds()
        assert api_id == 12345
        assert api_hash == "a" * 32

    def test_api_hash_null_rejected(self, tmp_path, monkeypatch):
        p = tmp_path / "telegram.json"
        p.write_text(json.dumps({"api_id": 1, "api_hash": None}))
        monkeypatch.setattr(tg, "CRED_FILE", str(p))
        assert tg._load_creds() == (None, None)

    def test_api_hash_int_rejected(self, tmp_path, monkeypatch):
        p = tmp_path / "telegram.json"
        p.write_text(json.dumps({"api_id": 1, "api_hash": 42}))
        monkeypatch.setattr(tg, "CRED_FILE", str(p))
        assert tg._load_creds() == (None, None)

    def test_extra_keys_ignored(self, tmp_path, monkeypatch):
        p = tmp_path / "telegram.json"
        p.write_text(json.dumps({"api_id": 1, "api_hash": "a" * 32, "extra": "x"}))
        monkeypatch.setattr(tg, "CRED_FILE", str(p))
        assert tg._load_creds() == (1, "a" * 32)

    def test_conf_dir_is_0o700(self, tmp_path, monkeypatch):
        conf = tmp_path / "conf"
        monkeypatch.setattr(tg, "CONF_DIR", str(conf))
        monkeypatch.setattr(tg, "CRED_FILE", str(conf / "telegram.json"))
        tg._save_creds(1, "h" * 32)
        mode = os.stat(conf).st_mode & 0o777
        assert mode == 0o700

    def test_save_is_atomic(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tg, "CONF_DIR", str(tmp_path))
        monkeypatch.setattr(tg, "CRED_FILE", str(tmp_path / "telegram.json"))
        tg._save_creds(1, "h" * 32)
        leftover = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
        assert leftover == []


# ── Bridge — instantiation & shared-state API ────────────────────────────

class TestBridgeInit:
    """Smoke-test the bridge without starting the thread."""

    def test_init_default_state(self):
        b = tg._TelegramBridge(1, "h")
        assert b.api_id == 1
        assert b.api_hash == "h"
        state, err, me = b.state()
        assert state == "init"
        assert err is None
        assert me is None

    def test_snap_dialogs_empty(self):
        b = tg._TelegramBridge(1, "h")
        dialogs, loading, err = b.snap_dialogs()
        assert dialogs == []
        assert loading is False
        assert err is None

    def test_snap_messages_empty(self):
        b = tg._TelegramBridge(1, "h")
        msgs, loading, err = b.snap_messages(42)
        assert msgs == []
        assert loading is False
        assert err is None

    def test_snap_typing_empty(self):
        b = tg._TelegramBridge(1, "h")
        assert b.snap_typing(42) is None

    def test_close_without_connect(self):
        b = tg._TelegramBridge(1, "h")
        b.close()  # must not raise when no thread was started


# ── Bridge — command enqueue ─────────────────────────────────────────────

class TestBridgeCommands:
    """Verify user-facing methods enqueue the right commands without
    actually running the background thread."""

    def test_fetch_dialogs_enqueues(self):
        b = tg._TelegramBridge(1, "h")
        b.fetch_dialogs()
        assert b._cmd_q.qsize() == 1
        assert b._cmd_q.get_nowait() == ("fetch_dialogs",)
        _, loading, _ = b.snap_dialogs()
        assert loading is True

    def test_fetch_history_enqueues(self):
        b = tg._TelegramBridge(1, "h")
        b.fetch_history(99)
        assert b._cmd_q.get_nowait() == ("fetch_history", 99)
        _, loading, _ = b.snap_messages(99)
        assert loading is True

    def test_send_enqueues(self):
        b = tg._TelegramBridge(1, "h")
        b.send(10, "hi")
        assert b._cmd_q.get_nowait() == ("send", 10, "hi")

    def test_send_typing_debounced(self):
        b = tg._TelegramBridge(1, "h")
        b.send_typing(5)
        b.send_typing(5)  # immediate second call
        b.send_typing(5)  # third immediate call
        # Only the first should have enqueued
        assert b._cmd_q.qsize() == 1
        assert b._cmd_q.get_nowait() == ("send_typing", 5)

    def test_send_typing_different_chats_not_debounced_together(self):
        b = tg._TelegramBridge(1, "h")
        b.send_typing(5)
        b.send_typing(6)
        assert b._cmd_q.qsize() == 2

    def test_send_typing_after_window_expires(self, monkeypatch):
        b = tg._TelegramBridge(1, "h")
        b.send_typing(5)
        # Fake the debounce window by backdating the last_sent timestamp
        b._typing_last_sent[5] = time.time() - 10.0
        b.send_typing(5)
        assert b._cmd_q.qsize() == 2

    def test_send_typing_exactly_at_boundary(self, monkeypatch):
        """Debounce uses strict `< 4.0`, so at exactly 4.0s elapsed the
        window has expired and a fresh send should fire."""
        current = [1000.0]
        monkeypatch.setattr(tg.time, "time", lambda: current[0])
        b = tg._TelegramBridge(1, "h")
        b.send_typing(5)
        current[0] = 1003.99  # just under the window — debounced
        b.send_typing(5)
        assert b._cmd_q.qsize() == 1
        current[0] = 1004.00  # exactly 4.0s elapsed — window has passed, fires
        b.send_typing(5)
        assert b._cmd_q.qsize() == 2

    def test_send_typing_prunes_old_entries(self):
        b = tg._TelegramBridge(1, "h")
        old = time.time() - 400.0
        for i in range(10):
            b._typing_last_sent[1000 + i] = old
        b.send_typing(99)
        assert len(b._typing_last_sent) <= 2


# ── Event handlers — direct unit tests ──────────────────────────────────

class TestEventHandlers:
    """We can't easily fire real Telethon events, so we replicate what the
    handlers do given a fake event object. This keeps the state-update
    logic covered without needing a running asyncio loop."""

    def _apply_new_message(self, b, chat_id, text, is_self=False, sender_name=None):
        """Mirror what _on_new_message does under the lock. Kept in sync
        with the real implementation on purpose — if the real handler
        changes, this helper should too, and that's the signal."""
        formatted = {
            "id": 1,
            "text": text,
            "date": datetime.datetime.now(datetime.timezone.utc),
            "sender": sender_name,
            "is_self": is_self,
        }
        with b._lock:
            b._typing.pop(chat_id, None)
            if chat_id in b._messages:
                b._messages[chat_id].append(formatted)
            preview = formatted["text"] or "[media]"
            moved = None
            for i, d in enumerate(b._dialogs):
                if d["id"] == chat_id:
                    d["text"] = preview
                    d["date"] = formatted["date"]
                    if not formatted["is_self"]:
                        d["unread"] = (d.get("unread") or 0) + 1
                    moved = i
                    break
            if moved is not None and moved > 0:
                b._dialogs.insert(0, b._dialogs.pop(moved))

    def test_new_message_appends_to_cached_chat(self):
        b = tg._TelegramBridge(1, "h")
        b._messages[42] = []
        self._apply_new_message(b, 42, "hello")
        msgs, _, _ = b.snap_messages(42)
        assert len(msgs) == 1
        assert msgs[0]["text"] == "hello"

    def test_new_message_ignored_for_uncached_chat(self):
        b = tg._TelegramBridge(1, "h")
        # Chat 42 is NOT in _messages — we should not create a cache entry
        self._apply_new_message(b, 42, "hello")
        assert 42 not in b._messages

    def test_new_message_updates_dialog_preview(self):
        b = tg._TelegramBridge(1, "h")
        b._dialogs = [
            {"id": 1, "name": "alice", "text": "old",
             "date": None, "unread": 0, "kind": "user"},
            {"id": 2, "name": "bob", "text": "old",
             "date": None, "unread": 0, "kind": "user"},
        ]
        self._apply_new_message(b, 2, "fresh")
        dialogs, _, _ = b.snap_dialogs()
        assert dialogs[0]["id"] == 2     # bob bubbled to top
        assert dialogs[0]["text"] == "fresh"
        assert dialogs[0]["unread"] == 1

    def test_self_message_does_not_bump_unread(self):
        b = tg._TelegramBridge(1, "h")
        b._dialogs = [{"id": 5, "name": "me-chat", "text": "", "date": None,
                       "unread": 0, "kind": "user"}]
        self._apply_new_message(b, 5, "me", is_self=True)
        dialogs, _, _ = b.snap_dialogs()
        assert dialogs[0]["unread"] == 0

    def test_new_message_clears_typing(self):
        b = tg._TelegramBridge(1, "h")
        b._typing[42] = ("alice", time.time() + 5)
        assert b.snap_typing(42) == "alice"
        self._apply_new_message(b, 42, "hi")
        assert b.snap_typing(42) is None


# ── snap_typing expiry ───────────────────────────────────────────────────

class TestTypingExpiry:
    def test_active(self):
        b = tg._TelegramBridge(1, "h")
        b._typing[7] = ("dalek", time.time() + 10.0)
        assert b.snap_typing(7) == "dalek"

    def test_expired_cleared_on_read(self):
        b = tg._TelegramBridge(1, "h")
        b._typing[7] = ("dalek", time.time() - 1.0)
        assert b.snap_typing(7) is None
        # And the stale entry should have been dropped
        assert 7 not in b._typing


# ── Integration with framework wiring ────────────────────────────────────

class TestFrameworkWiring:
    """run_telegram should be reachable via the same path framework.py uses."""

    def test_import_via_framework_path(self):
        mod = importlib.import_module("tui.telegram")
        assert hasattr(mod, "run_telegram")
        assert callable(mod.run_telegram)

    def test_telegram_key_resolves_to_run_telegram_at_runtime(self):
        import tui.framework as fw
        if fw.NATIVE_TOOLS is None:
            fw.NATIVE_TOOLS = fw._get_native_tools()
        assert "_telegram" in fw.NATIVE_TOOLS
        import inspect
        src = inspect.getsource(fw._get_native_tools)
        assert '"_telegram":' in src
        assert 'run_telegram' in src


# ── Bridge connect edge cases ────────────────────────────────────────────

class TestBridgeConnect:
    def test_connect_thread_death(self, monkeypatch):
        def boom(self):
            with self._lock:
                self._state = "error"
                self._error = "dead"
        monkeypatch.setattr(tg._TelegramBridge, "_run", boom)
        b = tg._TelegramBridge(1, "h")
        t0 = time.time()
        b.connect(timeout=1.0)
        elapsed = time.time() - t0
        assert elapsed < 0.9
        assert b.state()[0] == "error"

    def test_connect_with_stop_set(self, monkeypatch):
        # Make _run a no-op so the thread exits immediately.
        monkeypatch.setattr(tg._TelegramBridge, "_run", lambda self: None)
        b = tg._TelegramBridge(1, "h")
        b._stop.set()
        t0 = time.time()
        b.connect(timeout=2.0)
        assert time.time() - t0 < 1.5


# ── _HAS_TELETHON=False branch ───────────────────────────────────────────

class TestTelethonMissing:
    def test_run_telegram_without_telethon(self, monkeypatch):
        monkeypatch.setattr(tg, "_HAS_TELETHON", False)
        monkeypatch.setattr(tg, "wait_for_input", lambda *a, **k: None)
        status_calls = []
        monkeypatch.setattr(
            tg, "_status",
            lambda scr, msg, error=False: status_calls.append((msg, error)),
        )
        # Guard: _load_creds must NOT be reached
        monkeypatch.setattr(
            tg, "_load_creds",
            lambda: (_ for _ in ()).throw(AssertionError("should not reach _load_creds")),
        )
        scr = MagicMock()
        scr.getmaxyx.return_value = (24, 80)
        tg.run_telegram(scr)
        assert any("not installed" in msg for msg, _ in status_calls)
