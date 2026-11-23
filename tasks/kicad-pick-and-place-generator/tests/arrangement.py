"""Exact finite-segment arrangement and filled exterior-region measurements."""

from collections import defaultdict
from fractions import Fraction
from functools import cmp_to_key


def subtract(first, second):
    return first[0] - second[0], first[1] - second[1]


def cross(first, second):
    return first[0] * second[1] - first[1] * second[0]


def on_segment(point, first, second):
    return cross(subtract(point, first), subtract(second, first)) == 0 and all(
        min(first[axis], second[axis]) <= point[axis] <= max(first[axis], second[axis]) for axis in (0, 1))


def atomic_edges(segments):
    segments = [(tuple(Fraction(str(value)) for value in first), tuple(Fraction(str(value)) for value in second))
                for first, second in segments if first != second]
    cuts = [set(segment) for segment in segments]
    for index, (first, second) in enumerate(segments):
        direction = subtract(second, first)
        for other_index in range(index):
            other_first, other_second = segments[other_index]
            other_direction = subtract(other_second, other_first)
            determinant = cross(direction, other_direction)
            if determinant:
                offset = subtract(other_first, first)
                parameter = cross(offset, other_direction) / determinant
                other_parameter = cross(offset, direction) / determinant
                if 0 <= parameter <= 1 and 0 <= other_parameter <= 1:
                    point = tuple(first[axis] + parameter * direction[axis] for axis in (0, 1))
                    cuts[index].add(point)
                    cuts[other_index].add(point)
            elif cross(subtract(other_first, first), direction) == 0:
                for point in (first, second, other_first, other_second):
                    if on_segment(point, first, second) and on_segment(point, other_first, other_second):
                        cuts[index].add(point)
                        cuts[other_index].add(point)
    result = set()
    for points in cuts:
        ordered = sorted(points)
        result.update(zip(ordered, ordered[1:]))
    return result


def direction_order(first, second):
    first_half = first[1] < 0 or (first[1] == 0 and first[0] < 0)
    second_half = second[1] < 0 or (second[1] == 0 and second[0] < 0)
    if first_half != second_half:
        return 1 if first_half else -1
    determinant = cross(first, second)
    return (determinant < 0) - (determinant > 0)


def faces(edges):
    neighbours = defaultdict(list)
    for first, second in edges:
        neighbours[first].append(second)
        neighbours[second].append(first)
    for vertex, adjacent in neighbours.items():
        adjacent.sort(key=cmp_to_key(lambda first, second: direction_order(subtract(first, vertex), subtract(second, vertex))))
    unvisited = {(first, second) for edge in edges for first, second in (edge, edge[::-1])}
    result = []
    while unvisited:
        initial = min(unvisited)
        first, second = initial
        walk = []
        while True:
            unvisited.remove((first, second))
            walk.append(first)
            adjacent = neighbours[second]
            following = adjacent[(adjacent.index(first) - 1) % len(adjacent)]
            first, second = second, following
            if (first, second) == initial:
                break
        area = sum(cross(point, walk[(index + 1) % len(walk)]) for index, point in enumerate(walk)) / 2
        result.append((walk, area))
    return result


def inside(point, polygon):
    crossings = 0
    for index, first in enumerate(polygon):
        second = polygon[(index + 1) % len(polygon)]
        if (first[1] > point[1]) != (second[1] > point[1]):
            intersection = first[0] + (point[1] - first[1]) * (second[0] - first[0]) / (second[1] - first[1])
            crossings += intersection > point[0]
    return bool(crossings % 2)


def exterior_regions(segments):
    edges = atomic_edges(segments)
    bounded = [(walk, area) for walk, area in faces(edges) if area > 0]
    directed = set()
    for walk, _ in bounded:
        directed.update(zip(walk, walk[1:] + walk[:1]))
    boundary = {tuple(sorted((first, second))) for first, second in directed if (second, first) not in directed}
    loops = [walk for walk, area in faces(boundary) if area > 0]
    return [loop for index, loop in enumerate(loops)
            if not any(inside(loop[0], other) for other_index, other in enumerate(loops) if index != other_index)]


def straight_segments(shapes):
    result = []
    for kind, layer, vertices in shapes:
        if layer != 'own':
            continue
        if kind == 'line':
            result.append(tuple(vertices))
        elif kind == 'rect':
            (left, top), (right, lower) = vertices
            corners = [(left, top), (right, top), (right, lower), (left, lower)]
            result.extend(zip(corners, corners[1:] + corners[:1]))
        elif kind == 'poly':
            result.extend(zip(vertices, vertices[1:] + vertices[:1]))
    return result


def bounds(region):
    return tuple(operation(point[axis] for point in region) for operation, axis in ((min, 0), (min, 1), (max, 0), (max, 1)))
