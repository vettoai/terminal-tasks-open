"""Surface-metal measurements for supplier contact lands."""

import math


def child(node, name):
    return next((item for item in node if isinstance(item, list) and item and item[0] == name), None)


def children(node, name):
    return [item for item in node if isinstance(item, list) and item and item[0] == name]


def joined(intervals):
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def removed(intervals, holes):
    for start, end in holes:
        remaining = []
        for left, right in intervals:
            if right <= start or left >= end:
                remaining.append((left, right))
            else:
                if left < start:
                    remaining.append((left, start))
                if right > end:
                    remaining.append((end, right))
        intervals = remaining
    return intervals


def disk_band(centre, radius, ordinate):
    square = radius * radius - (ordinate - centre[1]) ** 2
    if square <= 0:
        return []
    half = math.sqrt(square)
    return [(centre[0] - half, centre[0] + half)]


def surface_centroid(footprint, theta, profile=None):
    polygons, rings, bores = [], [], []
    side = child(footprint, 'layer')[1]
    for pad in children(footprint, 'pad'):
        at = child(pad, 'at')
        anchor = tuple(map(float, at[1:3]))
        drill = child(pad, 'drill')
        if pad[2] == 'thru_hole' and drill:
            bores.append((anchor, float(drill[1]) / 2))
        if pad[1] not in ('1', 'A') or not set(child(pad, 'layers')[1:]) & {side, '*.Cu'}:
            continue
        angle = math.radians((float(at[3]) if len(at) > 3 else 0) - theta)
        cosine, sine = math.cos(angle), math.sin(angle)
        def point(value):
            horizontal, vertical = map(float, value)
            return anchor[0] + horizontal * cosine + vertical * sine, anchor[1] - horizontal * sine + vertical * cosine
        width, height = map(float, child(pad, 'size')[1:3])
        polygons.append([point(value) for value in ((-width / 2, -height / 2), (width / 2, -height / 2),
                                                   (width / 2, height / 2), (-width / 2, height / 2))])
        for primitive in child(pad, 'primitives') or []:
            if not isinstance(primitive, list):
                continue
            if primitive[0] == 'gr_poly':
                polygons.append([point(item[1:3]) for item in children(child(primitive, 'pts'), 'xy')])
            elif primitive[0] == 'gr_circle':
                local_centre = tuple(map(float, child(primitive, 'center')[1:3]))
                end = tuple(map(float, child(primitive, 'end')[1:3]))
                radius = math.dist(local_centre, end)
                stroke = float(child(primitive, 'width')[1])
                filled = child(primitive, 'fill')[1] == 'yes'
                rings.append((point(local_centre), radius + stroke / 2, 0 if filled else radius - stroke / 2))
    bounds = [point[1] for polygon in polygons for point in polygon]
    for centre, outer, _ in rings:
        bounds.extend((centre[1] - outer, centre[1] + outer))
    from outline import relevant
    extents = [point for polygon in polygons for point in polygon]
    extents.extend((centre[0]+horizontal*outer, centre[1]+vertical*outer)
                   for centre, outer, _ in rings for horizontal, vertical in ((-1, -1), (-1, 1), (1, -1), (1, 1)))
    if not relevant(profile, extents):
        profile = None
    if not bounds:
        return None
    bottom, top = min(bounds), max(bounds)
    if bottom == top:
        return None
    count = 8192
    step = (top - bottom) / count
    area = moment_x = moment_y = 0.
    for index in range(count):
        ordinate = bottom + (index + .5) * step
        intervals = []
        for polygon in polygons:
            crossings = []
            for first, second in zip(polygon, polygon[1:] + polygon[:1]):
                if (first[1] > ordinate) != (second[1] > ordinate):
                    crossings.append(first[0] + (ordinate - first[1]) * (second[0] - first[0]) / (second[1] - first[1]))
            crossings.sort()
            intervals.extend(zip(crossings[::2], crossings[1::2]))
        for centre, outer, inner in rings:
            intervals.extend(removed(disk_band(centre, outer, ordinate), disk_band(centre, inner, ordinate) if inner else []))
        holes = [band for centre, radius in bores for band in disk_band(centre, radius, ordinate)]
        metal = removed(joined(intervals), joined(holes))
        if profile:
            from outline import section
            retained = section(profile, ordinate)
            metal = [(max(left, start), min(right, stop)) for left, right in metal for start, stop in retained
                     if max(left, start) < min(right, stop)]
        for left, right in metal:
            length = right - left
            area += length
            moment_x += (right + left) * length / 2
            moment_y += ordinate * length
    return (moment_x / area, moment_y / area) if area else None
