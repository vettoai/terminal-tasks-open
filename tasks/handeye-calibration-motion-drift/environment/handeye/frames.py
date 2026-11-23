import numpy as np
from scipy.spatial.transform import Rotation


def transform(rotation, translation):
    result = np.eye(4)
    result[:3, :3] = rotation
    result[:3, 3] = translation
    return result


def inverse(pose):
    rotation = pose[:3, :3].T
    return transform(rotation, -rotation @ pose[:3, 3])


def from_detection(row):
    quaternion = [float(row[key]) for key in ('qx', 'qy', 'qz', 'qw')]
    translation = [float(row[key]) for key in ('tx', 'ty', 'tz')]
    return transform(Rotation.from_quat(quaternion).as_matrix(), translation)
