"""Telegram client for uConsole TUI.

Phase 1: async bridge + auth gate + connected placeholder.
Architecture: Telethon runs on a background asyncio thread. Shared state is
guarded by a threading.Lock; commands flow curses→bg via a queue.Queue, and
results flow back via a result queue. Pattern mirrors tui/marauder.py:_Conn.
"""
import asyncio
import curses
import datetime
import json
import os
import queue
import threading
import time

from tui.framework import (
    C_HEADER, C_STATUS, C_DIM, C_ITEM, C_SEL, C_CAT, C_DESC, C_FOOTER, C_BORDER,
    wait_for_input, _tui_input_loop, open_gamepad,
)
from tui.network import _tui_form
import tui_lib as tui

try:
    from telethon import TelegramClient, events
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        FloodWaitError,
    )
    _HAS_TELETHON = True
except ImportError:
    _HAS_TELETHON = False


CONF_DIR = os.path.expanduser("~/.config/uconsole")
CRED_FILE = os.path.join(CONF_DIR, "telegram.json")
SESSION_PATH = os.path.join(CONF_DIR, "telegram")


# ── Bridge ──────────────────────────────────────────────────────────────

class _TelegramBridge:
    """Thread-safe bridge between the sync curses loop and async Telethon."""

    def __init__(self, api_id, api_hash):
        self.api_id = int(api_id)
        self.api_hash = str(api_hash)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._loop = None
        self._client = None
        self._cmd_q = queue.Queue()
        self._result_q = queue.Queue()
        # shared state (under _lock)
        self._state = "init"   # init | needs_auth | connected | error
        self._error = None
        self._me = None        # display name once connected
        self._dialogs = []     # list of dialog dicts
        self._dialogs_loading = False
        self._dialogs_error = None
        self._messages = {}    # chat_id -> list of message dicts (oldest first)
        self._msgs_loading = set()   # chat_ids currently being fetched
        self._msgs_error = {}        # chat_id -> error string
        self._typing = {}      # chat_id -> (name, expires_at)
        self._typing_last_sent = {}  # chat_id -> ts of last outgoing typing event

    # ---- lifecycle ----

    def connect(self, timeout=15.0):
        """Start the background thread. Returns once state leaves 'init'."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._stop.is_set():
                return
            if not self._thread.is_alive():
                return
            with self._lock:
                if self._state != "init":
                    return
            time.sleep(0.1)

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def state(self):
        with self._lock:
            return self._state, self._error, self._me

    # ---- commands (curses → bg) ----

    def _cmd_await(self, cmd, timeout=60):
        # drop any stale results
        while True:
            try:
                self._result_q.get_nowait()
            except queue.Empty:
                break
        self._cmd_q.put(cmd)
        try:
            return self._result_q.get(timeout=timeout)
        except queue.Empty:
            return ("error", "timeout")

    def request_code(self, phone):
        return self._cmd_await(("request_code", phone))

    def sign_in(self, phone, code):
        return self._cmd_await(("sign_in", phone, code))

    def sign_in_2fa(self, password):
        return self._cmd_await(("sign_in_2fa", password))

    def fetch_dialogs(self):
        """Enqueue a dialog list refresh. Non-blocking. Read via snap_dialogs()."""
        with self._lock:
            self._dialogs_loading = True
            self._dialogs_error = None
        self._cmd_q.put(("fetch_dialogs",))

    def snap_dialogs(self):
        with self._lock:
            return list(self._dialogs), self._dialogs_loading, self._dialogs_error

    def fetch_history(self, chat_id):
        """Enqueue a history fetch for a chat. Non-blocking."""
        with self._lock:
            self._msgs_loading.add(chat_id)
            self._msgs_error.pop(chat_id, None)
        self._cmd_q.put(("fetch_history", chat_id))

    def send(self, chat_id, text):
        """Enqueue a send. Non-blocking; result appears in snap_messages() shortly."""
        self._cmd_q.put(("send", chat_id, text))

    def send_typing(self, chat_id):
        """Tell Telegram the user is typing. Debounced to ≤1 send / 4s per chat."""
        now = time.time()
        with self._lock:
            self._typing_last_sent = {
                k: v for k, v in self._typing_last_sent.items()
                if now - v < 300
            }
            last = self._typing_last_sent.get(chat_id, 0)
            if now - last < 4.0:
                return
            self._typing_last_sent[chat_id] = now
        self._cmd_q.put(("send_typing", chat_id))

    def snap_typing(self, chat_id):
        """Return the name of whoever is currently typing in this chat, or None."""
        now = time.time()
        with self._lock:
            entry = self._typing.get(chat_id)
            if entry is None:
                return None
            name, expires = entry
            if now > expires:
                self._typing.pop(chat_id, None)
                return None
            return name

    def snap_messages(self, chat_id):
        with self._lock:
            msgs = list(self._messages.get(chat_id, []))
            loading = chat_id in self._msgs_loading
            err = self._msgs_error.get(chat_id)
            return msgs, loading, err

    # ---- bg thread ----

    def _run(self):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._async_main())
        except Exception as e:
            with self._lock:
                self._state = "error"
                self._error = f"loop crashed: {e}"

    async def _async_main(self):
        try:
            os.makedirs(CONF_DIR, exist_ok=True)
            try:
                os.chmod(CONF_DIR, 0o700)
            except OSError:
                pass
            self._client = TelegramClient(SESSION_PATH, self.api_id, self.api_hash)
            await self._client.connect()
            try:
                os.chmod(SESSION_PATH + ".session", 0o600)
            except OSError:
                pass
            if await self._client.is_user_authorized():
                me = await self._client.get_me()
                with self._lock:
                    self._me = _format_name(me)
                    self._state = "connected"
                self._register_event_handlers()
            else:
                with self._lock:
                    self._state = "needs_auth"
        except Exception as e:
            with self._lock:
                self._state = "error"
                self._error = str(e)
            return

        # Main command loop. Uses non-blocking get + asyncio sleep so the
        # Telethon event loop keeps pumping updates (NewMessage etc.) between
        # commands instead of being frozen by a blocking queue.get().
        while not self._stop.is_set():
            try:
                cmd = self._cmd_q.get_nowait()
                await self._dispatch(cmd)
            except queue.Empty:
                await asyncio.sleep(0.05)

        try:
            await self._client.disconnect()
        except Exception:
            pass

    def _register_event_handlers(self):
        """Wire up live update handlers for incoming messages."""

        @self._client.on(events.UserUpdate)
        async def _on_user_update(event):
            try:
                if event.action is None or not event.typing:
                    return
                chat_id = event.chat_id
                if chat_id is None:
                    return
                name = None
                try:
                    u = await event.get_user()
                    if u is not None:
                        name = _format_name(u)
                except Exception:
                    pass
                if not name:
                    name = "someone"
                with self._lock:
                    self._typing[chat_id] = (name, time.time() + 6.0)
            except Exception:
                pass

        @self._client.on(events.NewMessage)
        async def _on_new_message(event):
            try:
                chat_id = event.chat_id
                if chat_id is None:
                    return
                formatted = _format_message(event.message)
                with self._lock:
                    # Incoming message ends any prior typing indicator
                    self._typing.pop(chat_id, None)
                    # Append to cached history if we've ever opened this chat
                    if chat_id in self._messages:
                        self._messages[chat_id].append(formatted)
                        if len(self._messages[chat_id]) > 200:
                            del self._messages[chat_id][:-200]
                    # Update the dialog preview + bump unread
                    preview = formatted["text"] or "[media]"
                    moved = None
                    for i, d in enumerate(self._dialogs):
                        if d["id"] == chat_id:
                            d["text"] = preview
                            d["date"] = formatted["date"]
                            if not formatted["is_self"]:
                                d["unread"] = (d.get("unread") or 0) + 1
                            moved = i
                            break
                    # Bump that dialog to the top of the list
                    if moved is not None and moved > 0:
                        self._dialogs.insert(0, self._dialogs.pop(moved))
            except Exception:
                # Never let handler exceptions crash the bg thread
                pass

    async def _dispatch(self, cmd):
        op = cmd[0]
        try:
            if op == "request_code":
                await self._client.send_code_request(cmd[1])
                self._result_q.put(("ok", None))

            elif op == "sign_in":
                _, phone, code = cmd
                try:
                    await self._client.sign_in(phone, code)
                    await self._mark_connected()
                    self._result_q.put(("ok", None))
                except SessionPasswordNeededError:
                    self._result_q.put(("need_2fa", None))

            elif op == "sign_in_2fa":
                await self._client.sign_in(password=cmd[1])
                await self._mark_connected()
                self._result_q.put(("ok", None))

            elif op == "fetch_dialogs":
                await self._do_fetch_dialogs()

            elif op == "fetch_history":
                await self._do_fetch_history(cmd[1])

            elif op == "send":
                await self._do_send(cmd[1], cmd[2])

            elif op == "send_typing":
                try:
                    await self._client.action(cmd[1], "typing")
                except Exception:
                    pass

        except PhoneCodeInvalidError:
            self._result_q.put(("error", "invalid code"))
        except FloodWaitError as e:
            self._result_q.put(("error", f"flood wait {e.seconds}s"))
        except Exception as e:
            if op in ("request_code", "sign_in", "sign_in_2fa"):
                self._result_q.put(("error", str(e)))
            else:
                import sys
                print(f"telegram _dispatch {op} error: {e}", file=sys.stderr)

    async def _mark_connected(self):
        me = await self._client.get_me()
        with self._lock:
            self._me = _format_name(me)
            self._state = "connected"
        self._register_event_handlers()

    async def _do_fetch_dialogs(self):
        """Fetch the dialog list and update shared state. Swallows exceptions
        into _dialogs_error so the curses loop can render them."""
        try:
            dialogs = await self._client.get_dialogs(limit=100)
            out = []
            for d in dialogs:
                msg = d.message
                text = _extract_msg_preview(msg)
                out.append({
                    "id": d.id,
                    "name": d.name or "(unnamed)",
                    "text": text,
                    "date": d.date,
                    "unread": d.unread_count or 0,
                    "kind": (
                        "user" if d.is_user
                        else "channel" if d.is_channel
                        else "group"
                    ),
                })
            with self._lock:
                self._dialogs = out
                self._dialogs_loading = False
                self._dialogs_error = None
        except Exception as e:
            with self._lock:
                self._dialogs_loading = False
                self._dialogs_error = str(e)

    async def _do_fetch_history(self, chat_id):
        try:
            raw = await self._client.get_messages(chat_id, limit=50)
            # Telethon returns newest first; we want oldest first.
            out = []
            for m in reversed(raw):
                out.append(_format_message(m))
            with self._lock:
                self._messages[chat_id] = out
                self._msgs_loading.discard(chat_id)
                self._msgs_error.pop(chat_id, None)
        except Exception as e:
            with self._lock:
                self._msgs_loading.discard(chat_id)
                self._msgs_error[chat_id] = str(e)

    async def _do_send(self, chat_id, text):
        try:
            sent = await self._client.send_message(chat_id, text)
            formatted = _format_message(sent)
            with self._lock:
                msgs = self._messages.setdefault(chat_id, [])
                msgs.append(formatted)
                # Update the dialog preview so chat list reflects the send.
                for d in self._dialogs:
                    if d["id"] == chat_id:
                        d["text"] = formatted["text"] or "[sent]"
                        d["date"] = formatted["date"]
                        break
        except Exception as e:
            with self._lock:
                self._msgs_error[chat_id] = f"send: {e}"


def _format_name(me):
    parts = [p for p in (getattr(me, "first_name", None),
                         getattr(me, "last_name", None)) if p]
    return " ".join(parts) or getattr(me, "username", None) or f"id:{me.id}"


def _format_message(m):
    """Extract a renderable dict from a Telethon Message."""
    text = _extract_msg_preview(m)
    sender = None
    try:
        s = m.sender
        if s is not None:
            sender = _format_name(s)
    except Exception:
        pass
    is_self = bool(getattr(m, "out", False))
    return {
        "id": m.id,
        "text": text,
        "date": getattr(m, "date", None),
        "sender": sender,
        "is_self": is_self,
    }


def _wrap_text(text, width):
    """Greedy word-wrap. Returns list of lines. Handles explicit \\n."""
    if width <= 0:
        return [""]
    if not text:
        return [""]
    lines = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for word in para.split(" "):
            if not word:
                if cur:
                    if len(cur) + 1 <= width:
                        cur += " "
                    else:
                        lines.append(cur)
                        cur = ""
                continue
            if len(cur) + len(word) + (1 if cur else 0) <= width:
                cur = f"{cur} {word}" if cur else word
            else:
                if cur:
                    lines.append(cur)
                # word itself may be longer than width
                while len(word) > width:
                    lines.append(word[:width])
                    word = word[width:]
                cur = word
        if cur:
            lines.append(cur)
    return lines or [""]


def _format_hhmm(dt):
    if dt is None:
        return ""
    try:
        return dt.astimezone().strftime("%H:%M")
    except Exception:
        try:
            return dt.strftime("%H:%M")
        except Exception:
            return ""


def _extract_msg_preview(msg):
    """Best-effort single-line preview for a Telethon Message."""
    if msg is None:
        return ""
    # Prefer raw .message (plain text) over .text (markdown-reconstructed)
    text = getattr(msg, "message", None) or getattr(msg, "raw_text", None) or ""
    if text:
        return text.replace("\n", " ").strip()
    # Media-only message
    media = getattr(msg, "media", None)
    if media is None:
        return ""
    cls = type(media).__name__
    if "Photo" in cls:
        return "[Photo]"
    if "Document" in cls:
        return "[Document]"
    if "Voice" in cls or "Audio" in cls:
        return "[Voice]"
    if "Video" in cls:
        return "[Video]"
    if "Sticker" in cls:
        return "[Sticker]"
    if "Webpage" in cls:
        return "[Link]"
    return f"[{cls}]"


def _relative_time(dt):
    """Short relative time like 2m, 3h, 1d, Apr12."""
    if dt is None:
        return ""
    now = datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    if secs < 86400 * 7:
        return f"{secs // 86400}d"
    try:
        return dt.strftime("%b%d")
    except Exception:
        return ""


# ── Credentials ─────────────────────────────────────────────────────────

def _load_creds():
    try:
        with open(CRED_FILE) as f:
            d = json.load(f)
        ahash = d.get("api_hash")
        if not isinstance(ahash, str) or not ahash:
            return None, None
        return int(d["api_id"]), ahash
    except (FileNotFoundError, KeyError, json.JSONDecodeError, ValueError):
        return None, None


def _save_creds(api_id, api_hash):
    os.makedirs(CONF_DIR, exist_ok=True)
    try:
        os.chmod(CONF_DIR, 0o700)
    except OSError:
        pass
    tmp = CRED_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"api_id": int(api_id), "api_hash": str(api_hash)}, f)
        f.flush()
        os.fsync(fd)
    os.replace(tmp, CRED_FILE)


def _creds_setup(scr):
    result = _tui_form(scr, "Telegram API Credentials", [
        ("api_id (from my.telegram.org)", ""),
        ("api_hash", ""),
    ])
    if not result:
        return None, None
    try:
        aid = int(result["api_id (from my.telegram.org)"].strip())
    except ValueError:
        return None, None
    ahash = result["api_hash"].strip()
    if not ahash:
        return None, None
    _save_creds(aid, ahash)
    return aid, ahash


# ── Auth flow ───────────────────────────────────────────────────────────

def _auth_flow(scr, bridge):
    """Walk phone → code → optional 2FA. Returns True on success."""
    result = _tui_form(scr, "Telegram Login — Phone", [
        ("Phone (e.g. +15551234567)", ""),
    ])
    if not result:
        return False
    phone = result["Phone (e.g. +15551234567)"].strip()
    if not phone:
        return False

    _status(scr, "Requesting code...")
    status, err = bridge.request_code(phone)
    if status != "ok":
        _status(scr, f"Code request failed: {err}", error=True)
        wait_for_input()
        return False

    status = None
    err = None
    for attempt in range(3):
        result = _tui_form(scr, "Telegram Login — Code", [
            ("Verification code (from Telegram app or SMS)", ""),
        ])
        if not result:
            return False
        code = result["Verification code (from Telegram app or SMS)"].strip()
        if not code:
            return False

        _status(scr, "Signing in...")
        status, err = bridge.sign_in(phone, code)
        if status == "error" and err == "invalid code":
            _status(scr, "Invalid code, try again", error=True)
            curses.napms(800)
            continue
        break

    if status == "need_2fa":
        result = _tui_form(scr, "Telegram Login — 2FA Password", [
            ("Two-factor password", ""),
        ])
        if not result:
            return False
        pwd = result["Two-factor password"]
        _status(scr, "Verifying 2FA...")
        status, err = bridge.sign_in_2fa(pwd)

    if status == "ok":
        return True

    _status(scr, f"Sign-in failed: {err}", error=True)
    wait_for_input()
    return False


# ── Rendering helpers ───────────────────────────────────────────────────

def _status(scr, msg, error=False):
    h, w = scr.getmaxyx()
    scr.erase()
    attr = curses.color_pair(C_STATUS) | curses.A_BOLD
    if error:
        attr |= curses.A_STANDOUT
    scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w, attr)
    scr.refresh()


_KIND_GLYPH = {"user": "·", "group": "*", "channel": "#"}


def _chat_list_view(scr, bridge):
    """Framed scrollable dialog list. Each entry is 2 rows inside a panel."""
    js = open_gamepad()
    try:
        sel = 0
        scroll = 0
        bridge.fetch_dialogs()

        while True:
            h, w = scr.getmaxyx()
            dialogs, loading, err = bridge.snap_dialogs()
            _, _, me = bridge.state()
            scr.erase()

            # ── Outer panel ──────────────────────────────────────────
            px, py = 0, 0
            pw = w
            ph = h - 1  # leave last row for footer
            detail = (
                "loading…" if loading
                else f"err: {err}"[: pw - 20] if err
                else f"{me or '?'} · {len(dialogs)} chats"
            )
            tui.panel_top(scr, py, px, pw, title="TELEGRAM", detail=detail)
            for r in range(1, ph - 1):
                tui.panel_side(scr, py + r, px, pw)
            tui.panel_bot(scr, py + ph - 1, px, pw)

            # Content area inside the panel
            inner_left = px + 2
            inner_right = px + pw - 2
            inner_top = py + 1
            inner_bot = py + ph - 2
            inner_w = inner_right - inner_left
            per_item = 3  # name row + preview row + blank spacer
            capacity = max(1, (inner_bot - inner_top) // per_item)

            # Scroll window
            if sel < scroll:
                scroll = sel
            elif sel >= scroll + capacity:
                scroll = sel - capacity + 1

            if not dialogs:
                msg = (
                    "Loading dialogs…" if loading
                    else (err or "No chats. Press R to refresh.")
                )
                tui.put(scr, inner_top + (inner_bot - inner_top) // 2,
                        inner_left + max(0, (inner_w - len(msg)) // 2),
                        msg, inner_w, curses.color_pair(C_DIM))
            else:
                for i in range(capacity):
                    idx = scroll + i
                    if idx >= len(dialogs):
                        break
                    d = dialogs[idx]
                    y = inner_top + 1 + i * per_item
                    if y + 1 > inner_bot:
                        break
                    selected = idx == sel

                    glyph = _KIND_GLYPH.get(d["kind"], "·")
                    rtime = _relative_time(d["date"])
                    unread = d["unread"]

                    name_attr = (
                        curses.color_pair(C_SEL) | curses.A_BOLD | curses.A_REVERSE
                        if selected
                        else curses.color_pair(C_ITEM) | curses.A_BOLD
                    )
                    time_attr = (
                        curses.color_pair(C_SEL) | curses.A_REVERSE if selected
                        else curses.color_pair(C_DIM)
                    )
                    preview_attr = (
                        curses.color_pair(C_SEL) | curses.A_REVERSE if selected
                        else curses.color_pair(C_DESC)
                    )
                    kind_pair = {
                        "channel": C_CAT,
                        "group":   C_HEADER,
                        "user":    C_ITEM,
                    }.get(d["kind"], C_ITEM)
                    glyph_attr = (
                        curses.color_pair(C_SEL) | curses.A_REVERSE if selected
                        else curses.color_pair(kind_pair) | curses.A_BOLD
                    )

                    # Row 1: glyph + name + unread badge + time
                    badge = f" ⬤{unread}" if unread else ""
                    name_line = f" {glyph} {d['name']}{badge}"
                    name_w = max(4, inner_w - len(rtime) - 2)
                    tui.put(scr, y, inner_left, " " * inner_w, inner_w, name_attr)
                    tui.put(scr, y, inner_left, name_line[:name_w], name_w, name_attr)
                    # Overwrite glyph with kind-colored version (first non-space char pos)
                    tui.put(scr, y, inner_left + 1, glyph, 1, glyph_attr)
                    tui.put(scr, y, inner_right - len(rtime), rtime, len(rtime),
                            time_attr)

                    # Row 2: indented preview
                    preview = d["text"] or ""
                    preview = preview[: inner_w - 6]
                    tui.put(scr, y + 1, inner_left, " " * inner_w, inner_w,
                            preview_attr)
                    tui.put(scr, y + 1, inner_left + 4, preview, inner_w - 5,
                            preview_attr)

            # ── Footer ───────────────────────────────────────────────
            hint = " ↑↓ Select   ⏎ Open   R Refresh   Q Back "
            tui.put(scr, h - 1, 0, hint.center(w)[:w], w,
                    curses.color_pair(C_FOOTER))

            scr.refresh()
            scr.timeout(500)
            key, gp = _tui_input_loop(scr, js)

            if key in (ord("q"), ord("Q"), 27) or gp in ("back", "quit"):
                return
            if key in (curses.KEY_DOWN, ord("j")):
                if dialogs:
                    sel = min(len(dialogs) - 1, sel + 1)
            elif key in (curses.KEY_UP, ord("k")):
                sel = max(0, sel - 1)
            elif key == curses.KEY_NPAGE:
                sel = min(len(dialogs) - 1, sel + capacity) if dialogs else 0
            elif key == curses.KEY_PPAGE:
                sel = max(0, sel - capacity)
            elif key in (ord("r"), ord("R")) or gp == "refresh":
                bridge.fetch_dialogs()
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                if dialogs:
                    _conversation_view(scr, bridge, dialogs[sel])
    finally:
        if js:
            js.close()


def _conversation_view(scr, bridge, dialog):
    """Framed message history for one chat.

    Rendering: each message is a header line (sender + time) plus one or more
    wrapped body lines. Layout is computed bottom-up (newest at bottom of the
    panel). A scroll offset counts lines from the bottom — 0 means pinned to
    the latest message.
    """
    js = open_gamepad()
    try:
        chat_id = dialog["id"]
        bridge.fetch_history(chat_id)
        scroll_from_bot = 0
        typing = False
        input_buf = []
        last_msg_count = 0

        while True:
            h, w = scr.getmaxyx()
            msgs, loading, err = bridge.snap_messages(chat_id)
            scr.erase()

            # ── Outer panel ──────────────────────────────────────────
            px, py = 0, 0
            pw, ph = w, h - 1
            kind_glyph = _KIND_GLYPH.get(dialog["kind"], "·")
            title = f"{kind_glyph} {dialog['name']}"[: pw - 12]
            if loading and not msgs:
                detail = "loading…"
            elif err:
                detail = f"err: {err}"[: pw - len(title) - 10]
            else:
                detail = f"{len(msgs)} msgs"
            tui.panel_top(scr, py, px, pw, title=title, detail=detail)
            for r in range(1, ph - 1):
                tui.panel_side(scr, py + r, px, pw)
            tui.panel_bot(scr, py + ph - 1, px, pw)

            inner_left = px + 2
            inner_right = px + pw - 2
            inner_top = py + 1
            inner_bot = py + ph - 2
            inner_w = inner_right - inner_left
            inner_h = inner_bot - inner_top + 1

            # Build render lines for *all* messages, then window.
            # Each entry: (kind, text, attr, align)
            #   kind: "header" | "body" | "spacer"
            #   align: "left" | "right"
            render_lines = []
            body_w_left = max(10, inner_w - 4)
            body_w_right = max(10, int(inner_w * 0.65))

            if not msgs:
                mid = inner_top + inner_h // 2
                msg = "Loading messages…" if loading else (err or "No messages")
                tui.put(scr, mid, inner_left + max(0, (inner_w - len(msg)) // 2),
                        msg, inner_w, curses.color_pair(C_DIM))
            else:
                for m in msgs:
                    align = "right" if m["is_self"] else "left"
                    sender = (
                        "You" if m["is_self"]
                        else (m["sender"] or dialog["name"])
                    )
                    hhmm = _format_hhmm(m["date"])
                    # Own messages show time first, others show sender first
                    if m["is_self"]:
                        header = f"{hhmm}  You".strip()
                        header_attr = curses.color_pair(C_CAT) | curses.A_BOLD
                        body_attr = curses.color_pair(C_CAT)
                        body_w = body_w_right
                    else:
                        header = f"{sender}  {hhmm}".rstrip()
                        header_attr = curses.color_pair(C_HEADER) | curses.A_BOLD
                        body_attr = curses.color_pair(C_ITEM)
                        body_w = body_w_left
                    render_lines.append(("header", header, header_attr, align))
                    for line in _wrap_text(m["text"] or "", body_w):
                        render_lines.append(("body", line, body_attr, align))
                    render_lines.append(("spacer", "", 0, "left"))

                # Drop trailing spacer
                if render_lines and render_lines[-1][0] == "spacer":
                    render_lines.pop()

                total = len(render_lines)
                max_scroll = max(0, total - inner_h)
                scroll_from_bot = min(scroll_from_bot, max_scroll)
                scroll_from_bot = max(0, scroll_from_bot)
                end = total - scroll_from_bot
                start = max(0, end - inner_h)
                visible = render_lines[start:end]

                # Render from top of inner area down
                y = inner_top
                # If we have fewer lines than inner_h, push content to bottom so
                # latest message sits at the bottom (more natural).
                pad = max(0, inner_h - len(visible))
                y += pad
                for kind, text, attr, align in visible:
                    if kind == "spacer":
                        y += 1
                        continue
                    if align == "right":
                        # Right-align flush to the panel's inner right edge.
                        x = inner_right - len(text)
                        x = max(inner_left, x)
                    else:
                        indent = 0 if kind == "header" else 2
                        x = inner_left + indent
                    tui.put(scr, y, x, text, inner_right - x, attr)
                    y += 1

                # Scroll indicator
                if max_scroll > 0:
                    up_pos = int(
                        inner_top + ((total - end) / total) * (inner_h - 1)
                    )
                    dn_pos = int(
                        inner_top + ((total - start) / total) * (inner_h - 1)
                    )
                    try:
                        tui.put(scr, max(inner_top, up_pos), inner_right, "▲",
                                1, curses.color_pair(C_DIM))
                        tui.put(scr, min(inner_bot, dn_pos), inner_right, "▼",
                                1, curses.color_pair(C_DIM))
                    except curses.error:
                        pass

            # Auto-pin to bottom when a new message arrives while we're already
            # at the bottom. If user has scrolled up, preserve their position.
            if msgs and len(msgs) != last_msg_count:
                if scroll_from_bot == 0:
                    pass  # already pinned — new msg will show
                last_msg_count = len(msgs)

            # ── Typing indicator (incoming) ───────────────────────────
            typer = bridge.snap_typing(chat_id)
            if typer and inner_bot >= inner_top:
                # Render a dim italic-ish line at the bottom of the panel's
                # inner area. Uses a dot-cycle animation.
                dots = "." * (1 + int(time.time() * 2) % 3)
                indicator = f"  {typer} is typing{dots}"
                tui.put(scr, inner_bot, inner_left,
                        indicator[: inner_w].ljust(inner_w),
                        inner_w, curses.color_pair(C_DIM) | curses.A_BOLD)

            # ── Footer / input bar ───────────────────────────────────
            if typing:
                buf_str = "".join(input_buf)
                prompt = "▶ "
                tail = "   ⏎ send · Esc cancel"
                avail = w - len(prompt) - len(tail) - 1
                # Show the tail end of the buffer if it's longer than avail
                display = buf_str[-avail:] if len(buf_str) > avail else buf_str
                bar = f"{prompt}{display}_{' ' * max(0, avail - len(display) - 1)}{tail}"
                tui.put(scr, h - 1, 0, bar[:w], w,
                        curses.color_pair(C_HEADER) | curses.A_BOLD)
            else:
                hint = " ↑↓ Scroll   i Compose   R Refresh   End Latest   B Back "
                tui.put(scr, h - 1, 0, hint.center(w)[:w], w,
                        curses.color_pair(C_FOOTER))

            scr.refresh()
            scr.timeout(500)
            key, gp = _tui_input_loop(scr, js)

            if typing:
                if key == 27:  # Esc — cancel compose
                    typing = False
                    input_buf.clear()
                elif key in (curses.KEY_ENTER, 10, 13):
                    text = "".join(input_buf).strip()
                    input_buf.clear()
                    typing = False
                    if text:
                        bridge.send(chat_id, text)
                        scroll_from_bot = 0  # jump to bottom to see our msg
                elif key in (curses.KEY_BACKSPACE, 127, 8):
                    if input_buf:
                        input_buf.pop()
                elif key is not None and 32 <= key <= 126:
                    input_buf.append(chr(key))
                    bridge.send_typing(chat_id)
                # Ignore everything else while typing (no navigation)
                continue

            # Navigation mode
            if key in (ord("q"), ord("Q"), 27, ord("b"), ord("B")) or gp in ("back", "quit"):
                return
            if key in (ord("i"), ord("I")) or key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                typing = True
            elif key in (curses.KEY_UP, ord("k")):
                scroll_from_bot += 1
            elif key in (curses.KEY_DOWN, ord("j")):
                scroll_from_bot = max(0, scroll_from_bot - 1)
            elif key == curses.KEY_PPAGE:
                scroll_from_bot += max(1, inner_h - 2)
            elif key == curses.KEY_NPAGE:
                scroll_from_bot = max(0, scroll_from_bot - max(1, inner_h - 2))
            elif key == curses.KEY_END:
                scroll_from_bot = 0
            elif key == curses.KEY_HOME:
                scroll_from_bot = 10**9  # clamped later
            elif key in (ord("r"), ord("R")) or gp == "refresh":
                bridge.fetch_history(chat_id)
    finally:
        if js:
            js.close()


# ── Entry point ─────────────────────────────────────────────────────────

def run_telegram(scr):
    if not _HAS_TELETHON:
        _status(scr, "telethon not installed: pip3 install --user telethon",
                error=True)
        wait_for_input()
        return

    api_id, api_hash = _load_creds()
    if not api_id:
        _status(scr, "First-time setup: enter API credentials")
        curses.napms(400)
        api_id, api_hash = _creds_setup(scr)
        if not api_id:
            return

    bridge = _TelegramBridge(api_id, api_hash)
    try:
        _status(scr, "Connecting to Telegram...")
        bridge.connect()

        state, err, me = bridge.state()
        if state == "error":
            _status(scr, f"Connection failed: {err}", error=True)
            wait_for_input()
            return
        if state == "init":
            _status(scr, "Connect timed out — check network and retry",
                    error=True)
            wait_for_input()
            return

        if state == "needs_auth":
            if not _auth_flow(scr, bridge):
                return

        _chat_list_view(scr, bridge)
    finally:
        bridge.close()


HANDLERS = {
    "_telegram": run_telegram,
}
