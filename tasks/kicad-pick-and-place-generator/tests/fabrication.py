"""Private finite-trace and continuous-curve fabrication measurements."""

import math
from collections import defaultdict, deque


def arc_parameters(vertices):
    start, mid, end = map(lambda point: complex(*point), vertices)
    first, second = mid - start, end - start
    determinant = 2 * (first.real * second.imag - first.imag * second.real)
    offset = complex((abs(first) ** 2 * second.imag - abs(second) ** 2 * first.imag) / determinant,
                     (first.real * abs(second) ** 2 - second.real * abs(first) ** 2) / determinant)
    centre = start + offset
    angle = lambda point: math.atan2((point - centre).imag, (point - centre).real)
    initial, middle, final = map(angle, (start, mid, end))
    positive = (final - initial) % math.tau
    sweep = positive if (middle - initial) % math.tau < positive else positive - math.tau
    return centre, abs(offset), initial, sweep


def oriented(kind, points, reverse):
    return kind, list(reversed(points)) if reverse else points


def contours(shapes):
    if not any(kind in ('arc', 'circle') and layer == 'own' for kind, layer, _ in shapes):
        from arrangement import atomic_edges, faces, straight_segments
        return [[('line', [point, loop[(index + 1) % len(loop)]]) for index, point in enumerate(loop)]
                for loop, area in faces(atomic_edges(straight_segments(shapes))) if area > 0]
    loops, edges = [], []
    for kind, layer, points in shapes:
        if layer != 'own':
            continue
        if kind == 'circle':
            loops.append([(kind, points)])
        elif kind in ('poly', 'rect'):
            if kind == 'rect':
                (left, top), (right, bottom) = points
                points = [(left, top), (right, top), (right, bottom), (left, bottom)]
            loops.append([('line', [point, points[(index + 1) % len(points)]])
                          for index, point in enumerate(points)])
        else:
            edges.append((kind, points))
    def key(point):
        return tuple(round(coordinate, 7) for coordinate in point)
    adjacency = defaultdict(set)
    endpoints = []
    for index, (_, points) in enumerate(edges):
        ends = key(points[0]), key(points[-1])
        endpoints.append(ends)
        for vertex in ends:
            adjacency[vertex].add(index)
    leaves = deque(vertex for vertex, incident in adjacency.items() if len(incident) < 2)
    remaining = set(range(len(edges)))
    while leaves:
        vertex = leaves.popleft()
        for index in list(adjacency[vertex]):
            remaining.discard(index)
            for endpoint in endpoints[index]:
                adjacency[endpoint].discard(index)
                if len(adjacency[endpoint]) == 1:
                    leaves.append(endpoint)
    while remaining:
        index = min(remaining)
        vertex = endpoints[index][0]
        initial = vertex
        loop = []
        while True:
            reverse = endpoints[index][0] != vertex
            loop.append(oriented(*edges[index], reverse))
            remaining.remove(index)
            vertex = endpoints[index][0 if reverse else 1]
            if vertex == initial:
                break
            index = next(edge for edge in adjacency[vertex] if edge in remaining)
        loops.append(loop)
    return loops


def curve_points(kind, vertices):
    if kind == 'line':
        return [complex(*point) for point in vertices]
    if kind == 'circle':
        centre, endpoint = [complex(*point) for point in vertices]
        radius = abs(endpoint - centre)
        return [centre + radius * phase for phase in (1, -1, 1j, -1j)]
    centre, radius, start, sweep = arc_parameters(vertices)
    angles = [start, start + sweep]
    for candidate in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
        distance = ((candidate - start) if sweep > 0 else (start - candidate)) % math.tau
        if distance <= abs(sweep) + 1e-10:
            angles.append(candidate)
    return [centre + radius * complex(math.cos(angle), math.sin(angle)) for angle in angles]


def loop_bounds(loop):
    points = [point for kind, vertices in loop for point in curve_points(kind, vertices)]
    return (min(point.real for point in points), min(point.imag for point in points),
            max(point.real for point in points), max(point.imag for point in points))


def inside(point, loop):
    if loop[0][0] == 'circle':
        centre, endpoint = [complex(*value) for value in loop[0][1]]
        return abs(point - centre) < abs(endpoint - centre)
    polygon = []
    for kind, vertices in loop:
        if kind == 'line':
            polygon.append(complex(*vertices[0]))
        else:
            centre, radius, start, sweep = arc_parameters(vertices)
            steps = max(2, math.ceil(abs(sweep) / math.radians(0.25)))
            polygon.extend(centre + radius * complex(math.cos(start + sweep * index / steps),
                                                    math.sin(start + sweep * index / steps))
                           for index in range(steps))
    crossings = 0
    for index, first in enumerate(polygon):
        second = polygon[(index + 1) % len(polygon)]
        if (first.imag > point.imag) != (second.imag > point.imag):
            intersection = first.real + (point.imag - first.imag) * (second.real - first.real) / (second.imag - first.imag)
            crossings += intersection > point.real
    return bool(crossings % 2)


def exterior_contours(shapes):
    if not any(kind in ('arc', 'circle') and layer == 'own' for kind, layer, _ in shapes):
        from arrangement import exterior_regions, straight_segments
        return [[('line', [point, loop[(index + 1) % len(loop)]]) for index, point in enumerate(loop)]
                for loop in exterior_regions(straight_segments(shapes))]
    loops = contours(shapes)
    outside = []
    for index, loop in enumerate(loops):
        kind, vertices = loop[0]
        sample = complex(*vertices[1] if kind == 'circle' else vertices[0])
        if not any(inside(sample, other) for other_index, other in enumerate(loops) if other_index != index):
            outside.append(loop)
    return outside
