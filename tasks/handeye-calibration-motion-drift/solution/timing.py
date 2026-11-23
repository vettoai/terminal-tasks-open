import numpy as np


def circular_seconds(values, period):
    return np.angle(np.mean(np.exp(2j * np.pi * values / period))) * period / (2 * np.pi)


def edge_model(recording):
    period = 0.1
    controller = recording.edge_times['controller']
    camera = recording.edge_times['camera']
    controller_width = (1 - recording.edge_levels['controller']) * 0.017
    camera_width = (1 - recording.edge_levels['camera']) * 0.017
    phase = circular_seconds(controller - controller_width, period)
    gaps = np.diff(camera)
    width_changes = np.diff(camera_width)
    ratio = 1.0
    for iteration in range(4):
        residual = (ratio * gaps - width_changes + period / 2) % period - period / 2
        tolerance = 0.0005 if iteration == 0 else 0.000015
        cuts = np.flatnonzero((abs(residual) > tolerance) | (gaps > 10)) + 1
        blocks = np.split(np.arange(len(camera)), cuts)
        numerator, denominator = 0.0, 0.0
        for block in blocks:
            times, widths = camera[block], camera_width[block]
            origin = circular_seconds(ratio * times - widths, period)
            ideal = np.rint((ratio * times - widths - origin) / period) * period + widths
            centred = times - times.mean()
            numerator += np.dot(centred, ideal - ideal.mean())
            denominator += np.dot(centred, centred)
        ratio = numerator / denominator
    edge_offsets = np.array([(phase - circular_seconds(ratio * camera[block] - camera_width[block], period)
                              + period / 2) % period - period / 2 for block in blocks])
    windows = np.r_[0, np.cumsum(gaps > 10)]
    return ratio, edge_offsets, np.array([[camera[block[0]], camera[block[-1]]]
                                         for block in blocks]), np.array([windows[block[0]] for block in blocks])
