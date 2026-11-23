import numpy as np
from scipy.spatial.transform import Rotation

from frames import inverse, transform


def skew(vector):
    first, second, third = vector
    return np.array([[0, -third, second], [third, 0, -first], [-second, first, 0]])


def relative_motions(flange_poses, camera_poses):
    indices = np.unique(np.linspace(0, len(flange_poses) - 1, min(45, len(flange_poses))).astype(int))
    pairs = []
    for offset, first in enumerate(indices):
        for second in indices[offset + 1:]:
            arm = inverse(flange_poses[second]) @ flange_poses[first]
            camera = camera_poses[second] @ inverse(camera_poses[first])
            if Rotation.from_matrix(arm[:3, :3]).magnitude() > 0.08:
                pairs.append((arm, camera))
    return pairs


def estimate(flange_poses, camera_poses):
    pairs = relative_motions(flange_poses, camera_poses)
    coefficients, targets = [], []
    for arm, camera in pairs:
        arm_vector = Rotation.from_matrix(arm[:3, :3]).as_rotvec()
        camera_vector = Rotation.from_matrix(camera[:3, :3]).as_rotvec()
        coefficients.append(skew(arm_vector + camera_vector))
        targets.append(camera_vector - arm_vector)
    solution = np.linalg.lstsq(np.vstack(coefficients), np.concatenate(targets), rcond=None)[0]
    parameter = 2 * solution / np.sqrt(1 + solution @ solution)
    squared_norm = parameter @ parameter
    rotation = ((1 - squared_norm / 2) * np.eye(3)
                + 0.5 * (np.outer(parameter, parameter)
                         + np.sqrt(4 - squared_norm) * skew(parameter)))
    coefficients, targets = [], []
    for arm, camera in pairs:
        coefficients.append(arm[:3, :3] - np.eye(3))
        targets.append(rotation @ camera[:3, 3] - arm[:3, 3])
    translation = np.linalg.lstsq(np.vstack(coefficients), np.concatenate(targets), rcond=None)[0]
    return transform(rotation, translation)
