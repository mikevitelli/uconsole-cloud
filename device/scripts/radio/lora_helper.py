#!/usr/bin/env python3
"""LoRa SX1262 helper — called by lora.sh for SPI hardware interaction.

Usage:
    lora_helper.py send <msg> <freq> <bw> <sf> <power>
    lora_helper.py listen <freq> <bw> <sf>
    lora_helper.py ping <freq> <bw> <sf> <power>
    lora_helper.py chat <freq> <bw> <sf> <power>
    lora_helper.py bridge <freq> <bw> <sf> <api_url>
"""
import subprocess
import sys
import time
import json
import spidev
import struct

SPI_BUS = 1
SPI_CS = 0
SPI_SPEED = 2_000_000

# SX1262 GPIO pins (active-low reset, active-high busy)
GPIO_RESET = 25
GPIO_BUSY = 24
GPIO_IRQ = 26


def _gpioset(pin, value):
    try:
        subprocess.run(
            ["gpioset", "-m", "exit", "gpiochip0", f"{pin}={value}"],
            check=True, capture_output=True,
        )
    except FileNotFoundError:
        pass  # gpiod not installed — skip hardware reset


def _gpioget(pin):
    try:
        r = subprocess.run(
            ["gpioget", "gpiochip0", str(pin)], capture_output=True, text=True
        )
        return int(r.stdout.strip())
    except (FileNotFoundError, ValueError):
        return 0  # assume ready if gpiod not available

# SX1262 commands
CMD_SET_STANDBY = 0x80
CMD_SET_RF_FREQUENCY = 0x86
CMD_SET_TX = 0x83
CMD_SET_RX = 0x82
CMD_WRITE_BUFFER = 0x0E
CMD_READ_BUFFER = 0x1E
CMD_GET_RX_BUFFER_STATUS = 0x13
CMD_GET_PACKET_STATUS = 0x14
CMD_SET_PACKET_TYPE = 0x8A
CMD_SET_MODULATION_PARAMS = 0x8B
CMD_SET_PACKET_PARAMS = 0x8C
CMD_SET_BUFFER_BASE_ADDRESS = 0x8F
CMD_GET_STATUS = 0xC0
CMD_SET_PA_CONFIG = 0x95
CMD_SET_TX_PARAMS = 0x8E
CMD_SET_DIO3_AS_TCXO_CTRL = 0x97
CMD_CALIBRATE = 0x89
CMD_SET_REGULATOR_MODE = 0x96
CMD_CALIBRATE_IMAGE = 0x98
CMD_SET_DIO2_AS_RF_SWITCH_CTRL = 0x9D


class SX1262:
    def __init__(self, freq_mhz=915.0, bw_khz=125, sf=7, power=22):
        self.spi = spidev.SpiDev()
        self.spi.open(SPI_BUS, SPI_CS)
        self.spi.max_speed_hz = SPI_SPEED
        self.spi.mode = 0
        self.freq_mhz = freq_mhz
        self.bw_khz = bw_khz
        self.sf = sf
        self.power = power

    def _cmd(self, opcode, data=None):
        payload = [opcode] + (data or [])
        return self.spi.xfer2(payload)

    def _wait_busy(self, timeout=1.0):
        """Wait for SX1262 BUSY pin to go low."""
        start = time.time()
        while time.time() - start < timeout:
            if _gpioget(GPIO_BUSY) == 0:
                return
            time.sleep(0.001)

    def _reset(self):
        """Hardware reset via NRST pin."""
        _gpioset(GPIO_RESET, 0)
        time.sleep(0.05)
        _gpioset(GPIO_RESET, 1)
        time.sleep(0.1)
        self._wait_busy()

    def init(self):
        """Initialize SX1262 for LoRa mode."""
        self._reset()
        self._cmd(CMD_SET_STANDBY, [0x00])  # STDBY_RC
        self._wait_busy()

        # AIO board's SX1262 module clocks off a TCXO powered through DIO3.
        # Without this, the synthesizer never locks and SetRx/SetTx silently
        # fail with command-error status. 1.8V, 5ms warmup (320 * 15.625us).
        self._cmd(CMD_SET_DIO3_AS_TCXO_CTRL, [0x02, 0x00, 0x01, 0x40])
        self._wait_busy()

        # Recalibrate all blocks against TCXO clock
        self._cmd(CMD_CALIBRATE, [0x7F])
        self._wait_busy()
        time.sleep(0.005)
        self._cmd(CMD_SET_STANDBY, [0x00])
        self._wait_busy()

        self._cmd(CMD_SET_REGULATOR_MODE, [0x01])  # DC-DC
        self._wait_busy()

        # Set packet type to LoRa
        self._cmd(CMD_SET_PACKET_TYPE, [0x01])
        self._wait_busy()

        # Set RF frequency
        freq_reg = int(self.freq_mhz * 1e6 * (2**25) / 32e6)
        self._cmd(CMD_SET_RF_FREQUENCY, [
            (freq_reg >> 24) & 0xFF,
            (freq_reg >> 16) & 0xFF,
            (freq_reg >> 8) & 0xFF,
            freq_reg & 0xFF,
        ])
        self._wait_busy()

        # Image-rejection calibration per AN1200.42
        img_cal = None
        if 902 <= self.freq_mhz <= 928:
            img_cal = [0xE1, 0xE9]
        elif 863 <= self.freq_mhz <= 870:
            img_cal = [0xD7, 0xDB]
        elif 779 <= self.freq_mhz <= 787:
            img_cal = [0xC1, 0xC5]
        elif 470 <= self.freq_mhz <= 510:
            img_cal = [0x75, 0x81]
        elif 430 <= self.freq_mhz <= 440:
            img_cal = [0x6B, 0x6F]
        if img_cal:
            self._cmd(CMD_CALIBRATE_IMAGE, img_cal)
            self._wait_busy()

        # AIO V1 wires the antenna T/R switch to DIO2 — without this the chip
        # has no path to/from the SMA.
        self._cmd(CMD_SET_DIO2_AS_RF_SWITCH_CTRL, [0x01])
        self._wait_busy()

        # PA config for SX1262 (up to +22 dBm)
        self._cmd(CMD_SET_PA_CONFIG, [0x04, 0x07, 0x00, 0x01])
        self._wait_busy()

        # TX params: power, ramp time
        power_val = max(-9, min(22, self.power))
        self._cmd(CMD_SET_TX_PARAMS, [power_val & 0xFF, 0x04])  # 200us ramp
        self._wait_busy()

        # Modulation params: SF, BW, CR, LowDataRateOptimize
        bw_map = {7: 0x00, 10: 0x08, 15: 0x01, 20: 0x09, 31: 0x02,
                  41: 0x0A, 62: 0x03, 125: 0x04, 250: 0x05, 500: 0x06}
        bw_val = bw_map.get(self.bw_khz, 0x04)
        ldro = 1 if (self.sf >= 11 and self.bw_khz <= 125) else 0
        self._cmd(CMD_SET_MODULATION_PARAMS, [self.sf, bw_val, 0x01, ldro])
        self._wait_busy()

        # Buffer base addresses
        self._cmd(CMD_SET_BUFFER_BASE_ADDRESS, [0x00, 0x80])
        self._wait_busy()

    def send(self, data: bytes):
        """Transmit data."""
        length = len(data)
        # Set packet params: preamble=8, header=explicit, payload_len, CRC=on, invert_iq=off
        self._cmd(CMD_SET_PACKET_PARAMS, [0x00, 0x08, 0x00, length, 0x01, 0x00])
        self._wait_busy()

        # Write to TX buffer
        self._cmd(CMD_WRITE_BUFFER, [0x00] + list(data))
        self._wait_busy()

        # Start TX (timeout=0 = no timeout)
        self._cmd(CMD_SET_TX, [0x00, 0x00, 0x00])

        # Wait for TX done (poll status)
        for _ in range(100):
            time.sleep(0.05)
            status = self._cmd(CMD_GET_STATUS, [0x00])
            chip_mode = (status[1] >> 4) & 0x07
            if chip_mode == 2:  # STDBY after TX
                return True
        return False

    def start_rx(self, timeout_ms=0):
        """Enter continuous RX mode."""
        # Set packet params for RX
        self._cmd(CMD_SET_PACKET_PARAMS, [0x00, 0x08, 0x00, 0xFF, 0x01, 0x00])
        self._wait_busy()

        # RX continuous (timeout=0xFFFFFF)
        if timeout_ms == 0:
            self._cmd(CMD_SET_RX, [0xFF, 0xFF, 0xFF])
        else:
            t = int(timeout_ms * 64)  # 15.625us per tick
            self._cmd(CMD_SET_RX, [(t >> 16) & 0xFF, (t >> 8) & 0xFF, t & 0xFF])
        self._wait_busy()

    def read_packet(self):
        """Check for and read received packet. Returns (data, rssi, snr) or None."""
        # Get RX buffer status
        resp = self._cmd(CMD_GET_RX_BUFFER_STATUS, [0x00, 0x00, 0x00])
        payload_len = resp[2]
        start_ptr = resp[3]

        if payload_len == 0 or payload_len == 0xFF:
            return None

        # Read buffer
        data = self._cmd(CMD_READ_BUFFER, [start_ptr, 0x00] + [0x00] * payload_len)
        payload = bytes(data[3:3 + payload_len])

        # Get packet status (RSSI, SNR)
        pkt = self._cmd(CMD_GET_PACKET_STATUS, [0x00, 0x00, 0x00, 0x00])
        rssi = -pkt[2] / 2
        snr = (pkt[3] if pkt[3] < 128 else pkt[3] - 256) / 4

        return payload, rssi, snr

    def close(self):
        self._cmd(CMD_SET_STANDBY, [0x00])
        self.spi.close()


def cmd_send(args):
    msg, freq, bw, sf, power = args[0], float(args[1]), int(args[2]), int(args[3]), int(args[4])
    radio = SX1262(freq, bw, sf, power)
    radio.init()
    ok = radio.send(msg.encode())
    radio.close()
    if ok:
        print(f"  Sent {len(msg)} bytes")
    else:
        print("  TX timeout — check antenna connection", file=sys.stderr)
        sys.exit(1)


def cmd_listen(args):
    freq, bw, sf = float(args[0]), int(args[1]), int(args[2])
    radio = SX1262(freq, bw, sf)
    radio.init()
    radio.start_rx()
    print("Listening...")
    try:
        while True:
            pkt = radio.read_packet()
            if pkt:
                data, rssi, snr = pkt
                ts = time.strftime('%H:%M:%S')
                try:
                    text = data.decode('utf-8', errors='replace')
                except:
                    text = data.hex()
                print(f"  [{ts}] RSSI:{rssi:.0f}dBm SNR:{snr:.1f}dB  {text}")
                # Re-enter RX
                radio.start_rx()
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        radio.close()


def cmd_ping(args):
    freq, bw, sf, power = float(args[0]), int(args[1]), int(args[2]), int(args[3])
    radio = SX1262(freq, bw, sf, power)
    radio.init()

    print("Sending PING...")
    t0 = time.time()
    radio.send(b"PING")

    radio.start_rx(timeout_ms=5000)
    deadline = time.time() + 5
    while time.time() < deadline:
        pkt = radio.read_packet()
        if pkt:
            data, rssi, snr = pkt
            rtt = (time.time() - t0) * 1000
            print(f"  PONG received: RTT={rtt:.0f}ms  RSSI={rssi:.0f}dBm  SNR={snr:.1f}dB")
            radio.close()
            return
        time.sleep(0.05)

    print("  No response (timeout 5s)")
    radio.close()


def cmd_chat(args):
    import select
    freq, bw, sf, power = float(args[0]), int(args[1]), int(args[2]), int(args[3])
    radio = SX1262(freq, bw, sf, power)
    radio.init()
    radio.start_rx()
    print("Type messages and press Enter. Ctrl-C to exit.\n")
    try:
        while True:
            # Check for incoming
            pkt = radio.read_packet()
            if pkt:
                data, rssi, snr = pkt
                ts = time.strftime('%H:%M:%S')
                text = data.decode('utf-8', errors='replace')
                print(f"\r  < [{ts}] {text}  (RSSI:{rssi:.0f} SNR:{snr:.1f})")
                radio.start_rx()

            # Check for user input (non-blocking)
            if select.select([sys.stdin], [], [], 0.1)[0]:
                line = sys.stdin.readline().strip()
                if line:
                    radio.send(line.encode())
                    print(f"  > {line}")
                    radio.start_rx()
    except KeyboardInterrupt:
        pass
    finally:
        radio.close()


def cmd_bridge(args):
    import urllib.request
    freq, bw, sf, api_url = float(args[0]), int(args[1]), int(args[2]), args[3]
    radio = SX1262(freq, bw, sf)
    radio.init()
    radio.start_rx()
    print("Bridging to webdash...")
    try:
        while True:
            pkt = radio.read_packet()
            if pkt:
                data, rssi, snr = pkt
                ts = time.strftime('%Y-%m-%d %H:%M:%S')
                text = data.decode('utf-8', errors='replace')
                payload = json.dumps({
                    'message': text, 'rssi': rssi, 'snr': snr,
                    'timestamp': ts, 'freq': freq,
                }).encode()
                try:
                    req = urllib.request.Request(api_url, data=payload,
                        headers={'Content-Type': 'application/json'})
                    urllib.request.urlopen(req, timeout=5)
                    print(f"  [{ts}] Forwarded: {text} (RSSI:{rssi:.0f})")
                except Exception as e:
                    print(f"  [{ts}] Forward failed: {e}", file=sys.stderr)
                radio.start_rx()
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        radio.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        'send': cmd_send,
        'listen': cmd_listen,
        'ping': cmd_ping,
        'chat': cmd_chat,
        'bridge': cmd_bridge,
    }

    if cmd not in commands:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

    commands[cmd](args)
