#!/usr/bin/env python3
"""Trackball scroll daemon: hold Select to convert trackball movement to scroll."""

import os
import sys
import signal
import struct
import select
import uinput

# Input event format: struct input_event (time_sec, time_usec, type, code, value)
EVENT_FMT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FMT)

# Event types
EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02

# Key codes
KEY_SELECT = 353

# REL codes
REL_X = 0x00
REL_Y = 0x01
REL_WHEEL = 0x08
REL_HWHEEL = 0x06

# Scroll sensitivity: accumulate this many REL units before emitting one scroll tick
SCROLL_DIVISOR = 3

# Find input devices by name
def find_device(name_substring):
    for i in range(20):
        path = f"/dev/input/event{i}"
        if not os.path.exists(path):
            continue
        try:
            with open(f"/sys/class/input/event{i}/device/name") as f:
                if name_substring in f.read():
                    return path
        except (IOError, PermissionError):
            continue
    return None


def wait_for_devices():
    """Wait for both input devices to appear, polling every 5 seconds."""
    import time
    while True:
        consumer = find_device("Consumer Control")
        mouse = find_device("uConsole Mouse")
        if consumer and mouse:
            return consumer, mouse
        print(f"Waiting for devices: consumer={consumer} mouse={mouse}",
              file=sys.stderr)
        time.sleep(5)


def main():
    consumer, mouse = wait_for_devices()

    # Virtual scroll device
    vscroll = uinput.Device([
        uinput.REL_WHEEL,
        uinput.REL_HWHEEL,
    ], name="uconsole-scroll")

    fd_key = os.open(consumer, os.O_RDONLY | os.O_NONBLOCK)
    fd_mouse = os.open(mouse, os.O_RDONLY | os.O_NONBLOCK)

    # Grab the mouse so real pointer doesn't move while scrolling
    # We'll grab/ungrab dynamically based on Select state
    EVIOCGRAB = 0x40044590

    select_held = False
    accum_x = 0
    accum_y = 0

    def cleanup(*_):
        if select_held:
            try:
                import fcntl
                fcntl.ioctl(fd_mouse, EVIOCGRAB, 0)
            except:
                pass
        os.close(fd_key)
        os.close(fd_mouse)
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    print(f"Trackball scroll active: {consumer} + {mouse}", file=sys.stderr)

    import fcntl

    while True:
        readable, _, _ = select.select([fd_key, fd_mouse], [], [], 1.0)

        for fd in readable:
            try:
                data = os.read(fd, EVENT_SIZE * 64)
            except BlockingIOError:
                continue

            for offset in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
                _, _, ev_type, ev_code, ev_value = struct.unpack(
                    EVENT_FMT, data[offset:offset + EVENT_SIZE]
                )

                # Track Select key
                if fd == fd_key and ev_type == EV_KEY and ev_code == KEY_SELECT:
                    if ev_value == 1:  # press
                        select_held = True
                        accum_x = 0
                        accum_y = 0
                        try:
                            fcntl.ioctl(fd_mouse, EVIOCGRAB, 1)
                        except:
                            pass
                    elif ev_value == 0:  # release
                        select_held = False
                        try:
                            fcntl.ioctl(fd_mouse, EVIOCGRAB, 0)
                        except:
                            pass

                # Convert mouse movement to scroll when Select held
                if fd == fd_mouse and ev_type == EV_REL and select_held:
                    if ev_code == REL_Y:
                        accum_y += ev_value
                        ticks = accum_y // SCROLL_DIVISOR
                        if ticks:
                            vscroll.emit(uinput.REL_WHEEL, -ticks)
                            accum_y -= ticks * SCROLL_DIVISOR
                    elif ev_code == REL_X:
                        accum_x += ev_value
                        ticks = accum_x // SCROLL_DIVISOR
                        if ticks:
                            vscroll.emit(uinput.REL_HWHEEL, ticks)
                            accum_x -= ticks * SCROLL_DIVISOR


if __name__ == "__main__":
    main()
