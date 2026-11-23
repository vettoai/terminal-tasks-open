"""Private surface reference: vertical material intervals and adaptive moments."""

import math

from copper import polygons, records, rotate, rational


def geometry(part, selected=('1', 'A')):
    lands, bores = [], []
    side = 'B.Cu' if part.bottom else 'F.Cu'
    for record in records(part):
        anchor = tuple(map(float, record['at']))
        if record.get('drill'):
            bores.append((*anchor, float(record['drill']) / 2))
        if record['name'] not in selected or not ({side, '*.Cu'} & set(record.get('layers', [side]))):
            continue
        outlines = [[tuple(map(float, point)) for point in polygon] for polygon in polygons(record, part.angle)]
        circles = []
        for circle in record.get('circles', []):
            offset = rotate(tuple(map(rational, circle['center'])), record.get('angle', 0) - part.angle)
            centre = tuple(anchor[axis] + float(offset[axis]) for axis in (0, 1))
            radius = math.dist(circle['center'], circle['end'])
            width = float(circle['width'])
            circles.append((*centre, radius + width / 2, 0 if circle['fill'] else radius - width / 2))
        lands.append((outlines, circles))
    return lands, bores


def merge(intervals):
    result = []
    for lower, upper in sorted(intervals):
        if upper <= lower:
            continue
        if result and lower <= result[-1][1]:
            result[-1] = (result[-1][0], max(upper, result[-1][1]))
        else:
            result.append((lower, upper))
    return result


def cut(intervals, holes):
    result = intervals
    for start, stop in holes:
        next_result = []
        for lower, upper in result:
            if stop <= lower or start >= upper:
                next_result.append((lower, upper))
            else:
                if lower < start:
                    next_result.append((lower, start))
                if stop < upper:
                    next_result.append((stop, upper))
        result = next_result
    return result


def disk_slice(circle, horizontal):
    centre_x, centre_y, radius = circle
    square = radius * radius - (horizontal - centre_x) ** 2
    if square <= 0:
        return []
    half = math.sqrt(square)
    return [(centre_y - half, centre_y + half)]


def intervals(lands, bores, horizontal):
    positive = []
    for outlines, circles in lands:
        for polygon in outlines:
            crossings = []
            for first, second in zip(polygon, polygon[1:] + polygon[:1]):
                if min(first[0], second[0]) <= horizontal < max(first[0], second[0]):
                    crossings.append(first[1] + (horizontal - first[0]) * (second[1] - first[1]) / (second[0] - first[0]))
            crossings.sort()
            positive.extend(zip(crossings[::2], crossings[1::2]))
        for centre_x, centre_y, outer, inner in circles:
            positive.extend(cut(disk_slice((centre_x, centre_y, outer), horizontal),
                                disk_slice((centre_x, centre_y, inner), horizontal) if inner else []))
    return cut(merge(positive), merge([interval for bore in bores for interval in disk_slice(bore, horizontal)]))


def breakpoints(lands, bores):
    edges, circles, values = [], list(bores), set()
    for outlines, round_shapes in lands:
        for polygon in outlines:
            values.update(point[0] for point in polygon)
            edges.extend(zip(polygon, polygon[1:] + polygon[:1]))
        for centre_x, centre_y, outer, inner in round_shapes:
            circles.append((centre_x, centre_y, outer))
            if inner:
                circles.append((centre_x, centre_y, inner))
    for centre_x, _, radius in circles:
        values.update((centre_x - radius, centre_x + radius))
    for index, (first, second) in enumerate(edges):
        delta_x, delta_y = second[0] - first[0], second[1] - first[1]
        for third, fourth in edges[:index]:
            other_x, other_y = fourth[0] - third[0], fourth[1] - third[1]
            determinant = delta_x * other_y - delta_y * other_x
            if abs(determinant) > 1e-14:
                offset_x, offset_y = third[0] - first[0], third[1] - first[1]
                along = (offset_x * other_y - offset_y * other_x) / determinant
                across = (offset_x * delta_y - offset_y * delta_x) / determinant
                if 0 <= along <= 1 and 0 <= across <= 1:
                    values.add(first[0] + along * delta_x)
        length_squared = delta_x ** 2 + delta_y ** 2
        if not length_squared:
            continue
        for centre_x, centre_y, radius in circles:
            offset_x, offset_y = first[0] - centre_x, first[1] - centre_y
            linear = 2 * (offset_x * delta_x + offset_y * delta_y)
            constant = offset_x ** 2 + offset_y ** 2 - radius ** 2
            discriminant = linear ** 2 - 4 * length_squared * constant
            if discriminant >= 0:
                for sign in (-1, 1):
                    along = (-linear + sign * math.sqrt(discriminant)) / (2 * length_squared)
                    if 0 <= along <= 1:
                        values.add(first[0] + along * delta_x)
    for index, (centre_x, centre_y, radius) in enumerate(circles):
        for other_x, other_y, other_radius in circles[:index]:
            distance = math.hypot(other_x - centre_x, other_y - centre_y)
            if distance <= 1e-13 or not abs(radius - other_radius) <= distance <= radius + other_radius:
                continue
            along = (radius ** 2 - other_radius ** 2 + distance ** 2) / (2 * distance)
            height = math.sqrt(max(0, radius ** 2 - along ** 2))
            base = centre_x + along * (other_x - centre_x) / distance
            values.update((base - height * (other_y - centre_y) / distance,
                           base + height * (other_y - centre_y) / distance))
    ordered = sorted(values)
    return [value for index, value in enumerate(ordered) if index == 0 or value - ordered[index - 1] > 1e-11]


def integrate(function, left, right, tolerance=2e-10):
    def simpson(start, stop, first, middle, last):
        return tuple((stop - start) * (first[axis] + 4 * middle[axis] + last[axis]) / 6 for axis in range(3))
    def refine(start, stop, first, middle, last, whole, budget, depth):
        midpoint = (start + stop) / 2
        quarter, third = function((start + midpoint) / 2), function((midpoint + stop) / 2)
        lower = simpson(start, midpoint, first, quarter, middle)
        upper = simpson(midpoint, stop, middle, third, last)
        total = tuple(lower[axis] + upper[axis] for axis in range(3))
        if depth == 0 or max(abs(total[axis] - whole[axis]) for axis in range(3)) < 15 * budget:
            return tuple(total[axis] + (total[axis] - whole[axis]) / 15 for axis in range(3))
        lower = refine(start, midpoint, first, quarter, middle, lower, budget / 2, depth - 1)
        upper = refine(midpoint, stop, middle, third, last, upper, budget / 2, depth - 1)
        return tuple(lower[axis] + upper[axis] for axis in range(3))
    first, middle, last = function(left), function((left + right) / 2), function(right)
    return refine(left, right, first, middle, last, simpson(left, right, first, middle, last), tolerance, 20)


def surface_moments(part, selected=('1', 'A'), prepared=None):
    lands, bores = prepared if prepared is not None else geometry(part, selected)
    from profile import intersect
    profile = part.profile
    breaks = breakpoints(lands + ([(profile, [])] if profile else []), bores)
    material_breaks = breakpoints(lands, bores)
    if not material_breaks:
        return 0., 0., 0.
    breaks = sorted(set([material_breaks[0], material_breaks[-1]] +
                        [value for value in breaks if material_breaks[0] < value < material_breaks[-1]]))
    total = [0., 0., 0.]
    for left, right in zip(breaks, breaks[1:]):
        def sample(parameter):
            if parameter <= 0 or parameter >= math.pi / 2:
                return 0., 0., 0.
            horizontal = left + (right - left) * math.sin(parameter) ** 2
            jacobian = (right - left) * math.sin(2 * parameter)
            bands = intervals(lands, bores, horizontal)
            if profile:
                from profile import bands as profile_bands
                bands = intersect(bands, profile_bands(profile, horizontal))
            length = sum(upper - lower for lower, upper in bands)
            return (length * jacobian, horizontal * length * jacobian,
                    sum((upper ** 2 - lower ** 2) / 2 for lower, upper in bands) * jacobian)
        moments = integrate(sample, 0, math.pi / 2)
        total = [total[axis] + moments[axis] for axis in range(3)]
    return tuple(total)
