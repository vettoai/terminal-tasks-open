"""Stationarity of a table-mounted board in the robot base frame.

Position errors are distances to the arithmetic position mean. Orientations
use scipy Rotation.mean; angular errors are the degree magnitudes of
mean_rotation.inv() * observation_rotation. RMS is sqrt(mean(error**2)).
"""

import argparse
from pathlib import Path

import numpy as np
import yaml
from scipy.spatial.transform import Rotation

from fk import Kinematics
from sync import load_observations


def statistics(poses):
    positions = poses[:, :3, 3]
    position_errors = np.linalg.norm(positions - positions.mean(axis=0), axis=1) * 1000
    rotations = Rotation.from_matrix(poses[:, :3, :3])
    orientation_errors = np.degrees((rotations.mean().inv() * rotations).magnitude())
    return {
        'samples_used': len(poses),
        'position_rms_mm': float(np.sqrt(np.mean(position_errors ** 2))),
        'position_max_mm': float(position_errors.max()),
        'orientation_rms_deg': float(np.sqrt(np.mean(orientation_errors ** 2))),
        'orientation_max_deg': float(orientation_errors.max()),
    }


def main():
    parser = argparse.ArgumentParser(description='Measure table-board stationarity.')
    parser.add_argument('--session', required=True)
    parser.add_argument('--calibration', required=True)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parent
    camera = yaml.safe_load((root / 'config/camera.yaml').read_text())
    kinematics = Kinematics(root / camera['urdf'], camera['flange_frame'])
    joints, observations = load_observations(arguments.session, kinematics.joint_names)
    calibration = np.asarray(yaml.safe_load(Path(arguments.calibration).read_text())['flange_T_camera'])
    poses = kinematics.poses(joints) @ calibration @ observations
    print(yaml.safe_dump(statistics(poses), sort_keys=False), end='')


if __name__ == '__main__':
    main()
