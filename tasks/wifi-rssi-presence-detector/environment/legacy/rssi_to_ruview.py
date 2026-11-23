"""RSSI to RuView injector v3: per-channel adaptive normalization."""

import argparse
import math
import socket
import struct
import time

import numpy as np

from wlan_native import NativeWlan


SLOTS = 63
DEADBAND = 2.0
NOISE_GATE = 2.5
MEAN_ALPHA = 0.01
NOISE_ALPHA = 0.02
MIN_SIGMA = 0.5
FORCE_SCAN_SECONDS = 6.0
POLL_SECONDS = 0.2


class Channel:
    def __init__(self, level):
        self.mean = level
        self.variance = 1.0
        self.last = level

    def update(self, level):
        delta = level - self.mean
        sigma = max(MIN_SIGMA, math.sqrt(self.variance))
        normalized = delta / sigma
        if abs(normalized) < NOISE_GATE:
            self.mean += MEAN_ALPHA * delta
            self.variance = (1 - NOISE_ALPHA) * self.variance + NOISE_ALPHA * delta * delta
        self.last = level
        return math.copysign(max(0.0, abs(normalized) - DEADBAND), normalized)


class Injector:
    def __init__(self, host, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.destination = (host, port)
        self.channels = {}
        self.slots = {}
        self.sequence = 0

    def frame(self, readings):
        amplitudes = np.ones(SLOTS, dtype=np.float32)
        for address, level in readings.items():
            if address not in self.slots:
                if len(self.slots) >= SLOTS:
                    continue
                self.slots[address] = len(self.slots)
                self.channels[address] = Channel(level)
            normalized = self.channels[address].update(level)
            amplitudes[self.slots[address]] = 1.0 + 0.1 * normalized
        # Access points doing power control cause the large RSSI swings.
        header = struct.pack("<4sIHH", b"CSI\0", self.sequence, 1, SLOTS)
        self.sequence += 1
        return header + amplitudes.tobytes()

    def send(self, readings):
        self.socket.sendto(self.frame(readings), self.destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5005)
    args = parser.parse_args()
    injector = Injector(args.host, args.port)
    with NativeWlan() as reader:
        last_scan = -math.inf
        while True:
            started = time.monotonic()
            if started - last_scan >= FORCE_SCAN_SECONDS:
                reader.force_scan()
                last_scan = started
            injector.send(reader.read_bss())
            time.sleep(max(0.0, POLL_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
