import {bindingKey} from '../forms/types';
import type {FormControl, FormData, Limits, OcrFillResult, OcrLine, ReadingLimit} from '../forms/types';

type LabelMatch = {label: string; distance: number};

function normalise(text: string): string {
  return text.replace(/[–—−]/g, '-').trim().replace(/\s+/g, ' ');
}

function labelKey(text: string): string {
  const clean = normalise(text).toLowerCase()
    .replace(/fi1ament/g, 'filament')
    .replace(/pressure/g, 'pres')
    .replace(/temperature/g, 'temp');
  let compact = clean.replace(/[^a-z0-9+./]/g, '');
  if (clean.startsWith('-')) compact = '-' + compact;
  compact = compact.replace('highvoltagemodulation', 'hvmodulation');
  if (compact === 'tubefilamentcurrent' || compact === 'xraytubefilamentcurrent') compact = 'xraytubefilament';
  return compact;
}

function editDistance(first: string, second: string): number {
  let previous = Array.from({length: second.length + 1}, (_, index) => index);
  for (let row = 1; row <= first.length; row++) {
    const current = [row];
    for (let column = 1; column <= second.length; column++) {
      current.push(Math.min(
        current[column - 1] + 1,
        previous[column] + 1,
        previous[column - 1] + Number(first[row - 1] !== second[column - 1]),
      ));
    }
    previous = current;
  }
  return previous[second.length];
}

function identify(text: string, labels: string[]): LabelMatch | undefined {
  const key = labelKey(text);
  let best: LabelMatch | undefined;
  for (const label of labels) {
    const candidate = labelKey(label);
    const sign = key.match(/^[+-]/)?.[0] ?? '';
    const candidateSign = candidate.match(/^[+-]/)?.[0] ?? '';
    if (sign !== candidateSign) continue;
    if (key.includes('anode') && !candidate.includes('anode')) continue;
    if (key.includes('cathode') && !candidate.includes('cathode')) continue;
    const distance = editDistance(key, candidate) / Math.max(key.length, candidate.length, 1);
    if (distance <= 0.23 && (!best || distance < best.distance)) best = {label, distance};
  }
  return best;
}

function median(values: number[]): number {
  const ordered = [...values].sort((first, second) => first - second);
  return ordered[Math.floor(ordered.length / 2)] ?? 0;
}

type ScreenFit = {parameters: number[]; width: number; height: number; twoColumn: boolean; error: number};
type ScreenAnchor = {line: OcrLine; channel: number};

function solveSystem(matrix: number[][], vector: number[]): number[] | undefined {
  const augmented = matrix.map((row, index) => [...row, vector[index]]);
  for (let column = 0; column < vector.length; column++) {
    let pivot = column;
    for (let row = column + 1; row < vector.length; row++) {
      if (Math.abs(augmented[row][column]) > Math.abs(augmented[pivot][column])) pivot = row;
    }
    if (Math.abs(augmented[pivot][column]) < 1e-12) return undefined;
    [augmented[column], augmented[pivot]] = [augmented[pivot], augmented[column]];
    const divisor = augmented[column][column];
    augmented[column] = augmented[column].map(value => value / divisor);
    for (let row = 0; row < vector.length; row++) {
      if (row === column) continue;
      const factor = augmented[row][column];
      augmented[row] = augmented[row].map((value, index) => value - factor * augmented[column][index]);
    }
  }
  return augmented.map(row => row[vector.length]);
}

function screenPoint(horizontal: number, vertical: number, fit: ScreenFit): number[] {
  const [originLeft, originTop, scale, tilt, horizontalPerspective, verticalPerspective] = fit.parameters;
  const denominator = 1 + horizontalPerspective * horizontal / fit.width + verticalPerspective * vertical / fit.height;
  if (fit.parameters.length > 6) {
    const angle = fit.parameters[6];
    const horizontalImage = scale * horizontal / denominator;
    const verticalImage = scale * (vertical + tilt * horizontal) / denominator;
    return [originLeft + Math.cos(angle) * horizontalImage - Math.sin(angle) * verticalImage,
      originTop + Math.sin(angle) * horizontalImage + Math.cos(angle) * verticalImage];
  }
  return [originLeft + scale * horizontal / denominator, originTop + scale * (vertical + tilt * horizontal) / denominator];
}

function screenBounds(horizontal: number, vertical: number, width: number, fit: ScreenFit): number[] {
  const corners = [screenPoint(horizontal, vertical - 8, fit), screenPoint(horizontal, vertical + 8, fit),
    screenPoint(horizontal + width, vertical - 8, fit), screenPoint(horizontal + width, vertical + 8, fit)];
  const left = Math.min(...corners.map(point => point[0]));
  const top = Math.min(...corners.map(point => point[1]));
  return [left, top, Math.max(...corners.map(point => point[0])) - left, Math.max(...corners.map(point => point[1])) - top];
}

function refineScreen(initial: ScreenFit, anchors: ScreenAnchor[]): ScreenFit {
  const residuals = (fit: ScreenFit) => anchors.flatMap(anchor => {
    const horizontal = fit.twoColumn && anchor.channel >= 8 ? 650 : 0;
    const vertical = (fit.twoColumn ? anchor.channel % 8 : anchor.channel) * 32;
    const expected = screenBounds(horizontal, vertical, anchor.line.text.length * 7.1, fit);
    const box = anchor.line.boundingBox;
    return expected.map((value, index) => value - [box.left, box.top, box.width, box.height][index]);
  });
  let fit = initial;
  let residual = residuals(fit);
  fit.error = residual.reduce((sum, value) => sum + value * value, 0);
  let damping = 0.001;
  const increments = [0.001, 0.001, 0.00001, 0.000001, 0.000001, 0.000001, 0.000001];
  for (let iteration = 0; iteration < (fit.parameters.length > 6 ? 85 : 70); iteration++) {
    const derivatives = fit.parameters.map((_, parameter) => {
      const parameters = [...fit.parameters];
      parameters[parameter] += increments[parameter];
      return residuals({...fit, parameters}).map((value, index) => (value - residual[index]) / increments[parameter]);
    });
    const matrix = derivatives.map(first => derivatives.map(second => first.reduce((sum, value, index) => sum + value * second[index], 0)));
    const vector = derivatives.map(derivative => -derivative.reduce((sum, value, index) => sum + value * residual[index], 0));
    for (let diagonal = 0; diagonal < matrix.length; diagonal++) matrix[diagonal][diagonal] += damping * (matrix[diagonal][diagonal] + 1);
    const step = solveSystem(matrix, vector);
    if (!step) break;
    const parameters = fit.parameters.map((value, index) => value + step[index]);
    const proposal = {...fit, parameters};
    if (parameters[2] <= 0.3 || parameters[2] > 3 || Math.abs(parameters[4]) > 0.5 || Math.abs(parameters[5]) > 0.5
      || Math.abs(parameters[6] ?? 0) > 1.2) {
      damping *= 8;
      continue;
    }
    const nextResidual = residuals(proposal);
    const error = nextResidual.reduce((sum, value) => sum + value * value, 0);
    if (Number.isFinite(error) && error < fit.error) {
      const improvement = fit.error - error;
      fit = {...proposal, error};
      residual = nextResidual;
      damping = Math.max(1e-9, damping / 4);
      if (improvement < 1e-8) break;
    } else damping *= 8;
  }
  return fit;
}

function fitRolledScreen(anchors: ScreenAnchor[]): ScreenFit | undefined {
  let best: ScreenFit | undefined;
  for (const twoColumn of [false, true]) {
    const width = twoColumn ? 1200 : 500;
    const height = twoColumn ? 256 : 512;
    const positions = anchors.map(anchor => [
      ((twoColumn && anchor.channel >= 8 ? 650 : 0) + anchor.line.text.length * 7.1 / 2) / width,
      (twoColumn ? anchor.channel % 8 : anchor.channel) * 32 / height, 1,
    ]);
    const matrix = [0, 1, 2].map(first => [0, 1, 2].map(second => positions.reduce(
      (sum, position) => sum + position[first] * position[second], 0)));
    const affine = [0, 1].map(axis => solveSystem(matrix, [0, 1, 2].map(column => anchors.reduce((sum, anchor, index) => {
      const box = anchor.line.boundingBox;
      const coordinate = axis === 0 ? box.left + box.width / 2 : box.top + box.height / 2;
      return sum + positions[index][column] * coordinate;
    }, 0))));
    const [horizontal, vertical] = affine;
    if (!horizontal || !vertical) continue;
    const angle = Math.atan2(-horizontal[1] / height, vertical[1] / height);
    const scale = Math.hypot(horizontal[1], vertical[1]) / height;
    const tilt = (-Math.sin(angle) * horizontal[0] + Math.cos(angle) * vertical[0]) / (width * scale);
    for (const horizontalPerspective of [-0.16, 0, 0.16]) {
      for (const verticalPerspective of [-0.12, 0, 0.12]) {
        const parameters = [horizontal[2], vertical[2], scale, tilt, horizontalPerspective, verticalPerspective, angle];
        const fit = refineScreen({parameters, width, height, twoColumn, error: Infinity}, anchors);
        if (!best || fit.error < best.error) best = fit;
      }
    }
  }
  if (!best || best.error / (anchors.length * 4) > 9) {
    for (const twoColumn of [false, true]) {
      const width = twoColumn ? 1200 : 500;
      const height = twoColumn ? 256 : 512;
      for (const angle of [-Math.PI / 6, 0, Math.PI / 6]) {
        for (const horizontalPerspective of [-0.16, 0, 0.16]) {
          for (const verticalPerspective of [-0.12, 0, 0.12]) {
            const seed: ScreenFit = {parameters: [0, 0, 1, 0, horizontalPerspective, verticalPerspective, angle],
              width, height, twoColumn, error: Infinity};
            const rectangle = (anchor: ScreenAnchor) => screenBounds(twoColumn && anchor.channel >= 8 ? 650 : 0,
              (twoColumn ? anchor.channel % 8 : anchor.channel) * 32, anchor.line.text.length * 7.1, seed);
            seed.parameters[2] = median(anchors.map(anchor => anchor.line.boundingBox.width / rectangle(anchor)[2]));
            const offsets = anchors.map(anchor => {
              const bounds = rectangle(anchor);
              return [anchor.line.boundingBox.left - bounds[0], anchor.line.boundingBox.top - bounds[1]];
            });
            seed.parameters[0] = median(offsets.map(offset => offset[0]));
            seed.parameters[1] = median(offsets.map(offset => offset[1]));
            const fit = refineScreen(seed, anchors);
            if (!best || fit.error < best.error) best = fit;
          }
        }
      }
    }
  }
  return best;
}

function rectifyScreen(lines: OcrLine[], labels: string[]): {lines: OcrLine[]; twoColumn: boolean} | undefined {
  const anchors = lines.flatMap(line => {
    const identity = identify(line.text, labels);
    if (!identity || labelKey(line.text) !== labelKey(identity.label)) return [];
    return [{line, channel: labels.indexOf(identity.label)}];
  });
  if (anchors.length < 3) return undefined;
  let best: ScreenFit | undefined;
  for (const twoColumn of [false, true]) {
    const width = twoColumn ? 1200 : 500;
    const height = twoColumn ? 256 : 512;
    const initialScale = median(anchors.map(anchor => anchor.line.boundingBox.width / (anchor.line.text.length * 7.1)));
    const originLeft = median(anchors.map(anchor => anchor.line.boundingBox.left - (twoColumn && anchor.channel >= 8 ? 650 : 0) * initialScale));
    const originTop = median(anchors.map(anchor => anchor.line.boundingBox.top + anchor.line.boundingBox.height / 2
      - (twoColumn ? anchor.channel % 8 : anchor.channel) * 32 * initialScale));

    const starts = [-0.05, 0, 0.05].map(tilt => [originLeft, originTop, initialScale, tilt, 0, 0]);
    if (!twoColumn) {
      const observations = anchors.map(anchor => ({
        coordinates: [1, anchor.line.text.length * 7.1 / width, anchor.channel * 32 / height],
        ratio: anchor.line.text.length * 7.1 / anchor.line.boundingBox.width,
      }));
      const matrix = [0, 1, 2].map(first => [0, 1, 2].map(second => observations.reduce(
        (sum, observation) => sum + observation.coordinates[first] * observation.coordinates[second], 0)));
      const vector = [0, 1, 2].map(index => observations.reduce(
        (sum, observation) => sum + observation.coordinates[index] * observation.ratio, 0));
      const estimate = solveSystem(matrix, vector);
      if (estimate) {
        const scale = 1 / (estimate[0] + Math.abs(estimate[2]) * 8 / height);
        const horizontalPerspective = estimate[1] * scale;
        const verticalPerspective = estimate[2] * scale;
        if (scale > 0.3 && scale <= 3 && Math.abs(horizontalPerspective) <= 0.5 && Math.abs(verticalPerspective) <= 0.5
          && (Math.abs(horizontalPerspective) >= 0.04 || Math.abs(verticalPerspective) >= 0.04)) {
          for (const tilt of [-0.05, 0, 0.05]) {
            const seed: ScreenFit = {parameters: [originLeft, 0, scale, tilt, horizontalPerspective, verticalPerspective],
              width, height, twoColumn, error: Infinity};
            seed.parameters[1] = median(anchors.map(anchor => anchor.line.boundingBox.top
              - screenBounds(0, anchor.channel * 32, anchor.line.text.length * 7.1, seed)[1]));
            starts.push(seed.parameters);
          }
        }
      }
    }
    for (const initialParameters of starts) {
      const fit = refineScreen({parameters: initialParameters, width, height, twoColumn, error: Infinity}, anchors);
      if (!best || fit.error < best.error) best = fit;
    }
  }
  if (!best || best.error / (anchors.length * 4) > 9) best = fitRolledScreen(anchors);
  if (!best || best.error / (anchors.length * 4) > 9) return undefined;
  if (Math.abs(best.parameters[4]) < 0.04 && Math.abs(best.parameters[5]) < 0.04 && Math.abs(best.parameters[6] ?? 0) < 0.04) return undefined;
  const fit = best;
  const rowHeight = (row: number, horizontal: number) => {
    const start = screenPoint(0, row * 32, fit);
    const end = screenPoint(fit.width, row * 32, fit);
    return start[1] + (end[1] - start[1]) * (horizontal - start[0]) / (end[0] - start[0]);
  };
  const physicalHorizontal = (imageHorizontal: number, physicalVertical: number) => {
    const [originLeft, , scale, tilt, horizontalPerspective, verticalPerspective] = fit.parameters;
    const offset = imageHorizontal - originLeft;
    if (fit.parameters.length > 6) {
      const angle = fit.parameters[6];
      return (offset * (1 + verticalPerspective * physicalVertical / fit.height) + scale * Math.sin(angle) * physicalVertical)
        / (scale * (Math.cos(angle) - tilt * Math.sin(angle)) - offset * horizontalPerspective / fit.width);
    }
    return offset * (1 + verticalPerspective * physicalVertical / fit.height) / (scale - offset * horizontalPerspective / fit.width);
  };
  return {twoColumn: fit.twoColumn, lines: lines.map(line => {
    const box = line.boundingBox;
    const centreLeft = box.left + box.width / 2;
    const centreTop = box.top + box.height / 2;
    const distances = Array.from({length: fit.twoColumn ? 8 : 16}, (_, row) => Math.abs(centreTop - rowHeight(row, centreLeft)));
    const row = distances.indexOf(Math.min(...distances));
    const side = Math.sign(fit.parameters[5]);
    const left = fit.parameters.length > 6
      ? Math.max(...[-8, 8].map(edge => physicalHorizontal(box.left, row * 32 + edge)))
      : physicalHorizontal(box.left, row * 32 + side * 8);
    const right = fit.parameters.length > 6
      ? Math.min(...[-8, 8].map(edge => physicalHorizontal(box.left + box.width, row * 32 + edge)))
      : physicalHorizontal(box.left + box.width, row * 32 - side * 8);
    return {text: line.text, boundingBox: {left, top: row * 32 - 8, width: right - left, height: 16}};
  })};
}

function recogniseRows(lines: OcrLine[], limits: Limits): Map<string, string> {
  const labels = Object.keys(limits);
  const rectified = rectifyScreen(lines, labels);
  lines = rectified?.lines ?? lines;
  const scale = rectified ? 1 : median(lines.filter(line => line.text.length >= 3).map(line => line.boundingBox.width / line.text.length / 7.1));
  const magnitude = Math.max(0, median(lines.map(line => (line.boundingBox.height - 16 * scale) / line.boundingBox.width)));
  const ordinate = (line: OcrLine, slope: number) => line.boundingBox.top + line.boundingBox.height / 2
    - slope * (line.boundingBox.left + line.boundingBox.width / 2);
  const concentration = (slope: number) => {
    const angles = lines.map(line => ordinate(line, slope) * 2 * Math.PI / (32 * scale));
    return Math.hypot(angles.reduce((sum, angle) => sum + Math.cos(angle), 0), angles.reduce((sum, angle) => sum + Math.sin(angle), 0));
  };
  const slope = rectified ? 0 : concentration(magnitude) >= concentration(-magnitude) ? magnitude : -magnitude;
  const result = new Map<string, string>();
  const rows: {ordinate: number; lines: OcrLine[]}[] = [];
  for (const line of [...lines].sort((first, second) => ordinate(first, slope) - ordinate(second, slope))) {
    const vertical = ordinate(line, slope);
    const row = rows.find(candidate => Math.abs(candidate.ordinate - vertical) < 9 * scale);
    if (row) row.lines.push(line);
    else rows.push({ordinate: vertical, lines: [line]});
  }
  type Parsed = {readings: {label: string; raw: string}[]; cost: number};
  const cache = new Map<string, Parsed | undefined>();
  const parse = (text: string, candidates: string[]): Parsed | undefined => {
    if (!text) return {readings: [], cost: 0};
    const cacheKey = candidates.join('\0') + '\0' + text;
    if (cache.has(cacheKey)) return cache.get(cacheKey);
    let best: Parsed | undefined;
    for (let cut = 1; cut < text.length; cut++) {
      if (text[cut] !== ' ') continue;
      const prefix = text.slice(0, cut);
      let identity = identify(prefix, candidates);
      if (!identity && rectified) {
        const signless = candidates.filter(label => /^[+-](?:12|24)vsupply$/.test(labelKey(label))
          && labelKey(prefix) === labelKey(label).slice(1));
        if (signless.length === 1) identity = {label: signless[0], distance: 0};
      }
      if (!identity) continue;
      const limit = limits[identity.label];
      const number = 'format' in limit ? '[0-9B]{4}' : '[+-]?[0-9B]+(?:\\.[0-9B]+)?';
      const suffix = 'min' in limit && limit.unit ? '\\s+' + limit.unit : '';
      const match = new RegExp('^(' + number + suffix + ')(?:\\s+|$)').exec(text.slice(cut + 1));
      if (!match) continue;
      const remaining = parse(text.slice(cut + 1 + match[0].length), candidates);
      if (!remaining || remaining.readings.some(reading => reading.label === identity.label)) continue;
      const proposal = {readings: [{label: identity.label, raw: match[1]}, ...remaining.readings], cost: identity.distance + remaining.cost};
      if (!best || proposal.cost < best.cost) best = proposal;
    }
    cache.set(cacheKey, best);
    return best;
  };
  for (const row of rows) {
    const pieces = row.lines.sort((first, second) => first.boundingBox.left - second.boundingBox.left);
    let text = '';
    for (let index = 0; index < pieces.length; index++) {
      const piece = pieces[index];
      const previous = pieces[index - 1];
      const gap = previous ? piece.boundingBox.left - previous.boundingBox.left - previous.boundingBox.width : 0;
      if (text && !/\s$/.test(text) && !/^\s/.test(piece.text) && gap > 3.5 * scale) text += ' ';
      text += piece.text;
    }
    const physicalRow = Math.round(row.ordinate / 32);
    const candidates = rectified
      ? [labels[physicalRow], ...(rectified.twoColumn ? [labels[physicalRow + 8]] : [])].filter(Boolean)
      : labels;
    const parsed = parse(normalise(text), candidates);
    for (const reading of parsed?.readings ?? []) result.set(reading.label, reading.raw);
  }
  return result;
}

function withinLimits(text: string, limit: ReadingLimit): boolean {
  const value = normalise(text);
  if ('format' in limit) return new RegExp(limit.format).test(value);
  const match = /^([+-]?(?:\d+(?:\.\d+)?|\.\d+))(?:\s+(\S+))?$/.exec(value);
  if (!match || (match[2] ?? '') !== limit.unit) return false;
  const numeric = Number(match[1]);
  return numeric >= limit.min && numeric <= limit.max;
}

function recover(raw: string, limit: ReadingLimit): string {
  const text = normalise(raw);
  if (withinLimits(text, limit)) return text;
  const alternatives = new Set<string>();
  function visit(index: number, prefix: string) {
    if (index === text.length) {
      if (withinLimits(prefix, limit)) alternatives.add(prefix);
      if ('min' in limit) {
        const restored = (limit.max < 0 ? '-' : '') + prefix.replace(/^[+-]/, '');
        if (withinLimits(restored, limit)) alternatives.add(restored);
      }
      return;
    }
    visit(index + 1, prefix + text[index]);
    if (/[89B]/.test(text[index])) visit(index + 1, prefix + '0');
  }
  visit(0, '');
  return alternatives.size === 1 ? [...alternatives][0] : text;
}

export function fillFormFromOcr(
  form: FormControl[],
  formData: FormData,
  ocrResult: OcrLine[],
  limits: Limits,
): OcrFillResult {
  const result = {...formData};
  const warnings = new Set<string>();
  const rows = recogniseRows(ocrResult, limits);
  let cameraFound = false;
  for (const field of form) {
    if (field.Control === 'OCRCamera') {
      cameraFound = true;
      continue;
    }
    if (!cameraFound || field.Control !== 'SmartText') continue;
    const identity = identify(field.Label, Object.keys(limits));
    if (!identity) continue;
    const raw = rows.get(identity.label);
    if (raw === undefined) continue;
    const limit = limits[identity.label];
    const value = recover(raw, limit);
    const key = bindingKey(field.Binding);
    result[key] = value;
    if (normalise(value) !== normalise(raw) || !withinLimits(value, limit)) warnings.add(key);
  }
  return {formData: result, warnings: [...warnings]};
}
