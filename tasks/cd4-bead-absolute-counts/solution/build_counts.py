import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from itertools import combinations
from pathlib import Path

import flowio
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from scipy.special import gammaln, log_ndtr, logsumexp


GATING = '{http://www.isac-net.org/std/Gating-ML/v2.0/gating}'
DATATYPES = '{http://www.isac-net.org/std/Gating-ML/v2.0/datatypes}'
FLUORESCENCE = ('FITC-A', 'PE-A', 'APC-A')


def read_acquisition(path):
    tube = flowio.FlowData(str(path))
    channels = [tube.channels[str(index)]['PnN'] for index in range(1, tube.channel_count + 1)]
    return tube, channels, np.asarray(tube.events).reshape(-1, tube.channel_count)


def block_identity(tube, channels):
    return (tube.text['cyt'], tube.text['date'],
            tuple(float(tube.text[f'p{channels.index(channel) + 1}v']) for channel in FLUORESCENCE))


def gate_masks(events, channels, gate_file):
    definitions = {}
    for gate in ET.parse(gate_file).getroot().findall(GATING + 'RectangleGate'):
        mask = np.ones(len(events), dtype=bool)
        for dimension in gate.findall(GATING + 'dimension'):
            channel = dimension.find(DATATYPES + 'fcs-dimension').attrib[DATATYPES + 'name']
            values = events[:, channels.index(channel)]
            if GATING + 'min' in dimension.attrib:
                mask &= values >= float(dimension.attrib[GATING + 'min'])
            if GATING + 'max' in dimension.attrib:
                mask &= values < float(dimension.attrib[GATING + 'max'])
        definitions[gate.attrib[GATING + 'id']] = (mask, gate.attrib.get(GATING + 'parent_id'))
    masks = {}

    def apply(name):
        if name not in masks:
            local, parent = definitions[name]
            masks[name] = local & apply(parent) if parent else local
        return masks[name]

    return {name: apply(name) for name in definitions}


def population_groups(areas, column, count):
    order = np.argsort(areas[:, column])
    gaps = np.diff(np.log(areas[order, column]))
    cuts = np.sort(np.argpartition(gaps, -(count - 1))[-(count - 1):]) + 1
    return np.split(areas[order], cuts)


def affine_response(targets, populations, column, ceiling):
    usable = [index for index, group in enumerate(populations)
              if np.isfinite(targets[index]) and np.max(group[:, column]) < ceiling]
    means = np.array([np.mean(populations[index][:, column]) for index in usable])
    errors = np.array([np.std(populations[index][:, column]) / np.sqrt(len(populations[index])) for index in usable])
    design = np.column_stack([np.asarray(targets)[usable], np.ones(len(usable))])
    return np.linalg.lstsq(design / errors[:, None], means / errors, rcond=None)[0]


def qc_records(project):
    records = []
    for path in sorted((project / 'qc/acquisitions').glob('*.fcs')):
        tube, channels, events = read_acquisition(path)
        indices = [channels.index(channel) for channel in FLUORESCENCE]
        records.append({'identity': block_identity(tube, channels), 'text': tube.text,
                        'areas': events[:, indices],
                        'ceiling': np.array([float(tube.text[f'p{index + 1}r']) - 1 for index in indices])})
    return records


def transferred_assignments(project, records, uncertainties=None):
    with (project / 'qc/mesf_certificates.csv').open(newline='') as handle:
        certificates = list(csv.DictReader(handle))
    sessions = {}
    covariances = {}
    for record in records:
        if 'calibration lot' not in record['text']:
            continue
        lot = record['text']['calibration lot']
        channel = record['text']['calibration channel']
        rows = sorted([row for row in certificates if row['lot'] == lot and row['channel'] == channel
                       and row['mesf']], key=lambda row: float(row['mesf']))
        assigned = np.array([np.nan, *[float(row['mesf']) for row in rows]])
        column = FLUORESCENCE.index(channel)
        populations = population_groups(record['areas'], column, len(assigned))
        sessions.setdefault(record['identity'], {})[column] = affine_response(
            assigned, populations, column, record['ceiling'][column])
        positive = np.array([np.mean(group[:, column]) for group in populations[1:]])
        errors = np.array([np.std(group[:, column], ddof=1) / np.sqrt(len(group)) for group in populations[1:]])
        design = np.column_stack([assigned[1:], np.ones(len(positive))])
        covariances.setdefault(record['identity'], {})[column] = np.linalg.inv(
            (design / errors[:, None]).T @ (design / errors[:, None]))
    assignments = {}
    for record in records:
        lot = record['text'].get('reference lot')
        if lot is None or record['identity'] not in sessions:
            continue
        populations = population_groups(record['areas'], 1, 6)
        response = sessions[record['identity']]
        means = np.array([np.mean(group, axis=0) for group in populations])
        assignments[(lot, record['identity'][0])] = np.column_stack([
            (means[:, column] - response[column][1]) / response[column][0] for column in range(3)])
        if uncertainties is not None:
            errors = np.array([np.std(group, axis=0, ddof=1) / np.sqrt(len(group)) for group in populations])
            assigned = assignments[(lot, record['identity'][0])]
            propagated = np.empty_like(assigned)
            for column in range(3):
                design = np.column_stack([assigned[:, column], np.ones(len(assigned))])
                variance = np.einsum('ij,jk,ik->i', design, covariances[record['identity']][column], design)
                propagated[:, column] = np.sqrt(errors[:, column] ** 2 + variance) / response[column][0]
            uncertainties[(lot, record['identity'][0])] = propagated
    return assignments


def observed_populations(areas):
    order = np.argsort(areas[:, 1])
    gaps = np.diff(np.log(areas[order, 1]))
    return np.split(areas[order], np.flatnonzero(gaps > 0.18) + 1)


def region_correspondences(record, targets, target_errors=None, forced=None, include_edges=False):
    populations = observed_populations(record['areas'])
    count = len(populations)
    if not 3 <= count <= len(targets):
        return []
    lower = float(record['text']['qc region min'])
    upper = float(record['text']['qc region max'])
    lower_cut = lower > 0 and populations[0][:, 0].min() - lower < 0.5 * populations[0][:, 0].std()
    upper_cut = upper < record['ceiling'][0] + 1 and upper - populations[-1][:, 0].max() < 0.5 * populations[-1][:, 0].std()
    complete = np.ones(count, dtype=bool)
    if not include_edges:
        complete[0] = not lower_cut
        complete[-1] = not upper_cut
    means = np.array([group.mean(axis=0) for group in populations])
    errors = np.array([group.std(axis=0, ddof=1) / np.sqrt(len(group)) for group in populations])
    target_errors = np.zeros_like(targets) if target_errors is None else target_errors
    offsets = range(len(targets) - count + 1)
    if forced == 'first':
        offsets = [0]
    elif forced == 'last':
        offsets = [len(targets) - count]
    candidates = []
    for start in offsets:
        indices = np.arange(start, start + count)
        fitted, scores = [], []
        for column in range(3):
            usable = complete & np.array([group[:, column].max() < record['ceiling'][column] for group in populations])
            if usable.sum() < 2:
                break
            design = np.column_stack([targets[indices[usable], column], np.ones(usable.sum())])
            measured = means[usable, column]
            standard = errors[usable, column]
            coefficients = np.linalg.lstsq(design / standard[:, None], measured / standard, rcond=None)[0]
            for iteration in range(3):
                standard = np.sqrt(errors[usable, column] ** 2 +
                                   (coefficients[0] * target_errors[indices[usable], column]) ** 2)
                coefficients = np.linalg.lstsq(design / standard[:, None], measured / standard, rcond=None)[0]
            if coefficients[0] <= 0:
                break
            residuals = (measured - design @ coefficients) / standard
            scores.extend(residuals.tolist())
            fitted.append(coefficients)
        if len(fitted) != 3:
            continue
        gain, pedestal = fitted[0]
        predicted = targets[:, 0] * gain + pedestal
        relative_spread = np.median([group[:, 0].std() / max(group[:, 0].mean() - pedestal, 1)
                                     for index, group in enumerate(populations)
                                     if complete[index] and group[:, 0].max() < record['ceiling'][0]])
        spread = np.maximum(targets[:, 0] * gain * relative_spread, 1)
        consistent = True
        for bound, cutting, index, previous, lower_edge in (
                (lower, lower_cut, start, start - 1, True),
                (upper, upper_cut, start + count - 1, start + count, False)):
            if cutting:
                consistent &= abs(bound - predicted[index]) <= 2.5 * spread[index]
            elif lower_edge:
                consistent &= bound < predicted[index] - 2 * spread[index]
            else:
                consistent &= bound > min(predicted[index] + 2 * spread[index], record['ceiling'][0])
            if 0 <= previous < len(targets):
                consistent &= (predicted[previous] + 2 * spread[previous] < bound if lower_edge else
                               predicted[previous] - 2 * spread[previous] > bound)
        for index, group in enumerate(populations):
            for column in range(3):
                if np.any(group[:, column] >= record['ceiling'][column]):
                    center = targets[start + index, column] * fitted[column][0] + fitted[column][1]
                    consistent &= center + 6 * 0.02 * targets[start + index, column] * fitted[column][0] >= record['ceiling'][column]
        if forced is not None or (consistent and max(map(abs, scores)) <= 6):
            candidates.append({'start': start, 'count': count, 'lower_cut': bool(lower_cut),
                               'upper_cut': bool(upper_cut), 'fitted': fitted,
                               'loss': float(np.sum(np.square(scores)))})
    return candidates


def detector_responses(project):
    with (project / 'qc/targets.csv').open(newline='') as handle:
        assigned = sorted(csv.DictReader(handle), key=lambda row: float(row['PE-A']))
    legacy = np.array([[float(row[channel]) for channel in FLUORESCENCE] for row in assigned])
    records = qc_records(project)
    uncertainties = {}
    assignments = transferred_assignments(project, records, uncertainties)
    responses = {}
    for record in records:
        lot = record['text'].get('reference lot')
        if lot is None:
            continue
        targets = assignments.get((lot, record['identity'][0]), legacy)
        candidates = region_correspondences(record, targets, uncertainties.get((lot, record['identity'][0])))
        if not candidates:
            raise ValueError('Reference populations cannot be assigned at ' + str(record['identity']))
        fitted = min(candidates, key=lambda candidate: candidate['loss'])['fitted']
        responses[record['identity']] = (np.array([gain for gain, _ in fitted]),
                                          np.array([pedestal for _, pedestal in fitted]))
    return responses


def blood_contents(project):
    with (project / 'preparation/containers.csv').open(newline='') as handle:
        containers = list(csv.DictReader(handle))
    liquid = {row['container']: float(row['initial_volume_ul']) for row in containers}
    blood = {row['container']: liquid[row['container']] if row['material'] == 'whole_blood' else 0.0
             for row in containers}
    with (project / 'preparation/transfers.csv').open(newline='') as handle:
        transfers = sorted(csv.DictReader(handle), key=lambda row: row['recorded_at'])
    for row in transfers:
        source, destination = row['source'], row['destination']
        amount = float(row['volume_ul'])
        whole_blood = amount * blood[source] / liquid[source]
        liquid[source] -= amount
        blood[source] -= whole_blood
        liquid[destination] += amount
        blood[destination] += whole_blood
    return blood


def specimen_records(project, responses):
    blood = blood_contents(project)
    records = []
    for path in sorted((project / 'fcs').glob('*.fcs')):
        tube, channels, events = read_acquisition(path)
        masks = gate_masks(events, channels, project / 'gates.xml')
        indices = [channels.index(channel) for channel in FLUORESCENCE]
        areas = events[masks['Beads']][:, indices]
        ceiling = np.array([float(tube.text[f'p{index + 1}r']) - 1 for index in indices])
        gain, pedestal = responses[block_identity(tube, channels)]
        aliquot = tube.text['prep aliquot']
        volume = float(tube.text['sample vol']) if aliquot == 'NEAT' else blood[aliquot]
        records.append({'file': path.name, 'label': tube.text['bead lot'],
                        'volume': volume, 'cd4': int(masks['CD4pos'].sum()),
                        'areas': (areas - pedestal) / gain, 'clipped': areas >= ceiling})
    return records


def lot_profiles(records, product_window):
    dispersed = [record for record in records if np.mean(
        (record['areas'][:, 0] >= product_window[0])
        & (record['areas'][:, 0] <= product_window[1])
        & ~np.any(record['clipped'], axis=1)) > 0.96]
    logarithms = np.log(np.concatenate([record['areas'][:, 2] for record in dispersed]))
    edges = np.arange(logarithms.min() - 0.01, logarithms.max() + 0.012, 0.002)
    histogram, edges = np.histogram(logarithms, bins=edges)
    density = gaussian_filter1d(histogram.astype(float), 1.2)
    peaks, _ = find_peaks(density, prominence=density.max() * 0.015, distance=6)
    locations = (edges[peaks] + edges[peaks + 1]) / 2
    widths = np.full(len(locations), 0.008)
    weights = np.full(len(locations), 1 / len(locations))
    for iteration in range(25):
        likelihood = (-0.5 * ((logarithms[:, None] - locations) / widths) ** 2
                      - np.log(widths) + np.log(weights))
        posterior = np.exp(likelihood - logsumexp(likelihood, axis=1)[:, None])
        mass = posterior.sum(axis=0)
        locations = (posterior * logarithms[:, None]).sum(axis=0) / mass
        widths = np.sqrt((posterior * (logarithms[:, None] - locations) ** 2).sum(axis=0) / mass)
        weights = mass / len(logarithms)
    observations = []
    for record in dispersed:
        logarithms = np.log(record['areas'][:, 2])
        likelihood = (-0.5 * ((logarithms[:, None] - locations) / widths) ** 2
                      - np.log(widths) + np.log(weights))
        labels = likelihood.argmax(axis=1)
        signature = tuple(index for index in range(len(locations)) if np.mean(labels == index) > 0.08)
        observations.append((record, labels, signature))
    signatures = sorted({signature for _, _, signature in observations}, key=lambda signature: (len(signature), signature))
    atomic = []
    for signature in signatures:
        covered = set().union(*(set(part) for part in atomic if set(part) <= set(signature)))
        if covered != set(signature):
            atomic.append(signature)
    profiles = []
    for signature in atomic:
        tubes = [(record, labels) for record, labels, observed in observations if observed == signature]
        lot = Counter(record['label'] for record, _ in tubes).most_common(1)[0][0]
        means, covariances, fractions = [], [], []
        for index in signature:
            groups = [record['areas'][labels == index] for record, labels in tubes]
            means.append(np.median([group.mean(axis=0) for group in groups], axis=0))
            covariances.append(np.mean([np.cov(group, rowvar=False) for group in groups], axis=0))
            fractions.append(sum(len(group) for group in groups))
        profiles.append((lot, {'means': np.array(means), 'covariances': np.array(covariances),
                               'weights': np.array(fractions) / sum(fractions),
                               'scale_error': np.maximum(np.std([record['areas'].mean(axis=0) for record, _ in tubes], axis=0)
                                                         / np.mean([record['areas'].mean(axis=0) for record, _ in tubes], axis=0), 0.001)}))
    return profiles


def integer_compositions(total, count):
    if count == 1:
        yield (total,)
    else:
        for first in range(total + 1):
            for remaining in integer_compositions(total - first, count - 1):
                yield (first, *remaining)


def pulse_likelihood(areas, clipped, means, covariances):
    likelihood = np.zeros((len(areas), len(means)))
    for pattern in np.unique(clipped, axis=0):
        rows = np.flatnonzero(np.all(clipped == pattern, axis=1))
        observed = np.flatnonzero(~pattern)
        censored = np.flatnonzero(pattern)
        covariance = covariances[:, observed][:, :, observed]
        inverse = np.linalg.inv(covariance)
        residual = areas[rows][:, None, observed] - means[None, :, observed]
        values = -0.5 * (np.einsum('nki,kij,nkj->nk', residual, inverse, residual)
                         + np.linalg.slogdet(covariance)[1][None, :]
                         + len(observed) * np.log(2 * np.pi))
        for column in censored:
            cross = covariances[:, column, observed]
            regression = np.einsum('ki,kij->kj', cross, inverse)
            conditional_mean = means[None, :, column] + np.einsum('ki,nki->nk', regression, residual)
            conditional_variance = covariances[:, column, column] - np.einsum('ki,ki->k', regression, cross)
            values += log_ndtr((conditional_mean - areas[rows, None, column]) / np.sqrt(conditional_variance))
        likelihood[rows] = values
    return likelihood


def composition_fit(record, profiles):
    areas = record['areas']
    all_centers = np.concatenate([profile['means'] for _, profile in profiles])
    all_variances = np.concatenate([np.diagonal(profile['covariances'], axis1=1, axis2=2)
                                    for _, profile in profiles])
    single_distances = ((areas[:, None, :] - all_centers) ** 2 / all_variances).sum(axis=2).min(axis=1)
    dispersed = not np.any(record['clipped']) and np.mean(single_distances < 64) > 0.999
    choices = []
    candidates = [(index,) for index in range(len(profiles))] + list(combinations(range(len(profiles)), 2))
    for active in candidates:
        centers = np.concatenate([profiles[index][1]['means'] for index in active])
        covariance = np.concatenate([profiles[index][1]['covariances'] for index in active])
        population_weights = np.concatenate([profiles[index][1]['weights'] for index in active])
        parent = np.concatenate([np.full(len(profiles[index][1]['weights']), offset) for offset, index in enumerate(active)])
        max_order = int(np.ceil(areas[:, 1].max() / centers[:, 1].min())) + 1
        if dispersed:
            max_order = 1
        counts = np.array([composition for total in range(1, max_order + 1)
                           for composition in integer_compositions(total, len(centers))])
        orders = counts.sum(axis=1)
        means = counts @ centers
        covariances = np.einsum('kc,cij->kij', counts, covariance)
        likelihood = pulse_likelihood(areas, record['clipped'], means, covariances)
        plausible = np.any(likelihood >= likelihood.max(axis=1)[:, None] - 25, axis=0)
        likelihood, counts, orders = likelihood[:, plausible], counts[plausible], orders[plausible]
        penalty = 0.5 * np.log(len(areas)) * (len(active) - 1)
        if choices and likelihood.max(axis=1).sum() - penalty <= max(choice[0] for choice in choices):
            continue
        combinatorial = gammaln(orders + 1) - gammaln(counts + 1).sum(axis=1)
        stock_weights = np.full(len(active), 1 / len(active))
        order_weights = np.full(max_order, 1 / max_order)
        stock_counts = np.column_stack([counts[:, parent == offset].sum(axis=1) for offset in range(len(active))])
        previous = -np.inf
        for iteration in range(40):
            probabilities = population_weights * stock_weights[parent]
            prior = combinatorial + counts @ np.log(np.maximum(probabilities, 1e-12)) + np.log(np.maximum(order_weights[orders - 1], 1e-12))
            joint = likelihood + prior
            normalization = logsumexp(joint, axis=1)
            posterior = np.exp(joint - normalization[:, None])
            mass = posterior.sum(axis=0)
            order_weights = np.bincount(orders - 1, weights=mass, minlength=max_order) / len(areas)
            acquired = mass @ stock_counts
            stock_weights = acquired / acquired.sum()
            score = normalization.sum()
            if score - previous < 1e-5:
                break
            previous = score
        result = np.zeros(len(profiles))
        result[list(active)] = acquired
        choices.append((score - penalty, result, active, counts,
                        centers, covariance, parent, population_weights, order_weights, stock_weights))
    best = max(choices, key=lambda item: item[0])
    _, result, active, counts, centers, covariance, parent, population_weights, order_weights, stock_weights = best
    if len(centers) == len(active):
        return result
    orders = counts.sum(axis=1)
    max_order = len(order_weights)
    combinatorial = gammaln(orders + 1) - gammaln(counts + 1).sum(axis=1)
    stock_counts = np.column_stack([counts[:, parent == offset].sum(axis=1) for offset in range(len(active))])
    contributions = np.stack([counts[:, parent == offset] @ centers[parent == offset]
                              for offset in range(len(active))], axis=1)
    if np.all(stock_counts == stock_counts[0]):
        return result
    scale_error = np.array([profiles[index][1]['scale_error'] for index in active])
    scales = np.ones((len(active), 3))
    for outer in range(4):
        means = np.einsum('ksc,sc->kc', contributions, scales)
        component_scales = scales[parent]
        scaled_covariance = covariance * component_scales[:, :, None] * component_scales[:, None, :]
        covariances = np.einsum('kc,cij->kij', counts, scaled_covariance)
        likelihood = pulse_likelihood(areas, record['clipped'], means, covariances)
        previous = -np.inf
        for iteration in range(40):
            probabilities = population_weights * stock_weights[parent]
            prior = combinatorial + counts @ np.log(np.maximum(probabilities, 1e-12)) + np.log(np.maximum(order_weights[orders - 1], 1e-12))
            joint = likelihood + prior
            posterior = np.exp(joint - logsumexp(joint, axis=1)[:, None])
            mass = posterior.sum(axis=0)
            order_weights = np.bincount(orders - 1, weights=mass, minlength=max_order) / len(areas)
            acquired = mass @ stock_counts
            stock_weights = acquired / acquired.sum()
            score = logsumexp(joint, axis=1).sum()
            if score - previous < 1e-5:
                break
            previous = score
        if outer < 3:
            for column in range(3):
                observed = ~record['clipped'][:, column]
                weights = posterior[observed] / covariances[None, :, column, column]
                design = contributions[:, :, column]
                precision = np.diag(1 / scale_error[:, column] ** 2)
                system = design.T @ (weights.sum(axis=0)[:, None] * design) + precision
                target = design.T @ (weights * areas[observed, None, column]).sum(axis=0) + np.diag(precision)
                scales[:, column] = np.linalg.solve(system, target)
    result[list(active)] = acquired
    return result


def main(project, output):
    with (project / 'lots.csv').open(newline='') as handle:
        quantities = {row['lot']: float(row['beads_per_test']) for row in csv.DictReader(handle)}
    product = re.search(r'between\s+(\d+)\s+and\s+(\d+)\s+MESF', (project / 'kit_insert.txt').read_text())
    window = tuple(map(float, product.groups()))
    records = specimen_records(project, detector_responses(project))
    profiles = lot_profiles(records, window)
    with output.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['file', 'cd4_per_ul'])
        for record in records:
            acquired = composition_fit(record, profiles)
            reagent_fraction = sum(number / quantities[lot] for number, (lot, _) in zip(acquired, profiles))
            count = record['cd4'] / reagent_fraction / record['volume']
            writer.writerow([record['file'], format(count, '.12g')])


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))
