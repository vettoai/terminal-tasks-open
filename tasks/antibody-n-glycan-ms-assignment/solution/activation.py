from dataclasses import replace

import numpy as np


def support_overlap(source, destination):
    overlap = np.maximum(0, np.minimum(destination[:, None, 1], source[None, :, 1])
                         - np.maximum(destination[:, None, 0], source[None, :, 0]))
    return overlap / (destination[:, 1] - destination[:, 0])[:, None]


def separate_activation(observations, injection, drifts):
    selected = [row for row in observations if row.injection == injection and row.drift in drifts
                and row.exposure is not None and min(row.exposure) > 0]
    functions = sorted({row.function for row in selected},
                       key=lambda function: -np.mean([row.exposure[0] / sum(row.exposure)
                                                       for row in selected if row.function == function]))
    if len(functions) != 2:
        raise ValueError('two complementary stepped activation programmes are needed')
    blocks = [sorted({(row.start, row.end, *row.exposure) for row in selected if row.function == function})
              for function in functions]
    supports = [np.array([block[:2] for block in programme]) for programme in blocks]
    fractions = [np.array([block[2:] for block in programme], dtype=float) for programme in blocks]
    fractions = [values / values.sum(axis=1, keepdims=True) for values in fractions]
    design = np.block([
        [np.diag(fractions[0][:, 0]), fractions[0][:, 1, None] * support_overlap(supports[1], supports[0])],
        [fractions[1][:, 0, None] * support_overlap(supports[0], supports[1]), np.diag(fractions[1][:, 1])],
    ])
    coordinates = []
    for row in sorted(selected, key=lambda row: row.coordinate):
        if not coordinates or abs(row.coordinate / coordinates[-1] - 1) > 1e-6:
            coordinates.append(row.coordinate)
    result = []
    for coordinate in coordinates:
        records = [row for row in selected if abs(row.coordinate / coordinate - 1) < 1e-6]
        indexed = {(row.function, row.start, row.drift): row for row in records}
        ordered = [indexed[function, block[0], drift] for function, programme in zip(functions, blocks)
                   for block in programme for drift in drifts]
        values = np.array([row.response for row in ordered]).reshape(len(design), len(drifts))
        conditional = np.maximum(np.linalg.solve(design, values), 0)
        beginning = 0
        for energy, function, programme in zip((18, 32), functions, blocks):
            for index, block in enumerate(programme):
                for position, drift in enumerate(drifts):
                    original = indexed[function, block[0], drift]
                    result.append(replace(original, coordinate=coordinate, energy=energy,
                                          response=conditional[beginning + index, position],
                                          exposure=(1, 0) if energy == 18 else (0, 1)))
            beginning += len(programme)
    return result
