from collections import deque

import numpy as np


def innovation_noise(history, separations):
    observed = np.isfinite(history) & (np.abs(history) <= 10)
    values = np.where(observed, history, 0.0)
    counts = observed.sum(axis=0)
    denominator = np.maximum(counts, 1)
    variance = np.maximum((values * values).sum(axis=0) / denominator, 0.16)
    best_scale = np.sqrt(variance)
    best_cost = denominator * np.log(variance) + (values * values).sum(axis=0) / variance
    for radius in (1, 2, 3):
        positions = np.arange(-radius, radius + 1, dtype=float)
        spacing = separations.copy()
        scale = np.full(len(spacing), 0.6)
        weights = np.full((len(spacing), len(positions)), 0.4 / (2 * radius))
        weights[:, radius] = 0.6
        for iteration in range(12):
            residual = values[:, :, None] - spacing[None, :, None] * positions
            density = np.exp(-0.5 * (residual / scale[None, :, None]) ** 2)
            density *= weights[None, :, :]
            responsibilities = density / np.maximum(density.sum(axis=2, keepdims=True), 1e-100)
            responsibilities *= observed[:, :, None]
            mass = responsibilities.sum(axis=0)
            weights = (mass + mass[:, ::-1] + 0.02) / (2 * denominator[:, None] + 0.02 * len(positions))
            numerator = (responsibilities * values[:, :, None] * positions).sum(axis=(0, 2))
            divisor = (responsibilities * positions ** 2).sum(axis=(0, 2))
            spacing = np.clip(numerator / np.maximum(divisor, 1e-10),
                              separations * 0.75, separations * 1.25)
            residual = values[:, :, None] - spacing[None, :, None] * positions
            scale = np.sqrt(np.maximum((responsibilities * residual ** 2).sum(axis=(0, 2)) / denominator, 0.16))
        residual = values[:, :, None] - spacing[None, :, None] * positions
        density = np.exp(-0.5 * (residual / scale[None, :, None]) ** 2)
        likelihood = (density * weights[None, :, :]).sum(axis=2) / scale
        cost = -2 * (np.log(np.maximum(likelihood, 1e-100)) * observed).sum(axis=0)
        cost += (radius + 1) * np.log(np.maximum(counts, 2))
        improved = cost + 10 < best_cost
        best_scale = np.where(improved, scale, best_scale)
        best_cost = np.where(improved, cost, best_cost)
    return np.where(counts >= 16, best_scale, np.inf)


def level_noise(history, separations):
    observed = np.isfinite(history)
    counts = observed.sum(axis=0)
    denominator = np.maximum(counts, 1)
    values = np.where(observed, history, 0.0)
    average = values.sum(axis=0) / denominator
    residual = np.where(observed, values - average, 0.0)
    variance = np.maximum((residual * residual).sum(axis=0) / denominator, 0.16)
    best_scale = np.sqrt(variance)
    best_cost = denominator * np.log(variance) + (residual * residual).sum(axis=0) / variance
    selected = np.zeros(len(separations), dtype=bool)
    for components in (2, 3, 4):
        centers = np.zeros((len(separations), components))
        for channel in range(len(separations)):
            sample = history[observed[:, channel], channel]
            if len(sample):
                lower, upper = np.quantile(sample, [0.05, 0.95])
                centers[channel] = np.linspace(lower, upper, components)
        scale = np.full(len(separations), 0.6)
        weights = np.full(centers.shape, 1 / components)
        for iteration in range(20):
            residual = values[:, :, None] - centers[None, :, :]
            density = np.exp(-0.5 * (residual / scale[None, :, None]) ** 2)
            density *= weights[None, :, :]
            responsibilities = density / np.maximum(density.sum(axis=2, keepdims=True), 1e-100)
            responsibilities *= observed[:, :, None]
            mass = responsibilities.sum(axis=0)
            weights = (mass + 0.01) / (denominator[:, None] + 0.01 * components)
            centers = (responsibilities * values[:, :, None]).sum(axis=0) / np.maximum(mass, 1e-10)
            residual = values[:, :, None] - centers[None, :, :]
            scale = np.sqrt(np.maximum((responsibilities * residual ** 2).sum(axis=(0, 2)) / denominator, 0.16))
        residual = values[:, :, None] - centers[None, :, :]
        density = np.exp(-0.5 * (residual / scale[None, :, None]) ** 2)
        likelihood = (density * weights[None, :, :]).sum(axis=2) / scale
        cost = -2 * (np.log(np.maximum(likelihood, 1e-100)) * observed).sum(axis=0)
        cost += (2 * components - 1) * np.log(np.maximum(counts, 2))
        separated = (np.diff(np.sort(centers, axis=1), axis=1) >= separations[:, None] * 0.65).all(axis=1)
        supported = (weights >= 0.08).all(axis=1)
        improved = (cost + 10 < best_cost) & separated & supported
        selected |= improved
        best_scale = np.where(improved, scale, best_scale)
        best_cost = np.where(improved, cost, best_cost)
    return np.where((counts >= 16) & selected, best_scale, np.inf)


class Features:
    def __init__(self, addresses, separations, warmup_seconds=240, signs=None):
        self.addresses = addresses
        self.indices = {address: index for index, address in enumerate(addresses)}
        self.separations = np.asarray(separations)
        self.signs = np.asarray(signs if signs is not None else [1] * len(addresses))
        self.timestamps = {}
        self.last_values = {}
        self.history = deque(maxlen=48)
        self.recent = deque(maxlen=2)
        self.scans = 0
        self.noise = np.full(len(addresses), np.inf)
        self.estimates = deque(maxlen=3)
        self.origin = None
        self.warmup_seconds = warmup_seconds
        self.calibrated = False
        self.last_support = -np.inf
        self.levels = deque(maxlen=32)
        self.calibration_levels = deque(maxlen=48)
        self.previous_levels = np.zeros(len(addresses), dtype=bool)
        self.suppressed_until = np.zeros(len(addresses)) - np.inf

    def update(self, row):
        if self.origin is None:
            self.origin = row["t"]
        differences = np.full(len(self.addresses), np.nan)
        levels = np.full(len(self.addresses), np.nan)
        for entry in row["bss"]:
            address = entry["bssid"]
            index = self.indices.get(address)
            if index is None or self.timestamps.get(address) == entry["host_timestamp"]:
                continue
            self.timestamps[address] = entry["host_timestamp"]
            value = entry["rssi_dbm"]
            levels[index] = value * self.signs[index]
            if address in self.last_values:
                differences[index] = value - self.last_values[address]
            self.last_values[address] = value
        if np.isfinite(differences).sum() < 6:
            return None
        self.scans += 1
        self.history.append(differences)
        self.calibration_levels.append(levels.copy())
        stepped = np.abs(differences) >= 5
        self.suppressed_until[stepped] = row["t"] + 90
        for previous in self.levels:
            previous[stepped] = np.nan
        self.levels.append(levels)
        finished = row["t"] >= self.origin + self.warmup_seconds
        if not self.calibrated and self.scans >= 18 and (self.scans % 6 == 0 or finished):
            innovation = innovation_noise(np.asarray(self.history), self.separations)
            levels_noise = level_noise(np.asarray(self.calibration_levels), self.separations) * np.sqrt(2)
            levels_noise = np.where(levels_noise <= 0.75, levels_noise, np.inf)
            self.estimates.append(np.minimum(innovation, levels_noise))
            self.noise = np.median(np.asarray(self.estimates), axis=0)
            self.calibrated = finished and self.scans >= 24
        magnitude = np.abs(differences)
        evidence = (self.noise <= 0.85) & (magnitude >= 2) & (magnitude <= 5)
        history = np.asarray(self.levels)
        usable = np.isfinite(history).sum(axis=0) >= 8
        background = np.full(len(self.addresses), np.nan)
        if usable.any():
            background[usable] = np.nanquantile(history[:, usable], 0.2, axis=0)
        displacement = levels - background
        elevated = ((self.noise <= 0.75) & (displacement >= 1.5) & (displacement <= 4.5)
                    & (row["t"] >= self.suppressed_until))
        sustained = int(np.count_nonzero(elevated & (self.previous_levels
                                                    | (differences * self.signs >= 1.5))))
        self.previous_levels = elevated
        if np.count_nonzero(evidence) >= 2 or sustained:
            self.last_support = row["t"]
        self.recent.append(evidence)
        total = np.sum(self.recent, axis=0)
        return int(total.sum()), int(np.count_nonzero(total)), sustained, self.last_support


class Presence:
    def __init__(self, settings):
        self.settings = settings
        self.origin = None
        self.present = False
        self.last_evidence = -np.inf
        self.last_observation = None
        self.paused = False

    def update(self, when, evidence):
        if self.origin is None:
            self.origin = when
        if evidence is None:
            if (self.present and self.last_observation is not None
                    and when - self.last_observation > self.settings["hold_seconds"]):
                self.paused = True
        else:
            if self.present and self.paused:
                self.last_evidence = when
            self.paused = False
            self.last_observation = when
            hits, channels, sustained, supported_at = evidence
            confirm = sustained >= 2 or (hits >= self.settings["entry_hits"]
                                        and channels >= self.settings["entry_channels"])
            maintain = self.present and (sustained or (hits >= self.settings["hold_hits"]
                                                     and channels >= self.settings["hold_channels"]))
            if confirm or maintain:
                self.present = True
                self.last_evidence = max(self.last_evidence, supported_at)
            if when - self.last_evidence > self.settings["hold_seconds"]:
                self.present = False
        if when < self.origin + self.settings["warmup_seconds"]:
            return "warming_up"
        return "present" if self.present else "absent"
