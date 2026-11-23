import numpy as np


def interval_matrix(knots, supports):
    identity = np.eye(len(knots))
    rows = []
    for start, end in supports:
        times = np.unique(np.r_[start, knots[(knots > start) & (knots < end)], end])
        values = np.array([np.interp(times, knots, column) for column in identity])
        rows.append(np.trapezoid(values, times, axis=1) / (end - start))
    return np.array(rows)


def positive_least_squares(design, target):
    enabled = np.ones(design.shape[1], dtype=bool)
    result = np.zeros(design.shape[1])
    for iteration in range(design.shape[1]):
        result[:] = 0
        result[enabled] = np.linalg.lstsq(design[:, enabled], target, rcond=None)[0]
        if result.min() >= 0:
            return result
        enabled[result < 0] = False
    return np.maximum(result, 0)


def nonnegative_fit(design, values):
    coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
    if coefficients.min() >= 0:
        return coefficients
    alternatives = [np.zeros(2)]
    for column in range(2):
        candidate = np.zeros(2)
        candidate[column] = max(0, np.dot(design[:, column], values) / np.dot(design[:, column], design[:, column]))
        alternatives.append(candidate)
    return min(alternatives, key=lambda candidate: np.linalg.norm(design @ candidate - values))


class ComponentProfiles:
    def __init__(self, drift, times, channels):
        self.drift = drift
        self.times = times
        signals = np.array([np.maximum(values, 0).ravel() for values in channels])
        normalized = signals / signals.sum(axis=1, keepdims=True)
        unit = normalized / np.linalg.norm(normalized, axis=1, keepdims=True)
        first, second = np.unravel_index(np.argmin(unit @ unit.T), (len(unit), len(unit)))
        endpoints = normalized[[first, second]].T
        mixtures = np.array([nonnegative_fit(endpoints, vector) for vector in normalized])
        fingerprints = []
        for component in range(2):
            independent = mixtures[:, component] > 8 * mixtures[:, 1 - component]
            if not independent.any():
                raise ValueError('independent component fingerprints are missing')
            fingerprints.append(normalized[independent].mean(axis=0))
        self.basis = np.array(fingerprints).T
        self.arrivals = self.basis.reshape(len(times), len(drift), 2).sum(axis=0)
        self.arrivals /= self.arrivals.sum(axis=0)
        self.chromatograms = self.basis.reshape(len(times), len(drift), 2).sum(axis=1)
        self.apices = times[np.argmax(self.chromatograms, axis=0)]

    def bind_source(self, times, profiles, supports):
        observed = np.array([nonnegative_fit(self.arrivals, row) for row in profiles])
        self.apices = times[np.argmax(observed, axis=0)]
        self.knots = np.unique(np.r_[times, np.asarray(supports).ravel()])
        sampling = np.array([np.interp(times, self.knots, column)
                             for column in np.eye(len(self.knots))]).T
        accumulation = interval_matrix(self.knots, supports)
        curvature = np.diff(np.eye(len(self.knots)), n=2, axis=0)
        densities = []
        for component in range(2):
            scale = observed[:, component].max()
            transfer = self.chromatograms[:, component]
            transfer = transfer / transfer.max()
            design = np.vstack([np.column_stack([sampling, np.zeros(len(times))]),
                                np.column_stack([accumulation, -transfer]),
                                .002 * np.column_stack([curvature, np.zeros(len(curvature))])])
            target = np.r_[observed[:, component] / scale,
                           np.zeros(len(supports) + len(curvature))]
            densities.append(positive_least_squares(design, target)[:-1] * scale)
        self.densities = np.array(densities).T

    def basis_at(self, times):
        times = np.asarray(times)
        if times.ndim == 2:
            populations = interval_matrix(self.knots, times) @ self.densities
        else:
            populations = np.column_stack([np.interp(times, self.knots, column)
                                            for column in self.densities.T])
        return (populations[:, None, :] * self.arrivals[None, :, :]).reshape(-1, 2)

    def contributions(self, times, profiles):
        basis = self.basis_at(times)
        coefficients = nonnegative_fit(basis, profiles.ravel())
        return coefficients, np.linalg.norm(basis @ coefficients - profiles.ravel()) / np.linalg.norm(profiles)
