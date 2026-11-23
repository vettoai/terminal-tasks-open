"""Independent rational slab integration of filled terminal material."""

import math
from fractions import Fraction


def rational(value):
    return Fraction(str(value))


def rectangle(left, top, right, bottom):
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def rotate(point, angle):
    angle %= 360
    if angle % 90 == 0:
        cosine, sine = ((1, 0), (0, 1), (-1, 0), (0, -1))[int(angle // 90)]
    else:
        cosine = rational(round(math.cos(math.radians(angle)), 14))
        sine = rational(round(math.sin(math.radians(angle)), 14))
    return point[0] * cosine + point[1] * sine, -point[0] * sine + point[1] * cosine


def records(part):
    if part.pad_data:
        return part.pad_data
    return [dict(name=name, at=point, size=(.7, .6) if index % 2 == 0 else (.65, .55),
                 angle=part.pad_angles[index] if part.pad_angles else 0, polygons=[])
            for index, (name, point) in enumerate(part.pads)]


def polygons(record, theta):
    width, height = map(rational, record['size'])
    local = [rectangle(-width / 2, -height / 2, width / 2, height / 2)]
    local += record.get('polygons', [])
    anchor = tuple(map(rational, record['at']))
    return [[tuple(anchor[axis] + rotate(tuple(map(rational, point)),
                    record.get('angle', 0) - theta)[axis] for axis in (0, 1))
             for point in polygon] for polygon in local]


def inside(point, polygon):
    horizontal, vertical = point
    result = False
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        if (first[1] > vertical) != (second[1] > vertical):
            crossing = first[0] + (vertical - first[1]) * (second[0] - first[0]) / (second[1] - first[1])
            if horizontal < crossing:
                result = not result
    return result


def slabs(polygons):
    polygons = [[tuple(map(rational, point)) for point in polygon] for polygon in polygons]
    edges = [(first, second) for polygon in polygons
             for first, second in zip(polygon, polygon[1:] + polygon[:1]) if first != second]
    breaks = {point[0] for polygon in polygons for point in polygon}
    for index, (first, second) in enumerate(edges):
        delta = (second[0] - first[0], second[1] - first[1])
        for third, fourth in edges[:index]:
            other = (fourth[0] - third[0], fourth[1] - third[1])
            determinant = delta[0] * other[1] - delta[1] * other[0]
            if determinant:
                offset = (third[0] - first[0], third[1] - first[1])
                along = (offset[0] * other[1] - offset[1] * other[0]) / determinant
                across = (offset[0] * delta[1] - offset[1] * delta[0]) / determinant
                if 0 <= along <= 1 and 0 <= across <= 1:
                    breaks.add(first[0] + along * delta[0])
    breaks = sorted(breaks)
    for left, right in zip(breaks, breaks[1:]):
        middle = (left + right) / 2
        lines = set()
        for first, second in edges:
            if min(first[0], second[0]) < middle < max(first[0], second[0]):
                slope = (second[1] - first[1]) / (second[0] - first[0])
                lines.add((slope, first[1] - slope * first[0]))
        lines = sorted(lines, key=lambda line: line[0] * middle + line[1])
        for lower, upper in zip(lines, lines[1:]):
            point = (middle, ((lower[0] + upper[0]) * middle + lower[1] + upper[1]) / 2)
            yield left, right, lower, upper, tuple(inside(point, polygon) for polygon in polygons)


def union_moments(polygons):
    area = moment_x = moment_y = Fraction(0)
    for left, right, lower, upper, membership in slabs(polygons):
        if not any(membership):
            continue
        slope, intercept = upper[0] - lower[0], upper[1] - lower[1]
        area += slope * (right ** 2 - left ** 2) / 2 + intercept * (right - left)
        moment_x += slope * (right ** 3 - left ** 3) / 3 + intercept * (right ** 2 - left ** 2) / 2
        quadratic = upper[0] ** 2 - lower[0] ** 2
        linear = 2 * (upper[0] * upper[1] - lower[0] * lower[1])
        constant = upper[1] ** 2 - lower[1] ** 2
        moment_y += (quadratic * (right ** 3 - left ** 3) / 3 +
                     linear * (right ** 2 - left ** 2) / 2 + constant * (right - left)) / 2
    return area, moment_x, moment_y


def centroid(part):
    from profile import affects
    material = [polygon for record in records(part) if record['name'] in ('1', 'A')
                for polygon in polygons(record, part.angle)]
    if affects(part.profile, [point for polygon in material for point in polygon]) or any(record.get('circles') or record.get('drill') for record in records(part)):
        from material import surface_moments
        area, moment_x, moment_y = surface_moments(part)
        return complex(moment_x / area, moment_y / area) if area else None
    area, moment_x, moment_y = union_moments(material)
    return complex(float(moment_x / area), float(moment_y / area)) if area else None


def equal_copper(first, second):
    combined = first + second
    for _, _, _, _, membership in slabs(combined):
        if any(membership[:len(first)]) != any(membership[len(first):]):
            return False
    return True


def overlaps(first, second):
    return any(any(membership[:len(first)]) and any(membership[len(first):])
               for _, _, _, _, membership in slabs(first + second))
