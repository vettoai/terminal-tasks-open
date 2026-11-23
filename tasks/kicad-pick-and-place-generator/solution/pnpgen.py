#!/usr/bin/env python3
"""Generate body-datum assembly positions from KiCad board geometry."""

import csv
import json
import math
import re
import sys
from decimal import Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction
from pathlib import Path
from terminal import copper_centroid


def parse(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[^\s()]+|[()]', text)
    stack = [[]]
    for token in tokens:
        if token == '(':
            child = []
            stack[-1].append(child)
            stack.append(child)
        elif token == ')':
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    return stack[0][0]


def children(node, name):
    return [item for item in node if isinstance(item, list) and item and item[0] == name]


def first(node, name):
    return next(iter(children(node, name)), None)


def pair(node):
    return float(node[1]), float(node[2])


def arc_geometry(points):
    (start_x, start_y), (mid_x, mid_y), (end_x, end_y) = points
    determinant = 2 * (start_x * (mid_y - end_y) + mid_x * (end_y - start_y) + end_x * (start_y - mid_y))
    start_norm, mid_norm, end_norm = [point_x * point_x + point_y * point_y for point_x, point_y in points]
    centre_x = (start_norm * (mid_y - end_y) + mid_norm * (end_y - start_y) + end_norm * (start_y - mid_y)) / determinant
    centre_y = (start_norm * (end_x - mid_x) + mid_norm * (start_x - end_x) + end_norm * (mid_x - start_x)) / determinant
    angles = [math.atan2(point_y - centre_y, point_x - centre_x) for point_x, point_y in points]
    sweep = (angles[2] - angles[0]) % math.tau
    if (angles[1] - angles[0]) % math.tau > sweep:
        sweep -= math.tau
    return centre_x, centre_y, math.hypot(start_x - centre_x, start_y - centre_y), angles[0], sweep


def straight_boundaries(primitives):
    strokes = []
    for primitive in primitives:
        kind = primitive[0][3:]
        def coordinate(node):
            return tuple(Fraction(value) for value in node[1:3])
        if kind == 'line':
            strokes.append((coordinate(first(primitive, 'start')), coordinate(first(primitive, 'end'))))
        else:
            if kind == 'rect':
                (left, top), (right, lower) = coordinate(first(primitive, 'start')), coordinate(first(primitive, 'end'))
                vertices = [(left, top), (right, top), (right, lower), (left, lower)]
            else:
                vertices = [coordinate(point) for point in children(first(primitive, 'pts'), 'xy')]
            strokes.extend(zip(vertices, vertices[1:] + vertices[:1]))
    def vector(first_point, second_point):
        return second_point[0] - first_point[0], second_point[1] - first_point[1]
    def determinant(first_vector, second_vector):
        return first_vector[0] * second_vector[1] - first_vector[1] * second_vector[0]
    splits = [set(stroke) for stroke in strokes]
    for index, (start, end) in enumerate(strokes):
        direction = vector(start, end)
        for other_index, (other_start, other_end) in enumerate(strokes[:index]):
            other_direction = vector(other_start, other_end)
            offset = vector(start, other_start)
            divisor = determinant(direction, other_direction)
            if divisor:
                position = determinant(offset, other_direction) / divisor
                other_position = determinant(offset, direction) / divisor
                if 0 <= position <= 1 and 0 <= other_position <= 1:
                    intersection = tuple(start[axis] + position * direction[axis] for axis in (0, 1))
                    splits[index].add(intersection)
                    splits[other_index].add(intersection)
            elif determinant(offset, direction) == 0:
                for point in (start, end, other_start, other_end):
                    if all(min(start[axis], end[axis]) <= point[axis] <= max(start[axis], end[axis])
                           and min(other_start[axis], other_end[axis]) <= point[axis] <= max(other_start[axis], other_end[axis])
                           for axis in (0, 1)):
                        splits[index].add(point)
                        splits[other_index].add(point)
    edges = set()
    for points in splits:
        ordered = sorted(points)
        edges.update(zip(ordered, ordered[1:]))
    adjacent = {}
    for start, end in edges:
        adjacent.setdefault(start, set()).add(end)
        adjacent.setdefault(end, set()).add(start)
    discovery, low, bridges = {}, {}, set()
    def traverse(vertex, parent=None):
        discovery[vertex] = low[vertex] = len(discovery)
        for other in adjacent[vertex]:
            if other == parent:
                continue
            if other not in discovery:
                traverse(other, vertex)
                low[vertex] = min(low[vertex], low[other])
                if low[other] > discovery[vertex]:
                    bridges.add(tuple(sorted((vertex, other))))
            else:
                low[vertex] = min(low[vertex], discovery[other])
    for vertex in adjacent:
        if vertex not in discovery:
            traverse(vertex)
    for start, end in bridges:
        adjacent[start].remove(end)
        adjacent[end].remove(start)
    ordered_neighbours = {vertex: sorted(others, key=lambda other: math.atan2(float(other[1] - vertex[1]), float(other[0] - vertex[0])))
                          for vertex, others in adjacent.items()}
    pending = {(start, end) for start, others in adjacent.items() for end in others}
    boundaries = []
    while pending:
        initial = min(pending)
        start, end = initial
        polygon = []
        while True:
            pending.remove((start, end))
            polygon.append(start)
            neighbours = ordered_neighbours[end]
            following = neighbours[(neighbours.index(start) - 1) % len(neighbours)]
            start, end = end, following
            if (start, end) == initial:
                break
        area = sum(determinant(point, polygon[(index + 1) % len(polygon)]) for index, point in enumerate(polygon))
        if area < 0:
            boundaries.append([('line', [point, polygon[(index + 1) % len(polygon)]]) for index, point in enumerate(polygon)])
    return boundaries


def fabrication_contours(footprint, layer):
    primitives = [primitive for primitive in footprint if isinstance(primitive, list)
                  and primitive[0] in ('fp_line', 'fp_arc', 'fp_circle', 'fp_rect', 'fp_poly')
                  and first(primitive, 'layer')[1] == layer]
    if not any(primitive[0] in ('fp_arc', 'fp_circle') for primitive in primitives):
        return straight_boundaries(primitives)
    closed, segments = [], []
    for primitive in footprint:
        if not isinstance(primitive, list) or primitive[0] not in ('fp_line', 'fp_arc', 'fp_circle', 'fp_rect', 'fp_poly'):
            continue
        if first(primitive, 'layer')[1] != layer:
            continue
        kind = primitive[0][3:]
        if kind == 'circle':
            closed.append([('circle', [pair(first(primitive, 'center')), pair(first(primitive, 'end'))])])
        elif kind in ('rect', 'poly'):
            if kind == 'rect':
                (left, top), (right, bottom) = pair(first(primitive, 'start')), pair(first(primitive, 'end'))
                vertices = [(left, top), (right, top), (right, bottom), (left, bottom)]
            else:
                vertices = [pair(point) for point in children(first(primitive, 'pts'), 'xy')]
            closed.append([('line', [vertex, vertices[(index + 1) % len(vertices)]])
                           for index, vertex in enumerate(vertices)])
        else:
            names = ('start', 'mid', 'end') if kind == 'arc' else ('start', 'end')
            segments.append((kind, [pair(first(primitive, name)) for name in names]))
    adjacency = {}
    ends = []
    for index, (_, points) in enumerate(segments):
        vertices = [tuple(round(value, 7) for value in point) for point in (points[0], points[-1])]
        ends.append(vertices)
        for vertex in vertices:
            adjacency.setdefault(vertex, []).append(index)
    visited, low, bridges = {}, {}, set()

    def visit(vertex, parent_edge=None):
        visited[vertex] = low[vertex] = len(visited)
        for edge in adjacency[vertex]:
            if edge == parent_edge:
                continue
            other = ends[edge][1] if ends[edge][0] == vertex else ends[edge][0]
            if other not in visited:
                visit(other, edge)
                low[vertex] = min(low[vertex], low[other])
                if low[other] > visited[vertex]:
                    bridges.add(edge)
            else:
                low[vertex] = min(low[vertex], visited[other])

    for vertex in adjacency:
        if vertex not in visited:
            visit(vertex)
    unused = set(range(len(segments))) - bridges
    while unused:
        edge = min(unused)
        start = vertex = ends[edge][0]
        loop = []
        while True:
            kind, points = segments[edge]
            reverse = ends[edge][0] != vertex
            loop.append((kind, list(reversed(points)) if reverse else points))
            unused.remove(edge)
            vertex = ends[edge][0 if reverse else 1]
            if vertex == start:
                break
            edge = next(candidate for candidate in adjacency[vertex] if candidate in unused)
        closed.append(loop)
    return closed


def curve_envelope(loop):
    points = []
    for kind, vertices in loop:
        if kind == 'circle':
            (centre_x, centre_y), endpoint = vertices
            radius = math.dist(vertices[0], endpoint)
            points.extend([(centre_x - radius, centre_y - radius), (centre_x + radius, centre_y + radius)])
        elif kind == 'line':
            points.extend(vertices)
        else:
            centre_x, centre_y, radius, start, sweep = arc_geometry(vertices)
            points.extend((vertices[0], vertices[-1]))
            for angle in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                distance = (angle - start) % math.tau if sweep > 0 else (start - angle) % math.tau
                if distance <= abs(sweep) + 1e-10:
                    points.append((centre_x + radius * math.cos(angle), centre_y + radius * math.sin(angle)))
    return points


def encloses(loop, point):
    if loop[0][0] == 'circle':
        centre, endpoint = loop[0][1]
        return math.dist(centre, point) < math.dist(centre, endpoint)
    polygon = []
    for kind, vertices in loop:
        if kind == 'line':
            polygon.append(vertices[0])
        else:
            centre_x, centre_y, radius, start, sweep = arc_geometry(vertices)
            step = min(math.pi / 16, 2 * math.acos(max(-1, 1 - 0.002 / radius)))
            count = max(2, math.ceil(abs(sweep) / step))
            polygon.extend((centre_x + radius * math.cos(start + sweep * index / count),
                            centre_y + radius * math.sin(start + sweep * index / count)) for index in range(count))
    point_x, point_y = point
    contained = False
    for index, (first_x, first_y) in enumerate(polygon):
        second_x, second_y = polygon[(index + 1) % len(polygon)]
        if (first_y > point_y) != (second_y > point_y):
            crossing_x = first_x + (point_y - first_y) * (second_x - first_x) / (second_y - first_y)
            if crossing_x > point_x:
                contained = not contained
    return contained


def centre(footprint, bottom):
    layer = 'B.Fab' if bottom else 'F.Fab'
    loops = fabrication_contours(footprint, layer)
    exterior = []
    for index, loop in enumerate(loops):
        kind, vertices = loop[0]
        sample = vertices[1] if kind == 'circle' else vertices[0]
        if not any(encloses(other, sample) for other_index, other in enumerate(loops) if other_index != index):
            exterior.append(loop)
    if len(exterior) > 1:
        raise ValueError('Separate fabrication bodies need review')
    envelope = curve_envelope(exterior[0]) if exterior else []
    pads = [(pad[1], pair(first(pad, 'at'))) for pad in children(footprint, 'pad') if pad[1]]
    points = envelope or [position for _, position in pads]
    if not points:
        raise ValueError('No body datum')
    mid_x = (min(point[0] for point in points) + max(point[0] for point in points)) / 2
    mid_y = (min(point[1] for point in points) + max(point[1] for point in points)) / 2
    if not envelope:
        remaining = list(points)
        for point_x, point_y in points:
            reflected = (2 * mid_x - point_x, 2 * mid_y - point_y)
            match = next((index for index, point in enumerate(remaining)
                          if math.dist(point, reflected) < 0.05), None)
            if match is None:
                raise ValueError('Electrical pad centres do not establish a symmetric body datum')
            remaining.pop(match)
    nominal = (Decimal(str(float(mid_x))), Decimal(str(float(mid_y))))
    if envelope and isinstance(points[0][0], Fraction):
        with localcontext() as context:
            context.prec = 80
            nominal = tuple(Decimal(value.numerator) / value.denominator for value in (mid_x, mid_y))
    elif not exterior or all(kind == 'line' for kind, _ in exterior[0]):
        dimensions = [{}, {}]
        nodes = list(children(footprint, 'pad')) if not exterior else [
            primitive for primitive in footprint if isinstance(primitive, list)
            and primitive[0] in ('fp_line', 'fp_rect', 'fp_poly')
            and first(primitive, 'layer')[1] == layer]
        for node in nodes:
            if node[0] == 'pad':
                vertices = [first(node, 'at')] if node[1] else []
            elif node[0] == 'fp_poly':
                vertices = list(children(first(node, 'pts'), 'xy'))
            else:
                vertices = [first(node, 'start'), first(node, 'end')]
            for vertex in vertices:
                for axis in (0, 1):
                    dimensions[axis][float(vertex[axis + 1])] = Decimal(vertex[axis + 1])
        nominal = []
        for axis in (0, 1):
            lower = min(point[axis] for point in points)
            upper = max(point[axis] for point in points)
            nominal.append((dimensions[axis][lower] + dimensions[axis][upper]) / 2)
    return (float(mid_x), float(mid_y)), pads, nominal


def nominal_position(at, body, origin, bottom):
    with localcontext() as context:
        context.prec = 80
        angle = Decimal(at[3]) % 360 if len(at) > 3 else Decimal(0)
        if angle < 0:
            angle += 360
        quadrant, remainder = divmod(angle, 90)
        half = Decimal('0.5')
        if remainder == 0:
            cosine, sine = Decimal(1), Decimal(0)
        elif remainder == 30:
            cosine, sine = Decimal(3).sqrt() / 2, half
        elif remainder == 45:
            cosine = sine = Decimal(2).sqrt() / 2
        elif remainder == 60:
            cosine, sine = half, Decimal(3).sqrt() / 2
        else:
            radians = remainder * Decimal('3.141592653589793238462643383279502884197169399375105820974944592307816406286208998628') / 180
            cosine, sine = Decimal(1), radians
            cosine_term, sine_term = cosine, sine
            for index in range(1, 100):
                cosine_term *= -radians * radians / ((2 * index - 1) * 2 * index)
                sine_term *= -radians * radians / (2 * index * (2 * index + 1))
                cosine += cosine_term
                sine += sine_term
        for _ in range(int(quadrant)):
            cosine, sine = -sine, cosine
        delta_x = Decimal(at[1]) - origin[0]
        delta_y = origin[1] - Decimal(at[2])
        offset_x = body[0] * cosine + body[1] * sine
        offset_y = body[0] * sine - body[1] * cosine
        position_x = delta_x + offset_x
        position_y = delta_y + offset_y
        return (-position_x if bottom else position_x), position_y


def placement(footprint, origin, tape, profile):
    bottom = first(footprint, 'layer')[1] == 'B.Cu'
    package = footprint[1].split(':')[-1]
    if package not in tape:
        raise ValueError('tape: Package missing from reel table')
    reel = tape[package]
    try:
        body, pads, nominal = centre(footprint, bottom)
    except ValueError as error:
        raise ValueError('body: ' + str(error)) from error
    at = first(footprint, 'at')
    theta = float(at[3]) if len(at) > 3 else 0.0
    cosine, sine = math.cos(math.radians(theta)), math.sin(math.radians(theta))
    output_x, output_y = nominal_position(at, nominal, origin, bottom)
    orient = -theta if bottom else theta
    if reel['polar'] == 'N':
        rotation = orient % 180
    else:
        from outline import footprint_contours
        pin = copper_centroid(footprint, theta, footprint_contours(profile, footprint))
        if pin is None:
            raise ValueError('pin1: No pin-one lands')
        offset_x = pin[0] - body[0]
        offset_y = pin[1] - body[1]
        if math.hypot(offset_x, offset_y) < 0.05:
            raise ValueError('pin1: Pin-one group is at body centre')
        direction_x = (offset_x * cosine + offset_y * sine) * (-1 if bottom else 1)
        direction_y = offset_x * sine - offset_y * cosine
        direction = math.degrees(math.atan2(direction_y, direction_x)) - orient
        octant = math.floor(direction / 45 + 0.5) % 8
        tape_octant = {'R': 0, 'TR': 1, 'T': 2, 'TL': 3,
                       'L': 4, 'BL': 5, 'B': 6, 'BR': 7}[reel['pin1_pos']]
        if octant % 2 != tape_octant % 2:
            raise ValueError('pin1: Pin-one side and reel presentation class disagree')
        rotation = (orient + octant * 45 - tape_octant * 45) % 360
    return ['bottom' if bottom else 'top', output_x, output_y, rotation, 'OK']


def formatted(number):
    return format(Decimal(str(number)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP), '.3f')


def export(board_path, tape_path, output_path):
    board = parse(Path(board_path).read_text())
    setup = first(board, 'setup')
    drill = first(setup, 'aux_axis_origin') if setup else None
    if drill is None:
        raise ValueError('Board has no drill origin')
    origin = tuple(Decimal(value) for value in drill[1:3])
    with open(tape_path, newline='') as source:
        tape = {row['package']: row for row in csv.DictReader(source)}
    placed, flags = [], []
    from outline import board_contours
    profile = board_contours(board)
    for footprint in children(board, 'footprint'):
        reference = next(prop[2] for prop in children(footprint, 'property') if prop[1] == 'Reference')
        try:
            side, position_x, position_y, rotation, status = placement(footprint, origin, tape, profile)
            placed.append([reference, side, formatted(position_x), formatted(position_y), formatted(rotation), status])
        except ValueError as error:
            flags.append([reference, str(error)])
    destination = Path(output_path)
    destination.mkdir(parents=True, exist_ok=True)
    for filename, header, rows in (
            ('placement.csv', ['ref', 'side', 'x', 'y', 'rot', 'status'], placed),
            ('flags.csv', ['ref', 'reason'], flags)):
        with (destination / filename).open('w', newline='') as target:
            writer = csv.writer(target)
            writer.writerow(header)
            writer.writerows(sorted(rows))


if __name__ == '__main__':
    try:
        export(*sys.argv[1:])
    except (ValueError, OSError) as error:
        sys.exit(str(error))
