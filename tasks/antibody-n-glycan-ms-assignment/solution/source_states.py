from collections import Counter, defaultdict

import numpy as np


def isotope_groups(composition, limit=16):
    isotopes = {
        'C': ((0, .9893, 0), (1, .0107, 1.00335483507)),
        'H': ((0, .999885, 0), (1, .000115, 1.00627674589)),
        'N': ((0, .99636, 0), (1, .00364, .99703489445)),
        'O': ((0, .99757, 0), (1, .00038, 1.00421713693), (2, .00205, 2.00424499329)),
        'P': ((0, 1, 0),),
        'Cl': ((0, .7578, 0), (2, .2422, 1.99704992)),
    }
    probabilities = np.zeros(limit)
    moments = np.zeros(limit)
    probabilities[0] = 1
    for element, count in composition.items():
        for atom in range(count):
            next_probability = np.zeros(limit)
            next_moment = np.zeros(limit)
            for shift, abundance, difference in isotopes[element]:
                for index in range(limit - shift):
                    next_probability[index + shift] += abundance * probabilities[index]
                    next_moment[index + shift] += abundance * (moments[index] + difference * probabilities[index])
            probabilities, moments = next_probability, next_moment
    return probabilities, moments / np.maximum(probabilities, 1e-30)


class CoincidentFamilies:
    def __init__(self, composition, precursor):
        ionic = Counter(composition)
        ionic.update({'H': 2, 'P': 1, 'O': 4})
        self.monomer, self.mono_shifts = isotope_groups(ionic)
        self.aggregate, self.aggregate_shifts = isotope_groups({element: 2 * count for element, count in ionic.items()})
        self.precursor = precursor

    def decompose(self, spectrum):
        points = np.array(sorted(spectrum))
        selected = points[(points[:, 0] >= self.precursor - .003) & (points[:, 0] < self.precursor + 9)]
        design = np.zeros((len(selected), 2))
        for column, (probabilities, shifts, charge) in enumerate((
                (self.monomer, self.mono_shifts, 1), (self.aggregate, self.aggregate_shifts, 2))):
            for probability, shift in zip(probabilities, shifts):
                distances = abs(selected[:, 0] - self.precursor - shift / charge)
                nearest = int(np.argmin(distances))
                if distances[nearest] < .003:
                    design[nearest, column] += probability
        totals = np.linalg.lstsq(design, selected[:, 1], rcond=None)[0]
        if min(totals) < 0:
            raise ValueError('negative source-family contribution')
        error = np.linalg.norm(design @ totals - selected[:, 1]) / np.linalg.norm(selected[:, 1])
        if error > .08:
            raise ValueError('source envelope is inconsistent with the monomer/aggregate isotope model')
        return totals, error

    def chromatograms(self, observations):
        blocks = defaultdict(list)
        for row in observations:
            if row.kind == 'Mass-channel trace' and self.precursor - .003 <= row.coordinate < self.precursor + 9:
                blocks[row.injection, row.retention].append((row.coordinate, row.response))
        result = defaultdict(list)
        for (injection, retention), spectrum in blocks.items():
            totals, error = self.decompose(spectrum)
            result[injection].append((retention, *totals))
        return {injection: np.array(sorted(rows)) for injection, rows in result.items()}

    def packets(self, observations, injection):
        signal = defaultdict(lambda: np.zeros(2))
        half_mass = self.precursor + self.aggregate_shifts[1] / 2
        for row in observations:
            if row.injection == injection and row.kind == 'Mobility extraction':
                if abs(row.coordinate - self.precursor) < .003:
                    signal[row.drift][0] += row.response
                elif abs(row.coordinate - half_mass) < .003:
                    signal[row.drift][1] += row.response
        drift = np.array(sorted(signal))
        gaps = np.diff(drift)
        split = np.flatnonzero(gaps > 3 * np.median(gaps)) + 1
        bands = np.split(drift, split)
        if len(bands) != 2:
            raise ValueError('isotope-resolved arrivals do not separate two packet bands')
        ratios = [sum(signal[position][1] for position in band) /
                  sum(signal[position][0] for position in band) for band in bands]
        aggregate_index = int(np.argmax(ratios))
        if ratios[aggregate_index] < .5 or ratios[1 - aggregate_index] > .05:
            raise ValueError('interstitial isotopes do not identify one aggregate packet')
        return set(bands[1 - aggregate_index]), set(bands[aggregate_index])
