import csv
from pathlib import Path

import numpy as np
import pinocchio as pin
import yaml
from scipy.spatial.transform import Rotation


FILES = ('joint_states.csv', 'camera_frames.csv', 'fiducials.csv', 'capture.yaml',
         'controller_edges.csv', 'camera_edges.csv')
METRICS = ('position_rms_mm', 'position_max_mm', 'orientation_rms_deg', 'orientation_max_deg')
LIMITS = dict(zip(METRICS, (1.5, 3.0, 0.3, 0.5)))


def read_rows(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))


def reference_poses(session, urdf, clock_map):
    model = pin.buildModelFromUrdf(str(urdf))
    data = model.createData()
    frame = model.getFrameId('flange')
    rows = read_rows(Path(session) / FILES[0])
    timestamps = np.array([int(row['timestamp_ns']) for row in rows], dtype=np.int64)
    positions = np.array([[float(row[name]) for name in list(model.names)[1:]] for row in rows])

    detections = [row for row in read_rows(Path(session) / FILES[2]) if int(row['valid'])]
    manifest = yaml.safe_load((Path(session) / 'capture.yaml').read_text())
    reference = int(manifest['clock_reference_ns'])
    flange_poses, camera_poses = [], []
    for row in detections:
        elapsed = clock_map['oscillator_ns_by_frame'][row['frame_id']]
        timestamp = reference + round((1 + clock_map['skew_ppm'] * 1e-6) * elapsed
                                      + clock_map['offset_seconds'] * 1e9)
        upper = int(np.searchsorted(timestamps, timestamp, side='right'))
        lower = upper - 1
        weight = (timestamp - int(timestamps[lower])) / int(timestamps[upper] - timestamps[lower])
        joints = positions[lower] + weight * (positions[upper] - positions[lower])
        pin.framesForwardKinematics(model, data, joints)
        flange_poses.append(np.array(data.oMf[frame].homogeneous))
        pose = np.eye(4)
        pose[:3, 3] = [float(row[name]) for name in ('tx', 'ty', 'tz')]
        pose[:3, :3] = Rotation.from_quat([float(row[name]) for name in ('qx', 'qy', 'qz', 'qw')]).as_matrix()
        camera_poses.append(pose)
    return np.array(flange_poses), np.array(camera_poses)


def metrics(flange_poses, camera_poses, calibration):
    board = flange_poses @ calibration @ camera_poses
    positions = board[:, :3, 3]
    distances = np.linalg.norm(positions - np.mean(positions, axis=0), axis=1) * 1000
    rotations = Rotation.from_matrix(board[:, :3, :3])
    angles = np.degrees((rotations.mean().inv() * rotations).magnitude())
    return {'samples_used': len(board),
            'position_rms_mm': float(np.sqrt(np.mean(distances ** 2))),
            'position_max_mm': float(np.max(distances)),
            'orientation_rms_deg': float(np.sqrt(np.mean(angles ** 2))),
            'orientation_max_deg': float(np.max(angles))}
