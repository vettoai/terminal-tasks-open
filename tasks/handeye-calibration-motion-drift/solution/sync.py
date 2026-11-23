import csv
from pathlib import Path

import numpy as np
import yaml
from scipy.spatial.transform import Rotation

from frames import transform as rigid


def rows(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))


class Recording:
    def __init__(self, session, joint_names):
        session = Path(session)
        manifest = yaml.safe_load((session / 'capture.yaml').read_text())
        self.capture_id = manifest['capture_id']
        reference = int(manifest['clock_reference_ns'])
        self.edge_times = {}
        self.edge_levels = {}
        for domain in ('controller', 'camera'):
            edges = rows(session / f'{domain}_edges.csv')
            self.edge_times[domain] = np.array([int(row['timestamp_ns']) - reference for row in edges], dtype=np.int64) * 1e-9
            self.edge_levels[domain] = np.array([int(row['level']) for row in edges])
        joints = rows(session / 'joint_states.csv')
        self.times = np.array([int(row['timestamp_ns']) - reference for row in joints], dtype=np.int64) * 1e-9
        self.positions = np.array([[float(row[name]) for name in joint_names] for row in joints])
        frames = rows(session / 'camera_frames.csv')
        self.shutters = np.array([int(row['timestamp_ns']) - reference for row in frames], dtype=np.int64) * 1e-9
        frame_indices = {row['frame_id']: index for index, row in enumerate(frames)}
        detections = [row for row in rows(session / 'fiducials.csv') if int(row['valid'])]
        self.frame_indices = np.array([frame_indices[row['frame_id']] for row in detections])
        self.exposures = self.shutters[self.frame_indices]
        self.camera = np.array([
            rigid(Rotation.from_quat([float(row[key]) for key in ('qx', 'qy', 'qz', 'qw')]).as_matrix(),
                  [float(row[key]) for key in ('tx', 'ty', 'tz')]) for row in detections])

    def joints_at(self, clock, indices):
        camera_times = self.exposures[indices]
        if isinstance(clock, dict):
            actual = camera_times * clock['ratio'] + clock['offsets'][indices]
        else:
            actual = camera_times + clock[0] + camera_times * clock[1] / 1000
        upper = np.searchsorted(self.times, actual, side='right')
        lower = upper - 1
        weight = (actual - self.times[lower]) / (self.times[upper] - self.times[lower])
        return self.positions[lower] + weight[:, None] * (self.positions[upper] - self.positions[lower])
