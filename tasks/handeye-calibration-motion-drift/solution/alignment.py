import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from frames import transform as rigid
from timing import edge_model


def residuals(flange, camera, mount):
    target = flange @ mount @ camera
    positions = target[:, :3, 3]
    position_error = (positions - positions.mean(axis=0)) / 0.0004
    rotations = Rotation.from_matrix(target[:, :3, :3])
    rotation_error = (rotations.mean().inv() * rotations).as_rotvec() / np.radians(0.09)
    return np.concatenate([position_error.ravel(), rotation_error.ravel()])


def spatial_estimate(flange, camera):
    rotation, translation = cv2.calibrateHandEye(
        list(flange[:, :3, :3]), list(flange[:, :3, 3]),
        list(camera[:, :3, :3]), list(camera[:, :3, 3]), method=cv2.CALIB_HAND_EYE_PARK)
    left, _, right = np.linalg.svd(rotation)
    rotation = left @ np.diag([1.0, 1.0, np.linalg.det(left @ right)]) @ right
    return rigid(rotation, np.asarray(translation).reshape(3))


def fit_spatial(recording, kinematics, indices, clock):
    flange = kinematics.poses(recording.joints_at(clock, indices))
    camera = recording.camera[indices]
    mount = spatial_estimate(flange, camera)
    initial = np.r_[Rotation.from_matrix(mount[:3, :3]).as_rotvec(), mount[:3, 3]]

    def evaluate(parameters):
        candidate = rigid(Rotation.from_rotvec(parameters[:3]).as_matrix(), parameters[3:])
        return residuals(flange, camera, candidate)

    result = least_squares(evaluate, initial, x_scale=[1, 1, 1, 0.1, 0.1, 0.1],
                           ftol=1e-10, xtol=1e-10, gtol=1e-8, max_nfev=120)
    mount = rigid(Rotation.from_rotvec(result.x[:3]).as_matrix(), result.x[3:])
    target = flange @ mount @ camera
    return mount, target[:, :3, 3].mean(axis=0), float(np.mean(result.fun ** 2))


class EventLattice:
    def __init__(self, recording, kinematics):
        self.recording = recording
        self.ratio, modulo, bounds, windows = edge_model(recording)
        self.bounds, self.block_windows = bounds, windows
        blocks, offsets = [], []
        for block, phase in enumerate(modulo):
            for alias in range(-19, 20):
                offset = phase + .1 * alias
                if abs(offset) <= 1.8:
                    blocks.append(block)
                    offsets.append(offset)
        self.blocks, self.offsets = np.array(blocks), np.array(offsets)
        self.times = recording.exposures[:, None] * self.ratio + self.offsets
        self.frame_windows = np.r_[0, np.cumsum(np.diff(recording.shutters) > 10)][recording.frame_indices]
        upper = np.searchsorted(recording.times, self.times, side='right')
        upper = np.clip(upper, 1, len(recording.times)-1)
        lower = upper - 1
        valid = ((self.times >= recording.times[lower]) & (self.times <= recording.times[upper])
                 & (recording.times[upper] - recording.times[lower] < .01))
        valid &= self.frame_windows[:, None] == windows[self.blocks]
        valid &= ((recording.exposures[:, None] >= bounds[self.blocks, 0] - 1)
                  & (recording.exposures[:, None] <= bounds[self.blocks, 1] + 1))
        self.valid = valid
        self.flange = np.broadcast_to(np.eye(4), (*valid.shape, 4, 4)).copy()
        weight = ((self.times - recording.times[lower])
                  / (recording.times[upper] - recording.times[lower]))
        joints = (recording.positions[lower]
                  + weight[..., None] * (recording.positions[upper] - recording.positions[lower]))
        self.flange[valid] = kinematics.poses(joints[valid])
        self.transitions = ((self.blocks[:, None] + 1 == self.blocks[None, :])
                            | (self.blocks[:, None] == self.blocks[None, :]))

    def associate(self, mount, board):
        poses = self.flange @ mount @ self.recording.camera[:, None]
        distance = np.sum((poses[:, :, :3, 3] - board[:3, 3]) ** 2, axis=2) / .0004 ** 2
        relative = board[:3, :3].T @ poses[:, :, :3, :3]
        cosine = (np.trace(relative, axis1=2, axis2=3) - 1) / 2
        distance += np.arccos(np.clip(cosine, -1, 1)) ** 2 / np.radians(.09) ** 2
        distance[~self.valid] = np.inf
        selected = np.empty(len(distance), dtype=int)
        for window in np.unique(self.frame_windows):
            rows = np.flatnonzero(self.frame_windows == window)
            costs = distance[rows[0]].copy()
            parents = []
            for previous, current in zip(rows[:-1], rows[1:]):
                allowed = self.transitions & (self.times[previous, :, None] < self.times[current, None, :])
                values = np.where(allowed, costs[:, None], np.inf)
                parent = np.argmin(values, axis=0)
                costs = values[parent, np.arange(len(costs))] + distance[current]
                parents.append(parent)
            state = int(np.argmin(costs))
            if not np.isfinite(costs[state]):
                raise ValueError('No ordered exposure association fits the latch streams')
            selected[rows[-1]] = state
            for row, parent in zip(rows[-2::-1], parents[::-1]):
                state = int(parent[state])
                selected[row] = state
        return {'ratio': self.ratio, 'offsets': self.offsets[selected]}


def mean_board(flange, camera, mount):
    poses = flange @ mount @ camera
    return rigid(Rotation.from_matrix(poses[:, :3, :3]).mean().as_matrix(), poses[:, :3, 3].mean(axis=0))


def estimate_capture(recording, kinematics, survey):
    indices = np.arange(len(recording.camera))
    if np.max(np.ptp(recording.positions, axis=0)) < .001:
        return np.eye(4), np.zeros(2), 0.0
    lattice = EventLattice(recording, kinematics)
    later = np.flatnonzero((lattice.block_windows == 0) & (np.arange(len(lattice.bounds)) > 0))
    end = min([lattice.bounds[0, 1], *[lattice.bounds[block, 0] for block in later]]) - .1
    anchor = np.flatnonzero((lattice.frame_windows == 0) & (recording.exposures < end))
    if len(anchor) < 12:
        raise ValueError('Insufficient initial uninterrupted camera motion')
    starts = []
    for state in np.flatnonzero(lattice.blocks == 0):
        clock = {'ratio': lattice.ratio, 'offsets': np.full(len(indices), lattice.offsets[state])}
        mount, origin, cost = fit_spatial(recording, kinematics, anchor, clock)
        starts.append((float(np.linalg.norm(origin - survey['origin_base_m'])), mount, clock))
    candidates = []
    for _, mount, clock in sorted(starts, key=lambda item: item[0])[:3]:
        board = mean_board(kinematics.poses(recording.joints_at(clock, anchor)), recording.camera[anchor], mount)
        for _ in range(6):
            clock = lattice.associate(mount, board)
            mount, origin, cost = fit_spatial(recording, kinematics, indices, clock)
            board = mean_board(kinematics.poses(recording.joints_at(clock, indices)), recording.camera, mount)
        distance = float(np.linalg.norm(origin - survey['origin_base_m']))
        candidates.append((distance, cost, mount, clock))
    admissible = [item for item in candidates if item[0] <= survey['position_uncertainty_m']]
    if not admissible:
        raise ValueError('No exposure association agrees with the target survey')
    _, cost, mount, clock = min(admissible, key=lambda item: item[1])
    return mount, clock, cost
