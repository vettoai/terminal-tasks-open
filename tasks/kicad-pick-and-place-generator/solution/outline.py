"""Physical board profile assembled from board and library drawing scopes."""

import math


def item(node, name):
    return next((value for value in node if isinstance(value, list) and value[0] == name), None)


def board_contours(board):
    edges = []
    scopes = [(board, (0., 0., 0.))]
    for node in board:
        if isinstance(node, list) and node[0] == 'footprint':
            pose = list(map(float, item(node, 'at')[1:]))
            scopes.append((node, tuple((pose + [0.])[:3])))
    for scope, (horizontal, vertical, angle) in scopes:
        cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        for node in scope:
            if not isinstance(node, list) or node[0] not in ('gr_line', 'gr_rect', 'gr_poly', 'fp_line', 'fp_rect', 'fp_poly'):
                continue
            if item(node, 'layer')[1] != 'Edge.Cuts':
                continue
            kind = node[0].split('_')[1]
            if kind == 'poly':
                points = [tuple(map(float, value[1:3])) for value in item(node, 'pts')[1:]]
            else:
                start, end = [tuple(map(float, item(node, name)[1:3])) for name in ('start', 'end')]
                points = [start, end] if kind == 'line' else [start, (end[0], start[1]), end, (start[0], end[1])]
            points = [(round(horizontal+coordinate_x*cosine+coordinate_y*sine, 6), round(vertical-coordinate_x*sine+coordinate_y*cosine, 6)) for coordinate_x, coordinate_y in points]
            edges.extend(zip(points, points[1:] + (points[:1] if kind != 'line' else [])))
    contours = []
    while edges:
        start, end = edges.pop()
        contour = [start]
        while end != start:
            contour.append(end)
            for index, (first, second) in enumerate(edges):
                if first == end or second == end:
                    edges.pop(index)
                    end = second if first == end else first
                    break
            else:
                raise ValueError('Open board profile')
        contours.append(contour)
    return contours


def footprint_contours(contours, footprint):
    pose = item(footprint, 'at')
    horizontal, vertical = map(float, pose[1:3])
    angle = math.radians(float(pose[3]) if len(pose) > 3 else 0.)
    cosine, sine = math.cos(angle), math.sin(angle)
    return [[((coordinate_x-horizontal)*cosine-(coordinate_y-vertical)*sine, (coordinate_x-horizontal)*sine+(coordinate_y-vertical)*cosine)
             for coordinate_x, coordinate_y in contour] for contour in contours]


def section(contours, ordinate):
    crossings = []
    for contour in contours:
        for first, second in zip(contour, contour[1:] + contour[:1]):
            if (first[1] > ordinate) != (second[1] > ordinate):
                crossings.append(first[0] + (ordinate-first[1])*(second[0]-first[0])/(second[1]-first[1]))
    crossings.sort()
    return list(zip(crossings[::2], crossings[1::2]))


def relevant(contours, points):
    if not contours or not points:
        return False
    left, right = min(float(coordinate_x) for coordinate_x, _ in points), max(float(coordinate_x) for coordinate_x, _ in points)
    top, bottom = min(float(coordinate_y) for _, coordinate_y in points), max(float(coordinate_y) for _, coordinate_y in points)
    for contour in contours:
        for first, second in zip(contour, contour[1:] + contour[:1]):
            lower, upper = 0., 1.
            for axis, minimum, maximum in ((0, left, right), (1, top, bottom)):
                delta = second[axis]-first[axis]
                if delta == 0:
                    if not minimum <= first[axis] <= maximum:
                        lower, upper = 1., 0.
                        break
                else:
                    start, stop = sorted(((minimum-first[axis])/delta, (maximum-first[axis])/delta))
                    lower, upper = max(lower, start), min(upper, stop)
            if lower <= upper:
                return True
    return not any(start < (left+right)/2 < stop for start, stop in section(contours, (top+bottom)/2))
