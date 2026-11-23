from collections import defaultdict

import numpy as np


def windows(sheet, interval):
    records = defaultdict(dict)
    for row in sheet.iter_rows(min_row=2, values_only=True):
        key = (*row[:4], row[6], row[7])
        records[key].setdefault(row[5], {})[row[8]] = row[9]
    grouped = defaultdict(list)
    for key, slices in records.items():
        grouped[key[:4]].append((key[4], key[5], slices))
    for block, intervals in grouped.items():
        merged = []
        for start, end, slices in sorted(intervals):
            if merged and start <= merged[-1][1] + interval * 1.1:
                previous_start, previous_end, previous = merged.pop()
                for drift, points in slices.items():
                    previous.setdefault(drift, {}).update(points)
                merged.append((previous_start, max(end, previous_end), previous))
            else:
                merged.append((start, end, slices))
        for start, end, slices in merged:
            yield block, slices


def channels(slices):
    drift = sorted(slices, key=lambda value: -1 if value is None else value)
    times = np.array(sorted({time for points in slices.values() for time in points}))
    responses = np.array([[slices[position].get(time, 0.0) for time in times] for position in drift])
    side = min(12, len(times) // 5)
    edge = np.r_[np.arange(side), np.arange(len(times) - side, len(times))]
    design = np.column_stack([np.ones(len(times)), times - times.mean()])
    baseline = design @ np.linalg.lstsq(design[edge], responses[:, edge].T, rcond=None)[0]
    signal = responses - baseline.T
    total = signal.sum(axis=0)
    smooth = np.convolve(total, np.ones(3) / 3, mode='same')
    candidates = np.flatnonzero((smooth[1:-1] > smooth[:-2]) & (smooth[1:-1] >= smooth[2:])) + 1
    noise = np.std(total[edge])
    candidates = [int(index) for index in candidates if smooth[index] > max(smooth.max() * .00001, noise * 10)]
    peaks = []
    for index in sorted(candidates, key=lambda index: -smooth[index]):
        if all(abs(times[index] - times[other]) > 1 for other in peaks):
            peaks.append(index)
    peaks.sort()
    for position, index in enumerate(peaks):
        left = index
        right = index
        while left > 0 and smooth[left] > smooth[index] / 2:
            left -= 1
        while right < len(times) - 1 and smooth[right] > smooth[index] / 2:
            right += 1
        radius = max(8, int(np.ceil((right - left) * 2.6)))
        lower = max(0, index - radius, (peaks[position - 1] + index) // 2 + 1 if position else 0)
        upper = min(len(times), index + radius + 1,
                    (index + peaks[position + 1]) // 2 + 1 if position + 1 < len(peaks) else len(times))
        weights = total[lower:upper]
        center = np.dot(times[lower:upper], weights) / weights.sum()
        areas = signal[:, lower:upper].sum(axis=1)
        yield center, [(position, area) for position, area in zip(drift, areas)
                       if times[index] in slices[position]]


def match_references(observed, targets):
    flight = np.asarray(sorted(observed))
    masses = np.asarray(sorted(targets))
    root = np.sqrt(masses)
    solutions = {}
    for first in range(len(flight) - len(masses) + 1):
        for last in range(first + len(masses) - 1, len(flight)):
            coefficient = (flight[last] - flight[first]) / (root[-1] - root[0])
            offset = flight[first] - coefficient * root[0]
            predicted = ((flight - offset) / coefficient) ** 2
            distances = abs(predicted[:, None] - masses[None, :]) / masses[None, :]
            indices = np.argmin(distances, axis=0)
            if len(set(indices)) != len(masses) or np.max(distances[indices, np.arange(len(masses))]) > 4e-6:
                continue
            coefficient, offset = np.linalg.lstsq(
                np.column_stack([root, np.ones(len(root))]), flight[indices], rcond=None)[0]
            residual = abs(((flight[indices] - offset) / coefficient) ** 2 / masses - 1)
            if coefficient > 0 and residual.max() <= 1e-6:
                solutions[tuple(indices)] = (coefficient, offset)
    if len(solutions) != 1:
        raise ValueError(f'external calibration has {len(solutions)} complete reference-series matches')
    return next(iter(solutions.values()))


class FlightTimeReader:
    def __init__(self, workbook):
        settings = {row[0]: row[1] for row in workbook['Run settings'].values}
        self.interval = settings['TOF digitizer interval (ns)']
        observed = sorted(center for block, slices in windows(workbook['TOF calibration'], self.interval)
                          for center, areas in channels(slices))
        targets = sorted(row[2] for row in workbook['TOF references'].iter_rows(min_row=2, values_only=True))
        self.coefficient, self.offset = match_references(observed, targets)
        if self.coefficient <= 0:
            raise ValueError('flight-time calibration has a nonpositive slope')

    def mass(self, flight):
        return ((flight - self.offset) / self.coefficient) ** 2

    def records(self, sheet):
        for block, slices in windows(sheet, self.interval):
            for flight, areas in channels(slices):
                for drift, area in areas:
                    yield block, self.mass(flight), drift, float(area)
