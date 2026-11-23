"""Private physical board contours and local material sections."""

import math


def loops(board, entries, entry):
    segments = []
    scopes = [(board, None)] + [(node, node) for node in entries(board, 'footprint')]
    for scope, owner in scopes:
        for node in scope:
            if not isinstance(node, list) or node[0] not in ('gr_line', 'gr_rect', 'gr_poly', 'fp_line', 'fp_rect', 'fp_poly'):
                continue
            if (entry(node, 'layer') or ['', ''])[1] != 'Edge.Cuts':
                continue
            if node[0].endswith('poly'):
                points = [tuple(map(float, point[1:3])) for point in entries(entry(node, 'pts'), 'xy')]
            else:
                start, end = [tuple(map(float, entry(node, name)[1:3])) for name in ('start', 'end')]
                points = [start, end] if node[0].endswith('line') else [start, (end[0], start[1]), end, (start[0], end[1])]
            if owner:
                pose = entry(owner, 'at')
                angle = math.radians(float(pose[3]) if len(pose) > 3 else 0)
                cosine, sine = math.cos(angle), math.sin(angle)
                points = [(round(float(pose[1]) + coordinate_x*cosine + coordinate_y*sine, 6),
                           round(float(pose[2]) - coordinate_x*sine + coordinate_y*cosine, 6)) for coordinate_x, coordinate_y in points]
            segments.extend(zip(points, points[1:] + ([] if node[0].endswith('line') else points[:1])))
    adjacency = {}
    for first, second in segments:
        adjacency.setdefault(first, []).append(second)
        adjacency.setdefault(second, []).append(first)
    result = []
    while adjacency:
        start = next(iter(adjacency))
        path, current = [], start
        while True:
            path.append(current)
            following = adjacency[current].pop()
            adjacency[following].remove(current)
            if not adjacency[current]:
                del adjacency[current]
            if not adjacency.get(following):
                adjacency.pop(following, None)
            current = following
            if current == start:
                break
        result.append(path)
    return result


def local(contours, part):
    angle = math.radians(part.angle)
    cosine, sine = math.cos(angle), math.sin(angle)
    return [[((coordinate_x-part.x)*cosine-(coordinate_y-part.y)*sine,
              (coordinate_x-part.x)*sine+(coordinate_y-part.y)*cosine) for coordinate_x, coordinate_y in contour] for contour in contours]


def bands(contours, horizontal):
    crossings = []
    for polygon in contours:
        for first, second in zip(polygon, polygon[1:] + polygon[:1]):
            if min(first[0], second[0]) <= horizontal < max(first[0], second[0]):
                crossings.append(first[1] + (horizontal-first[0])*(second[1]-first[1])/(second[0]-first[0]))
    crossings.sort()
    return list(zip(crossings[::2], crossings[1::2]))


def intersect(first, second):
    return [(max(left, start), min(right, stop)) for left, right in first for start, stop in second
            if max(left, start) < min(right, stop)]


def affects(contours, points):
    if not contours or not points:
        return False
    left, right = min(coordinate_x for coordinate_x, _ in points), max(coordinate_x for coordinate_x, _ in points)
    top, bottom = min(coordinate_y for _, coordinate_y in points), max(coordinate_y for _, coordinate_y in points)
    for polygon in contours:
        for first, second in zip(polygon, polygon[1:] + polygon[:1]):
            interval = [0., 1.]
            for axis, bounds in enumerate(((left, right), (top, bottom))):
                direction = second[axis]-first[axis]
                if not direction:
                    if not bounds[0] <= first[axis] <= bounds[1]:
                        interval = [1., 0.]
                        break
                else:
                    parameters = sorted((bound-first[axis])/direction for bound in bounds)
                    interval = [max(interval[0], parameters[0]), min(interval[1], parameters[1])]
            if interval[0] <= interval[1]:
                return True
    return not any(start < (top+bottom)/2 < stop for start, stop in bands(contours, (left+right)/2))
