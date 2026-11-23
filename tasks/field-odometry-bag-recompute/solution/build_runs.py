import csv
import struct
import sys
from pathlib import Path

import numpy as np
import yaml
from rosbags.rosbag1 import Reader


def integral(times, values):
    return np.concatenate(([0.0], np.cumsum(np.diff(times) * (values[:-1] + values[1:]) * .5)))


def acquisition_times(wheel_records, topics):
    stamps = np.array([record[0] for record in wheel_records], dtype=np.int64)
    sequence = np.array([record[1] for record in wheel_records], dtype=np.int64)
    residual = stamps - (sequence - sequence[0]) * 50000000
    sorted_residual = np.sort(residual)
    sections = np.split(sorted_residual, np.flatnonzero(np.diff(sorted_residual) > 500000000) + 1)
    levels = np.array([int(np.median(section)) for section in sections], dtype=np.int64)
    membership = np.argmin(np.abs(residual[:, None] - levels), axis=1)
    host_difference = np.array([record[-1] - record[0] for record in wheel_records])
    host_levels = np.array([np.median(host_difference[membership == index])
                            for index in range(len(levels))])
    corrections = levels - levels[membership[0]]
    origin = topics[1][0][0]
    aligned = []
    for records in topics:
        stamps = np.array([record[0] for record in records], dtype=np.int64)
        host_difference = np.array([record[-1] - record[0] for record in records])
        membership = np.argmin(np.abs(host_difference[:, None] - host_levels), axis=1)
        aligned.append((stamps - origin - corrections[membership]) / 1e9)
    return aligned


def turn_observations(wheel_times, yaw_travel, imu_times, gyro, temperature):
    gyro_integral = np.interp(wheel_times, imu_times, integral(imu_times, gyro))
    thermal_integral = np.interp(wheel_times, imu_times, integral(imu_times, temperature))
    observations = []
    begin = 0
    while begin < len(wheel_times) - 1:
        end = np.searchsorted(wheel_times, wheel_times[begin] + 2.)
        if end >= len(wheel_times):
            break
        duration = wheel_times[end] - wheel_times[begin]
        if np.max(np.diff(wheel_times[begin:end + 1])) <= .25:
            observations.append(((yaw_travel[end] - yaw_travel[begin]) / duration,
                                 (thermal_integral[end] - thermal_integral[begin]) / duration,
                                 (gyro_integral[end] - gyro_integral[begin]) / duration, duration))
        begin = end
    return np.array(observations)


def load_run(path, geometry):
    wheel_records = []
    inertial_records = []
    temperature_records = []
    counter = False
    with Reader(path) as reader:
        wheel_connection = next(connection for connection in reader.connections if connection.topic == '/wheel_ticks')
        counter = 'uint16 left_count' in wheel_connection.msgdef.data
        for connection, receipt, raw in reader.messages():
            sequence, seconds, nanoseconds, frame_length = struct.unpack_from('<IIII', raw)
            stamp = seconds * 10**9 + nanoseconds
            offset = 16 + frame_length
            if connection.topic == '/wheel_ticks':
                counts = struct.unpack_from('<HH' if counter else '<ii', raw, offset)
                wheel_records.append((stamp, sequence, *counts, receipt))
            elif connection.topic == '/imu/data':
                gyro = struct.unpack_from('<d', raw, offset + 120)[0]
                acceleration = struct.unpack_from('<d', raw, offset + 200)[0]
                lateral = struct.unpack_from('<d', raw, offset + 208)[0]
                inertial_records.append((stamp, sequence, gyro, acceleration, lateral, receipt))
            elif connection.topic == '/imu/temperature':
                temperature_records.append((stamp, sequence, struct.unpack_from('<d', raw, offset)[0], receipt))
    wheel_times, imu_times, temperature_times = acquisition_times(
        wheel_records, [wheel_records, inertial_records, temperature_records])
    left = np.array([record[2] for record in wheel_records], dtype=np.int64)
    right = np.array([record[3] for record in wheel_records], dtype=np.int64)
    delta_left = np.diff(left, prepend=left[0])
    delta_right = np.diff(right, prepend=right[0])
    modulus = 65536 if counter else 2**32
    delta_left = (delta_left + modulus // 2) % modulus - modulus // 2
    delta_right = (delta_right + modulus // 2) % modulus - modulus // 2
    gyro = np.array([record[2] for record in inertial_records])
    acceleration = np.array([record[3] for record in inertial_records])
    lateral = np.array([record[4] for record in inertial_records])
    temperatures = np.interp(imu_times, temperature_times, [record[2] for record in temperature_records])
    stationary = (delta_left == 0) & (delta_right == 0)
    stationary &= np.diff(wheel_times, prepend=0.) < .2
    stop_indices = np.flatnonzero(stationary)
    sections = np.split(stop_indices, np.flatnonzero(np.diff(stop_indices) > 1) + 1)
    still = np.zeros(len(imu_times), dtype=bool)
    for section in sections:
        if len(section) == 0:
            continue
        begin = wheel_times[max(0, section[0] - 1)]
        end = wheel_times[section[-1]]
        if end - begin >= 1.:
            still |= (imu_times >= begin + .3) & (imu_times <= end - .3)
    acceleration_bias = np.mean(acceleration[(imu_times > .5) & (imu_times < 18.)])
    scale = 2. * np.pi * geometry['wheel_radius_m'] / geometry['ticks_per_rev']
    centre_delta = (delta_left + delta_right) * scale * .5
    intervals = np.diff(wheel_times, prepend=0.)
    velocity = centre_delta / intervals
    usable = (intervals <= .15) & (wheel_times > .1)
    velocity_times = wheel_times - intervals * .5
    yaw_travel = np.cumsum((delta_right - delta_left) * scale)
    return {'run': path.stem, 'imu': geometry['imu'], 'times': imu_times,
            'temperature': temperatures, 'gyro': gyro, 'still': still,
            'acceleration': acceleration, 'lateral': lateral, 'acceleration_bias': acceleration_bias,
            'velocity_times': velocity_times[usable], 'velocity': velocity[usable],
            'turns': turn_observations(wheel_times, yaw_travel, imu_times, gyro, temperatures)}


def thermal_models(runs):
    moments = {}
    for run in runs:
        turns = run['turns']
        design = np.column_stack((turns[:, 0], np.ones(len(turns))))
        weights = np.sqrt(turns[:, 3])
        design *= weights[:, None]
        temperature = turns[:, 1] * weights
        gyro = turns[:, 2] * weights
        centred_temperature = temperature - design @ np.linalg.lstsq(design, temperature, rcond=None)[0]
        centred_gyro = gyro - design @ np.linalg.lstsq(design, gyro, rcond=None)[0]
        numerator, denominator = moments.get(run['imu'], (0., 0.))
        numerator += np.dot(centred_temperature, centred_gyro)
        denominator += np.dot(centred_temperature, centred_temperature)
        moments[run['imu']] = numerator, denominator
    return {imu: numerator / denominator for imu, (numerator, denominator) in moments.items()}


def contact_velocity(run, corrected, times, forward, inertial_transverse):
    imu_times = run['times']
    knots = np.linspace(0., times[-1], max(4, round(times[-1] / 15.) + 1))
    basis = np.column_stack([np.interp(imu_times, knots, row) for row in np.eye(len(knots))])
    forcing_integrals = np.column_stack([
        integral(imu_times, corrected * run['lateral'] * column) for column in basis.T])
    acceleration_integral = integral(imu_times, run['acceleration'])
    design, target = [], []
    for begin in np.arange(22., times[-1] - 2., 2.):
        end = begin + 2.
        selected = (run['velocity_times'] >= begin - .1) & (run['velocity_times'] <= end + .1)
        if np.count_nonzero(selected) < 2:
            continue
        wheel_times = run['velocity_times'][selected]
        if wheel_times[0] > begin or wheel_times[-1] < end or np.max(np.diff(wheel_times)) > .2:
            continue
        if np.min(run['velocity'][selected]) < .35:
            continue
        velocity_change = np.diff(np.interp([begin, end], run['velocity_times'], run['velocity']))[0]
        acceleration_change = np.diff(np.interp([begin, end], imu_times, acceleration_integral))[0]
        coefficients = [np.diff(np.interp([begin, end], imu_times, column))[0]
                        for column in forcing_integrals.T]
        design.append([end - begin, *coefficients])
        target.append(acceleration_change - velocity_change)
    design = np.array(design) / .0015
    target = np.array(target) / .0015
    global_design = np.column_stack((design[:, 0], design[:, 1:].sum(axis=1)))
    global_fit = np.linalg.lstsq(global_design, target, rcond=None)[0]
    penalties = []
    penalty_targets = []
    for index in range(len(knots)):
        row = np.zeros(len(knots) + 1)
        row[index + 1] = 1. / .2
        penalties.append(row)
        penalty_targets.append(global_fit[1] / .2)
    for index in range(len(knots) - 2):
        row = np.zeros(len(knots) + 1)
        row[index + 1:index + 4] = np.array([1., -2., 1.]) / .04
        penalties.append(row)
        penalty_targets.append(0.)
    coefficients = np.linalg.lstsq(np.vstack((design, penalties)),
                                    np.concatenate((target, penalty_targets)), rcond=None)[0]
    response = np.interp(times, knots, coefficients[1:])
    window = max(1, round(.2 / np.median(np.diff(imu_times))))
    lateral = np.convolve(run['lateral'], np.ones(window) / window, mode='same')
    model = -response * np.interp(times, imu_times, lateral)
    weight = np.clip((forward - .25) / .15, 0., 1.)
    weight = weight * weight * (3. - 2. * weight)
    return weight * model + (1. - weight) * inertial_transverse


def velocity_state(run, slope):
    turns = run['turns']
    design = np.column_stack((turns[:, 0], np.ones(len(turns))))
    weights = np.sqrt(turns[:, 3])
    coefficients = np.linalg.lstsq(design * weights[:, None],
                                    (turns[:, 2] - slope * turns[:, 1]) * weights, rcond=None)[0]
    debiased = run['gyro'] - slope * run['temperature']
    corrected = debiased - coefficients[1]
    corrected[run['still']] = 0.
    imu_times = run['times']
    times = np.unique(np.concatenate((imu_times, run['velocity_times'])))
    heading = np.interp(times, imu_times, integral(imu_times, corrected))
    acceleration = np.column_stack((np.interp(times, imu_times, run['acceleration']),
                                    np.interp(times, imu_times, run['lateral'])))
    observed = np.full(len(times), np.nan)
    observed[np.searchsorted(times, run['velocity_times'])] = run['velocity']
    still = np.interp(times, imu_times, run['still'].astype(float)) > .999
    window = max(1, round(1. / np.median(np.diff(imu_times))))
    averaged_yaw = np.convolve(corrected, np.ones(window) / window, mode='same')
    straight = np.abs(np.interp(times, imu_times, averaged_yaw)) < .0004
    settled_straight = np.zeros(len(times), dtype=bool)
    straight_indices = np.flatnonzero(straight)
    for section in np.split(straight_indices, np.flatnonzero(np.diff(straight_indices) > 1) + 1):
        if len(section):
            settled_straight[section] = times[section] > times[section[0]] + 4.
    state = np.array([0., 0., run['acceleration_bias']])
    covariance = np.diag([1e-10, 1e-10, .007**2 / 800.])
    filtered = np.empty((len(times), 3))
    covariances = np.empty((len(times), 3, 3))
    predicted = np.empty_like(filtered)
    prediction_covariances = np.empty_like(covariances)
    transitions = np.empty_like(covariances)
    identity = np.eye(3)
    for index in range(len(times)):
        transition = identity.copy()
        if index:
            duration = times[index] - times[index - 1]
            angle = heading[index] - heading[index - 1]
            cosine, sine = np.cos(angle), np.sin(angle)
            rotation = np.array([[cosine, sine], [-sine, cosine]])
            transition[:2, :2] = rotation
            transition[:2, 2] = -duration * np.array([(1. + cosine) * .5, -sine * .5])
            forcing = duration * (rotation @ acceleration[index - 1] + acceleration[index]) * .5
            state = transition @ state
            state[:2] += forcing
            covariance = transition @ covariance @ transition.T
            covariance[:2, :2] += np.eye(2) * (.007**2 * .02 * duration)
        transitions[index] = transition
        predicted[index] = state
        prediction_covariances[index] = covariance
        if np.isfinite(observed[index]):
            gain = covariance[:, 0] / (covariance[0, 0] + .0006**2)
            state = state + gain * (observed[index] - state[0])
            covariance = covariance - np.outer(gain, covariance[0])
        if still[index]:
            for component in (0, 1):
                gain = covariance[:, component] / (covariance[component, component] + 1e-8)
                state = state - gain * state[component]
                covariance = covariance - np.outer(gain, covariance[component])
        elif settled_straight[index]:
            gain = covariance[:, 1] / (covariance[1, 1] + .0005**2)
            state = state - gain * state[1]
            covariance = covariance - np.outer(gain, covariance[1])
        filtered[index] = state
        covariances[index] = covariance
    smoothed = filtered.copy()
    for index in range(len(times) - 2, -1, -1):
        gain = np.linalg.solve(prediction_covariances[index + 1],
                               transitions[index + 1] @ covariances[index]).T
        smoothed[index] += gain @ (smoothed[index + 1] - predicted[index + 1])
    forward, transverse = smoothed[:, :2].T
    transverse = contact_velocity(run, corrected, times, forward, transverse)
    return times, heading, forward, transverse


def reconstruct(run, slope):
    times, heading, forward, transverse = velocity_state(run, slope)
    distance = integral(times, np.hypot(forward, transverse))[-1]
    east = integral(times, forward * np.cos(heading) - transverse * np.sin(heading))[-1]
    north = integral(times, forward * np.sin(heading) + transverse * np.cos(heading))[-1]
    return run['run'], float(distance), float(east), float(north)


def main(project, output):
    geometry = yaml.safe_load((project / 'robots.yaml').read_text())
    runs = [load_run(path, geometry[path.stem.rsplit('_', 1)[0]])
            for path in sorted((project / 'bags').glob('*.bag'))]
    slopes = thermal_models(runs)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['run', 'distance_m', 'end_x_m', 'end_y_m'])
        for run in runs:
            writer.writerow(reconstruct(run, slopes[run['imu']]))


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))
