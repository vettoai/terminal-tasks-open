from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from profiles import FlightTimeReader


@dataclass(frozen=True)
class Observation:
    injection: str
    function: str
    retention: float
    kind: str
    coordinate: float
    drift: float | None
    response: float
    energy: float | str
    cone: float
    start: float
    end: float
    exposure: tuple[int, int] | None


class AcquisitionExports:
    def __init__(self, workbook):
        self.workbook = workbook
        self.ledger = {tuple(row[:4]): row[4:] for row in
                       workbook['Acquisition ledger'].iter_rows(min_row=2, values_only=True)}
        settings = list(workbook['Run settings'].values)
        registry_start = next(index for index, row in enumerate(settings)
                              if row[0] == 'Reference source function')
        targets = {row[0]: row[4] for row in settings[registry_start + 1:] if row[0]}
        self.flight = FlightTimeReader(workbook)
        self.references = defaultdict(list)
        for block, coordinate, drift, area in self.flight.records(workbook['Lock reference']):
            midpoint = (block[2] + block[3]) / 2
            ratio = coordinate / targets[block[1]]
            self.references[block[0]].append((midpoint, ratio))
        for injection in self.references:
            self.references[injection] = np.array(sorted(self.references[injection]))

    def observations(self, sheet):
        result = []
        records = ((tuple(row[:4]), row[5], row[6], row[7]) for row in
                   self.workbook[sheet].iter_rows(min_row=2, values_only=True)) if sheet == 'MSMS' else (
                       self.flight.records(self.workbook[sheet]))
        for block, coordinate, drift, area in records:
            cone, region, energy, packets, kind = self.ledger[block][:5]
            doses = self.ledger[block][5:7]
            exposure = tuple(doses) if region == 'Transfer' else None
            kind = kind.removesuffix(' profile')
            midpoint = (block[2] + block[3]) / 2
            if sheet != 'MSMS':
                references = self.references[block[0]]
                if not references[0, 0] <= midpoint <= references[-1, 0]:
                    raise ValueError('mass reference does not bracket a sample block')
                factor = np.interp(midpoint, references[:, 0], references[:, 1])
                coordinate /= factor
            result.append(Observation(block[0], block[1], midpoint / 60, kind,
                                      coordinate, drift, area / packets, energy, cone,
                                      block[2] / 60, block[3] / 60, exposure))
        return result


def mobility_profiles(observations, injection, coordinate, energy=None):
    selected = [row for row in observations if row.injection == injection
                and row.kind == 'Mobility extraction'
                and abs(row.coordinate - coordinate) / coordinate < 1e-6
                and (energy is None or row.energy == energy)]
    drift = sorted({row.drift for row in selected})
    retentions = sorted({row.retention for row in selected})
    values = {(row.retention, row.drift): row.response for row in selected}
    profiles = [[values[(retention, position)] for position in drift] for retention in retentions]
    return np.array(drift), np.array(retentions), np.array(profiles)
