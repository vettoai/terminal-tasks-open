"""Copper-area measurement for rectangular and polygonal component lands."""

import math
from fractions import Fraction


def child(node, tag):
    return next((item for item in node if isinstance(item, list) and item and item[0] == tag), None)


def children(node, tag):
    return [item for item in node if isinstance(item, list) and item and item[0] == tag]


def cross(first, second):
    return first[0] * second[1] - first[1] * second[0]


def subtract(first, second):
    return first[0] - second[0], first[1] - second[1]


def occupied(point, polygons):
    for polygon in polygons:
        within = False
        for first, second in zip(polygon, polygon[1:] + polygon[:1]):
            if (first[1] > point[1]) != (second[1] > point[1]):
                intercept = first[0] + (point[1] - first[1]) * (second[0] - first[0]) / (second[1] - first[1])
                if point[0] < intercept:
                    within = not within
        if within:
            return True
    return False


def copper_centroid(footprint, theta, profile=None):
    if any(pad[2] == 'thru_hole' or children(child(pad, 'primitives') or [], 'gr_circle')
           for pad in children(footprint, 'pad')):
        from contact import surface_centroid
        return surface_centroid(footprint, theta, profile)
    polygons = []
    for pad in children(footprint, 'pad'):
        if pad[1] not in ('1', 'A'):
            continue
        at = child(pad, 'at')
        anchor_x, anchor_y = map(Fraction, at[1:3])
        angle = (float(at[3]) if len(at) > 3 else 0) - theta
        cosine = Fraction(str(round(math.cos(math.radians(angle)), 14)))
        sine = Fraction(str(round(math.sin(math.radians(angle)), 14)))
        width, height = map(Fraction, child(pad, 'size')[1:3])
        material = [[(-width / 2, -height / 2), (width / 2, -height / 2),
                     (width / 2, height / 2), (-width / 2, height / 2)]]
        for primitive in children(child(pad, 'primitives') or [], 'gr_poly'):
            material.append([tuple(map(Fraction, point[1:3])) for point in children(child(primitive, 'pts'), 'xy')])
        for polygon in material:
            polygons.append([(anchor_x + horizontal * cosine + vertical * sine,
                              anchor_y - horizontal * sine + vertical * cosine) for horizontal, vertical in polygon])
    if not polygons:
        return None
    from outline import relevant
    if relevant(profile, [point for polygon in polygons for point in polygon]):
        from contact import surface_centroid
        return surface_centroid(footprint, theta, profile)
    edges = [(first, second) for polygon in polygons for first, second in zip(polygon, polygon[1:] + polygon[:1]) if first != second]
    fragments = set()
    for first, second in edges:
        direction = subtract(second, first)
        parameters = {Fraction(0), Fraction(1)}
        axis = 0 if direction[0] else 1
        for other_first, other_second in edges:
            other_direction = subtract(other_second, other_first)
            offset = subtract(other_first, first)
            determinant = cross(direction, other_direction)
            if determinant:
                along = cross(offset, other_direction) / determinant
                across = cross(offset, direction) / determinant
                if 0 <= along <= 1 and 0 <= across <= 1:
                    parameters.add(along)
            elif cross(offset, direction) == 0:
                for point in (other_first, other_second):
                    parameter = (point[axis] - first[axis]) / direction[axis]
                    if 0 <= parameter <= 1:
                        parameters.add(parameter)
        ordered = sorted(parameters)
        for start, end in zip(ordered, ordered[1:]):
            endpoints = [tuple(first[axis] + parameter * direction[axis] for axis in (0, 1)) for parameter in (start, end)]
            fragments.add(tuple(sorted(endpoints)))
    twice_area = numerator_x = numerator_y = Fraction(0)
    for first, second in fragments:
        direction = subtract(second, first)
        middle = tuple((first[axis] + second[axis]) / 2 for axis in (0, 1))
        step = Fraction(1, 10 ** 10) / max(abs(direction[0]), abs(direction[1]))
        left = (middle[0] - direction[1] * step, middle[1] + direction[0] * step)
        right = (middle[0] + direction[1] * step, middle[1] - direction[0] * step)
        inside_left, inside_right = occupied(left, polygons), occupied(right, polygons)
        if inside_left == inside_right:
            continue
        if inside_right:
            first, second = second, first
        weight = cross(first, second)
        twice_area += weight
        numerator_x += (first[0] + second[0]) * weight
        numerator_y += (first[1] + second[1]) * weight
    if not twice_area:
        return None
    return float(numerator_x / (3 * twice_area)), float(numerator_y / (3 * twice_area))
