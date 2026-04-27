"""TUI module: ESP32 hub — firmware detect, dynamic submenu, flash flows."""

import curses
import subprocess
import threading
import time

from tui.framework import (
    C_DIM,
    C_HEADER,
    C_STATUS,
    SUBMENUS,
    run_submenu,
)

# ── ESP32 dynamic submenu items ──────────────────────────────────────────

_ESP32_MICROPYTHON_ITEMS = [
    ("Live Monitor",     "_esp32_monitor",            "real-time sensor dashboard",             "action",     "📈"),
    ("Serial Monitor",   "radio/esp32.sh serial",     "raw serial output",                      "fullscreen", "🔌"),
    ("Status",           "radio/esp32.sh status",     "latest sensor reading + chip info",      "panel",      "🩺"),
    ("REPL",             "radio/esp32.sh repl",       "MicroPython interactive shell",          "fullscreen", "🐚"),
    ("Flash Scripts",    "radio/esp32.sh flash",      "upload boot.py + main.py",               "stream",     "⚡"),
    ("Log Entry",        "radio/esp32.sh log",        "append reading to esp32.log",            "action",     "📝"),
]

_ESP32_MARAUDER_ITEMS = [
    ("Marauder",         "_marauder",                      "WiFi/BLE attack toolkit",                "action",     "💀"),
    ("War Drive (BETA)", "_wardrive",                      "GPS-tagged AP sweep → CSV",              "action",     "🚗"),
    ("Replay Session",   "_wardrive_replay",               "browse + replay past war-drive CSVs",    "action",     "🎞️"),
    ("Serial Monitor",   "radio/esp32-marauder.sh serial", "raw Marauder output",                    "fullscreen", "🔌"),
    ("Status",           "radio/esp32-marauder.sh info",   "firmware, MAC, hardware",                "panel",      "🩺"),
    ("Settings",         "radio/esp32-marauder.sh settings","Marauder settings",                     "panel",      "🛠️"),
]

_ESP32_COMMON_ITEMS = [
    ("USB Reset",          "_esp32_usb_reset",          "power cycle ESP32 via USB reset",            "action",     "🔌"),
    ("Re-detect",          "_esp32_redetect",           "re-probe firmware handshake",                "action",     "🔁"),
    ("Backup FW",          "_esp32_backup",             "dump current flash to ~/esp32-backup-*.bin", "action",     "💾"),
    ("Reflash",            "_esp32_flash",              "pick firmware: MicroPython, Marauder, Bruce, MimiClaw", "action", "⚡"),
    ("Install Bruce (1-tap)", "_esp32_install_watchdogs", "auto-detect chip + flash Bruce variant",  "action",     "🐶"),
    ("Clear FW Cache",     "_esp32_fw_cache_clear",     "delete downloaded Bruce firmware bins",      "action",     "🗑️"),
]


_ESP32_MIMICLAW_ITEMS = [
    ("Chat",             "_mimiclaw_chat",      "talk to MimiClaw AI agent",              "action",     "💬"),
    ("Serial Monitor",   "_mimiclaw_serial",    "raw serial output from MimiClaw",        "action",     "🔌"),
    ("Status",           "_mimiclaw_status",    "agent status and WiFi info",             "action",     "🩺"),
    ("Settings",         "sub:mimiclaw:settings","WiFi, tokens, model provider",          "submenu",    "🛠️"),
]


def _esp32_menu_for(firmware):
    """Return submenu items for the detected firmware mode."""
    from tui.esp32_detect import Firmware
    if firmware == Firmware.MICROPYTHON:
        items = list(_ESP32_MICROPYTHON_ITEMS)
    elif firmware == Firmware.MARAUDER:
        items = list(_ESP32_MARAUDER_ITEMS)
    elif firmware == Firmware.MIMICLAW:
        items = list(_ESP32_MIMICLAW_ITEMS)
    else:
        items = [
            ("Manual: MicroPython", "_esp32_force_mp",  "assume MicroPython firmware",  "action", "🐍"),
            ("Manual: Marauder",    "_esp32_force_mrd", "assume Marauder firmware",     "action", "☠"),
            ("Manual: MimiClaw",    "_esp32_force_mc",  "assume MimiClaw firmware",     "action", "🐾"),
        ]
    items.extend(_ESP32_COMMON_ITEMS)
    return items


def run_esp32_hub(scr):
    """ESP32 hub — detect firmware, show appropriate submenu."""
    from tui.esp32_detect import Firmware, detect

    # Release Marauder serial connection if held (so detect() can open the port)
    try:
        from tui.marauder import _inst as _mrd_inst
        if _mrd_inst and getattr(_mrd_inst, 'port', None):
            _mrd_inst.close()
    except Exception:
        pass

    h, w = scr.getmaxyx()
    scr.erase()

    msg = " Detecting ESP32 firmware... "
    scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w,
                curses.color_pair(C_HEADER) | curses.A_BOLD)
    scr.refresh()

    firmware = detect()

    SUBMENUS["sub:esp32"] = _esp32_menu_for(firmware)

    badge = {
        Firmware.MICROPYTHON: "MicroPython",
        Firmware.MARAUDER: "Marauder",
        Firmware.BRUCE: "Bruce",
        Firmware.MIMICLAW: "MimiClaw",
        Firmware.UNKNOWN: "Unknown",
    }.get(firmware, "Unknown")

    run_submenu(scr, "sub:esp32", f"ESP32 [{badge}]")


def run_esp32_flash_picker(scr):
    """Switch firmware — pick target and flash with safety gates."""
    from tui.esp32_detect import Firmware, detect, invalidate_cache
    from tui.esp32_flash import list_watchdogs_variants
    from tui.esp32_detect import detect_board_variant

    current = detect()

    options = [
        (Firmware.MICROPYTHON, "MicroPython"),
        (Firmware.MARAUDER,    "Marauder"),
        (Firmware.BRUCE,       "Bruce"),
        (Firmware.MIMICLAW,    "MimiClaw"),
    ]

    h, w = scr.getmaxyx()
    scr.erase()
    title = " Flash which firmware? "
    scr.addnstr(1, max(0, (w - len(title)) // 2), title, w,
                curses.color_pair(C_HEADER) | curses.A_BOLD)

    sel = 0
    for i, (fw, name) in enumerate(options):
        if fw == current:
            sel = i
    if current == Firmware.UNKNOWN:
        sel = 1

    scr.timeout(-1)
    while True:
        for i, (fw, name) in enumerate(options):
            marker = ">" if i == sel else " "
            tag = "  (current)" if fw == current else ""
            line = f" {marker} {i+1}. {name}{tag} "
            attr = curses.A_BOLD | curses.color_pair(
                C_HEADER if i == sel else C_DIM)
            try:
                scr.addnstr(3 + i, max(0, (w - len(line)) // 2),
                            line, w - 1, attr)
            except curses.error:
                pass
        hint = " up/down select  Enter confirm  Q cancel "
        try:
            scr.addnstr(h - 1, 0, hint[:w - 1].center(w - 1), w - 1,
                        curses.color_pair(C_DIM))
        except curses.error:
            pass
        scr.refresh()
        key = scr.getch()
        if key in (curses.KEY_UP, ord("k")):
            sel = (sel - 1) % len(options)
        elif key in (curses.KEY_DOWN, ord("j")):
            sel = (sel + 1) % len(options)
        elif ord("1") <= key < ord("1") + len(options):
            sel = key - ord("1")
            break
        elif key in (10, 13, curses.KEY_ENTER):
            break
        elif key in (ord("q"), ord("Q"), 27):
            scr.timeout(100)
            return
    scr.timeout(100)

    target, target_name = options[sel]

    # MimiClaw uses local ~/mimiclaw-flash/ binaries, not the Bruce fetch
    # flow. Short-circuit to its self-contained flasher.
    if target == Firmware.MIMICLAW:
        from tui.mimiclaw import run_mimiclaw_flash
        run_mimiclaw_flash(scr)
        invalidate_cache()
        return

    if target == current:
        scr.addnstr(h - 2, 0,
                    f" Already running {target_name} — nothing to do. "[:w - 1],
                    w - 1, curses.color_pair(C_STATUS) | curses.A_BOLD)
        scr.refresh()
        scr.timeout(-1); scr.getch(); scr.timeout(100)
        return

    variant = None
    if target == Firmware.BRUCE:
        variants = list_watchdogs_variants()
        if not variants:
            try:
                scr.addnstr(h - 2, 0,
                            " No Bruce variants registered. "[:w - 1],
                            w - 1,
                            curses.color_pair(C_STATUS) | curses.A_BOLD)
            except curses.error:
                pass
            scr.refresh()
            scr.timeout(-1); scr.getch(); scr.timeout(100)
            return
        picked = _pick_watchdogs_variant(scr, variants, detect_board_variant())
        if picked is None:
            return
        variant, variant_disp = picked
        target_name = f"Bruce [{variant_disp}]"

    if not _confirm_flash(scr, target_name):
        return
    _run_threaded_flash(scr, target, variant, target_name)
    invalidate_cache()
    return


def _confirm_flash(scr, target_name):
    """Show a Y/N confirmation for a destructive flash operation."""
    h, w = scr.getmaxyx()
    scr.erase()
    msg = f" Flash {target_name}? (Y/N) "
    try:
        scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w - 1,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
    except curses.error:
        pass
    scr.refresh()
    scr.timeout(-1)
    key = scr.getch()
    scr.timeout(100)
    return key in (ord("y"), ord("Y"))


def _run_threaded_flash(scr, target, variant, target_name):
    """Run ``flash()`` on a worker thread and drive a curses progress UI.

    Handles download progress, esptool output surfacing, Q/ESC cancel
    during the fetch phase, and final result display.  Returns when
    the user acknowledges the result screen.
    """
    from tui.esp32_flash import FetchCancelled, FlashError, flash

    h, w = scr.getmaxyx()

    scr.erase()
    progress_state = {"done": 0, "total": None, "msg": "Starting..."}
    progress_lock = threading.Lock()
    cancel_event = threading.Event()
    result = {"error": None, "done": False}

    def on_fetch_progress(done, total):
        with progress_lock:
            progress_state["done"] = done
            progress_state["total"] = total
            progress_state["msg"] = "Downloading firmware"

    def on_output_cb(line):
        with progress_lock:
            progress_state["msg"] = line[:60]
        try:
            scr.addnstr(h - 2, 1, line[:w - 2], w - 2,
                        curses.color_pair(C_DIM))
            scr.refresh()
        except curses.error:
            pass

    def worker():
        try:
            flash(target, on_output=on_output_cb,
                  variant=variant, on_fetch_progress=on_fetch_progress,
                  cancel_event=cancel_event)
        except BaseException as exc:
            result["error"] = exc
        finally:
            result["done"] = True

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    scr.timeout(100)
    try:
        while not result["done"]:
            try:
                scr.addnstr(0, 0,
                            f" Flashing {target_name}... ".center(w - 1),
                            w - 1,
                            curses.color_pair(C_HEADER) | curses.A_BOLD)
                with progress_lock:
                    done = progress_state["done"]
                    total = progress_state["total"]
                    msg_line = progress_state["msg"]
                if total:
                    pct = int(done * 100 / total) if total else 0
                    bar = (f" {msg_line}: {done // 1024} / "
                           f"{total // 1024} KB ({pct}%) ")
                elif done:
                    bar = f" {msg_line}: {done // 1024} KB "
                else:
                    bar = f" {msg_line} "
                scr.addnstr(2, 0, bar[:w - 1].center(w - 1), w - 1,
                            curses.color_pair(C_DIM))
                scr.addnstr(h - 1, 0,
                            " Q/ESC to cancel (download only) "[:w - 1]
                            .center(w - 1), w - 1,
                            curses.color_pair(C_DIM))
                scr.refresh()
            except curses.error:
                pass
            key = scr.getch()
            if key in (ord("q"), ord("Q"), 27):
                cancel_event.set()
        t.join(timeout=5)
        err = result["error"]
        if isinstance(err, FetchCancelled):
            msg = " Download cancelled. "
        elif isinstance(err, FlashError):
            msg = f" Flash failed: {err} "
        elif err is not None:
            msg = f" Unexpected error: {err} "
        else:
            msg = f" Flash complete — {target_name} installed. Press any key. "
    finally:
        scr.timeout(100)

    try:
        scr.addnstr(h - 1, 0, msg[:w - 1], w - 1,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)
    except curses.error:
        pass
    scr.refresh()
    scr.timeout(-1)
    scr.getch()
    scr.timeout(100)


def run_esp32_install_watchdogs(scr):
    """One-tap Bruce install: detect chip → fetch → flash.

    If ``detect_board_variant`` is confident, we skip the variant
    picker and only ask for the single Y/N confirmation.  If detection
    fails, fall back to the manual picker so the user can choose
    explicitly.
    """
    from tui.esp32_detect import (
        Firmware, detect_board_variant, invalidate_cache, _read_chip_type,
        get_port, release_gpsd)
    from tui.esp32_flash import list_watchdogs_variants

    h, w = scr.getmaxyx()

    try:
        from tui.marauder import _inst as _mrd_inst
        if _mrd_inst and getattr(_mrd_inst, 'port', None):
            _mrd_inst.close()
    except Exception:
        pass

    scr.erase()
    splash = " Detecting ESP32 board... "
    try:
        scr.addnstr(h // 2, max(0, (w - len(splash)) // 2), splash, w - 1,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
    except curses.error:
        pass
    scr.refresh()

    port = get_port()
    if port:
        release_gpsd(port)
    chip = _read_chip_type(port) if port else None
    guessed = detect_board_variant(port)

    variants = list_watchdogs_variants(chip=chip) or list_watchdogs_variants()
    variants_map = {vid: disp for vid, disp in variants}

    if len(variants) == 1 and guessed is None:
        guessed = variants[0][0]

    if guessed and guessed in variants_map:
        variant = guessed
        variant_disp = variants_map[variant]
        chip_label = chip or "unknown chip"
        scr.erase()
        lines = [
            f" Detected: {chip_label} ",
            f" Board: {variant_disp} ",
            "",
            " Install Bruce firmware? ",
            " Y to confirm, M to pick manually, anything else to cancel ",
        ]
        for i, line in enumerate(lines):
            attr = curses.color_pair(
                C_HEADER if i in (1, 3) else C_DIM)
            if i in (1, 3):
                attr |= curses.A_BOLD
            try:
                scr.addnstr(h // 2 - 2 + i,
                            max(0, (w - len(line)) // 2),
                            line, w - 1, attr)
            except curses.error:
                pass
        scr.refresh()
        scr.timeout(-1)
        key = scr.getch()
        scr.timeout(100)
        if key in (ord("m"), ord("M")):
            variant = None
        elif key not in (ord("y"), ord("Y")):
            return

    else:
        variant = None

    if variant is None:
        if not variants:
            scr.erase()
            msg = " No Bruce variants registered. "
            try:
                scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w - 1,
                            curses.color_pair(C_STATUS) | curses.A_BOLD)
            except curses.error:
                pass
            scr.refresh()
            scr.timeout(-1); scr.getch(); scr.timeout(100)
            return
        picked = _pick_watchdogs_variant(scr, variants, guessed)
        if picked is None:
            return
        variant, variant_disp = picked
        if not _confirm_flash(scr, f"Bruce [{variant_disp}]"):
            return

    _run_threaded_flash(scr, Firmware.BRUCE, variant,
                        f"Bruce [{variant_disp}]")
    invalidate_cache()


def _pick_watchdogs_variant(scr, variants, guessed):
    """Interactive variant picker.  Returns (vid, display) or None."""
    h, w = scr.getmaxyx()
    vsel = 0
    if guessed:
        for i, (vid, _disp) in enumerate(variants):
            if vid == guessed:
                vsel = i
                break
    scr.timeout(-1)
    try:
        while True:
            scr.erase()
            title = " Which board? "
            try:
                scr.addnstr(1, max(0, (w - len(title)) // 2), title, w - 1,
                            curses.color_pair(C_HEADER) | curses.A_BOLD)
            except curses.error:
                pass
            for i, (vid, disp) in enumerate(variants):
                marker = ">" if i == vsel else " "
                tag = "  (detected)" if guessed == vid else ""
                line = f" {marker} {i+1}. {disp}{tag} "
                attr = curses.A_BOLD | curses.color_pair(
                    C_HEADER if i == vsel else C_DIM)
                try:
                    scr.addnstr(3 + i, max(0, (w - len(line)) // 2),
                                line, w - 1, attr)
                except curses.error:
                    pass
            hint = " up/down select  Enter confirm  Q cancel "
            try:
                scr.addnstr(h - 1, 0, hint[:w - 1].center(w - 1), w - 1,
                            curses.color_pair(C_DIM))
            except curses.error:
                pass
            scr.refresh()
            key = scr.getch()
            if key in (curses.KEY_UP, ord("k")):
                vsel = (vsel - 1) % len(variants)
            elif key in (curses.KEY_DOWN, ord("j")):
                vsel = (vsel + 1) % len(variants)
            elif ord("1") <= key <= ord("9") and (key - ord("1")) < len(variants):
                vsel = key - ord("1")
                return variants[vsel]
            elif key in (10, 13, curses.KEY_ENTER):
                return variants[vsel]
            elif key in (ord("q"), ord("Q"), 27):
                return None
    finally:
        scr.timeout(100)


def _run_esp32_force(scr, firmware):
    """Force-set detection to a specific firmware and re-enter hub."""
    from tui.esp32_detect import _cache
    _cache["firmware"] = firmware
    _cache["port"] = "/dev/esp32"
    _cache["timestamp"] = time.time()
    run_esp32_hub(scr)


def run_esp32_force_mp(scr):
    from tui.esp32_detect import Firmware
    _run_esp32_force(scr, Firmware.MICROPYTHON)


def run_esp32_force_mrd(scr):
    from tui.esp32_detect import Firmware
    _run_esp32_force(scr, Firmware.MARAUDER)


def run_esp32_force_mc(scr):
    from tui.esp32_detect import Firmware
    _run_esp32_force(scr, Firmware.MIMICLAW)


def run_esp32_usb_reset(scr):
    """USB-reset the ESP32 to recover from a hung state."""
    from tui.esp32_detect import invalidate_cache

    h, w = scr.getmaxyx()
    scr.erase()
    msg = " Resetting ESP32 via USB... "
    scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w,
                curses.color_pair(C_HEADER) | curses.A_BOLD)
    scr.refresh()

    try:
        from tui.marauder import _inst as _mrd_inst
        if _mrd_inst and getattr(_mrd_inst, 'port', None):
            _mrd_inst.close()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["usbreset", "CP2102 USB to UART Bridge Controller"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            time.sleep(2)
            invalidate_cache()
            msg = " ESP32 reset OK "
        else:
            msg = f" Reset failed: {result.stderr.strip()[:40]} "
    except FileNotFoundError:
        msg = " usbreset not installed "
    except subprocess.TimeoutExpired:
        msg = " Reset timed out "

    scr.addnstr(h // 2 + 1, max(0, (w - len(msg)) // 2), msg, w,
                curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    scr.timeout(-1)
    scr.getch()
    scr.timeout(100)


def run_esp32_redetect(scr):
    """Invalidate cache and re-enter ESP32 hub."""
    from tui.esp32_detect import invalidate_cache
    invalidate_cache()
    run_esp32_hub(scr)


def run_esp32_fw_cache_clear(scr):
    """Delete every cached Bruce firmware .bin in ~/watchdogs-fw/."""
    from tui.esp32_flash import clear_watchdogs_cache

    h, w = scr.getmaxyx()
    scr.erase()
    title = " Clear Bruce firmware cache? (Y/N) "
    try:
        scr.addnstr(h // 2, max(0, (w - len(title)) // 2), title, w - 1,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
    except curses.error:
        pass
    scr.refresh()
    scr.timeout(-1)
    key = scr.getch()
    scr.timeout(100)
    if key not in (ord("y"), ord("Y")):
        return

    removed = clear_watchdogs_cache()
    msg = (f" Removed {len(removed)} file(s) "
           if removed else " Cache already empty ")
    try:
        scr.addnstr(h // 2 + 2, max(0, (w - len(msg)) // 2), msg, w - 1,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)
    except curses.error:
        pass
    scr.refresh()
    scr.timeout(-1)
    scr.getch()
    scr.timeout(100)


def run_esp32_backup(scr):
    """Dump current ESP32 flash to a timestamped .bin."""
    from tui.esp32_flash import FlashError, backup_flash

    try:
        from tui.marauder import _inst as _mrd_inst
        if _mrd_inst and getattr(_mrd_inst, 'port', None):
            _mrd_inst.close()
    except Exception:
        pass

    h, w = scr.getmaxyx()
    scr.erase()
    scr.addnstr(0, 0, " Backing up ESP32 flash... ".center(w), w,
                curses.color_pair(C_HEADER) | curses.A_BOLD)
    scr.refresh()

    lines = []

    def on_output(line):
        lines.append(line)
        y = min(len(lines) + 1, h - 2)
        try:
            scr.addnstr(y, 1, line[:w - 2], w - 2, curses.color_pair(C_DIM))
            scr.refresh()
        except curses.error:
            pass

    try:
        dest = backup_flash(on_output=on_output)
        msg = f" Backup saved: {dest} "
    except FlashError as e:
        msg = f" Backup failed: {e} "

    try:
        scr.addnstr(h - 1, 0, msg[:w - 1], w - 1,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)
    except curses.error:
        pass
    scr.refresh()
    scr.timeout(-1)
    scr.getch()
    scr.timeout(100)


HANDLERS = {
    "_esp32_hub":               run_esp32_hub,
    "_esp32_flash":             run_esp32_flash_picker,
    "_esp32_usb_reset":         run_esp32_usb_reset,
    "_esp32_redetect":          run_esp32_redetect,
    "_esp32_backup":            run_esp32_backup,
    "_esp32_fw_cache_clear":    run_esp32_fw_cache_clear,
    "_esp32_install_watchdogs": run_esp32_install_watchdogs,
    "_esp32_force_mp":          run_esp32_force_mp,
    "_esp32_force_mrd":         run_esp32_force_mrd,
    "_esp32_force_mc":          run_esp32_force_mc,
}
