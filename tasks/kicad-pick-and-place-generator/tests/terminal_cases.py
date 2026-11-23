"""Private dimensional copper controls and seeded equivalent supplier lands."""

import copy
import random
from fractions import Fraction

from copper import polygons, rectangle, rotate
from reference import (ANGLES, DIRECTIONS, Part, body_datum, inspection, raw_inspection,
                       rectangle as fab_rectangle, render_board, saved_parts, separated, tape_text)


def land(anchor, material, size=(.1, .1), name='1', angle=0):
    anchor = tuple(Fraction(str(value)) for value in anchor)
    return dict(name=name, at=anchor, size=size, angle=angle,
                polygons=[[tuple(Fraction(str(point[axis])) - anchor[axis] for axis in (0, 1))
                           for point in polygon] for polygon in material])


def native(anchor, size, name='1'):
    return dict(name=name, at=anchor, size=size, angle=0, polygons=[])


def sync(part):
    part.pads = [(record['name'], record['at']) for record in part.pad_data]
    part.pad_angles = [record.get('angle', 0) for record in part.pad_data]
    part.nets = {name: index + 1 for index, name in enumerate(sorted({name for name, _ in part.pads if name}))}
    return part


def base_part(family, material, tape='TL'):
    part = Part(family, '', True, tape, [], [fab_rectangle(-9, -8, 9, 8)])
    part.pad_data = material + [native((4, 4), (.3, .3), '2')]
    return sync(part)


def analytic_parts():
    first = land((-.2, -1.5), [rectangle(-4, -4, -1, -1), rectangle(-1, -2, 0, -1)])
    second = land((-1, -5), [rectangle(-7, -1, -1, 1), rectangle(-1.1, -6, -.9, 0)])
    third = [native((-3, 0), (2, 2)), native((0, -3), (1, .5))]
    horizontal = rectangle(-6, -1, 0, 1)
    fourth = land((-.5, -.5), [horizontal, horizontal[::-1], horizontal, rectangle(-1, -6, 1, 0)])
    parts = [base_part('offset-anchor', [first]), base_part('nonconvex-area', [second], 'L'),
             base_part('unequal-split', third, 'L'), base_part('overlap-union', [fourth])]
    for index, part in enumerate(parts):
        part.ref = ('J18', 'U63', 'Q27', 'J204')[index]
        part.package = ('Contact_PW4', 'Terminal_FK3', 'PowerLead_D2', 'SpringLand_C7')[index]
        part.library = 'Supplier_Lands'
        part.x, part.y = 110 + 20 * index, 90
    return parts


def analytic_case():
    parts = saved_parts(analytic_parts(), (100, 100))
    truth = {part.ref: ['top', f'{10 + 20 * index:.3f}', '10.000', '0.000'] for index, part in enumerate(parts)}
    return render_board(parts, (100, 100), 'Connector carrier').encode(), tape_text(parts).encode(), truth, parts


def physical_transform(part, scale_x, scale_y, shift, turns, bottom, theta, relative):
    result = copy.deepcopy(part)
    def point(value):
        horizontal, vertical = rotate((Fraction(str(value[0])) * scale_x, Fraction(str(value[1])) * scale_y), 90 * turns)
        return horizontal + shift[0], (-vertical if bottom else vertical) + shift[1]
    result.shapes = [(kind, layer, [point(value) for value in vertices]) for kind, layer, vertices in part.shapes]
    result.pad_data = []
    for original in part.pad_data:
        material = [[point((Fraction(str(original['at'][0])) + Fraction(str(value[0])),
                            Fraction(str(original['at'][1])) + Fraction(str(value[1]))))
                     for value in polygon] for polygon in original.get('polygons', [])]
        anchor = point(original['at'])
        size = (Fraction(str(original['size'][0])) * scale_x,
                Fraction(str(original['size'][1])) * scale_y)
        if (turns - relative // 90) % 2:
            size = size[::-1]
        record = dict(name=original['name'], at=anchor, size=size, angle=(theta + relative) % 360)
        record['polygons'] = [[rotate((vertex[0] - anchor[0], vertex[1] - anchor[1]), -relative)
                               for vertex in polygon] for polygon in material]
        result.pad_data.append(record)
    result.angle, result.bottom = theta, bottom
    return sync(result)


def alternate(part, generator):
    result = copy.deepcopy(part)
    for record in result.pad_data:
        old_material = polygons(record, part.angle)
        shift = rotate((Fraction(1, 200), Fraction(-1, 200)), record['angle'] - part.angle)
        anchor = tuple(Fraction(str(record['at'][axis])) + shift[axis] for axis in (0, 1))
        relative = (record['angle'] - part.angle + generator.choice((90, 180, 270))) % 360
        record['at'], record['size'] = anchor, (.02, .02)
        record['angle'] = (part.angle + relative) % 360
        material = []
        for polygon in old_material:
            vertices = [rotate((point[0] - anchor[0], point[1] - anchor[1]), -relative) for point in polygon]
            if generator.choice((False, True)):
                vertices.reverse()
            material.append(vertices)
        first = material[0]
        horizontal = sorted({point[0] for point in first})
        vertical = sorted({point[1] for point in first})
        if len(first) == 4 and len(horizontal) == len(vertical) == 2:
            middle = sum(horizontal) / 2
            material[:1] = [rectangle(horizontal[0], vertical[0], middle, vertical[1]),
                            rectangle(middle, vertical[0], horizontal[1], vertical[1])]
        if len(material) < 7:
            material.append(copy.deepcopy(material[-1]))
        generator.shuffle(material)
        record['polygons'] = material
        record.pop('omit_angle', None)
    return sync(result)


def supplier_templates():
    controls = analytic_parts()
    chamfer = [(-4, -4), (-1.5, -4), (-1, -3.5), (-1, -1), (-3.5, -1), (-4, -1.5)]
    shifted = base_part('shifted-anchor', [land((-.2, -1.5), [chamfer, rectangle(-1.5, -2, 0, -1)])])
    unequal = controls[2]
    unequal.family = 'unequal-split'
    overlap = controls[3]
    overlap.family = 'overlap'
    overlap.pad_data.insert(1, land((-2, 0), [rectangle(-3, -.8, -.5, .8)]))
    sync(overlap)
    frames = copy.deepcopy(shifted)
    frames.family = 'frames'
    exposed = base_part('exposed-anchor', [land((-2, -3), [rectangle(-.4, -3.5, .4, -2.5),
                       rectangle(-.3, -3.4, .3, -2.6)], size=(5, 1))])
    review = base_part('orientation-review', [land((1, 0), [rectangle(-2, -1, 2, 1), rectangle(-1, -.5, 1, .5)])], 'L')
    return [shifted, unequal, overlap, frames, exposed, review]


def equivalent_cases():
    generator = random.Random(471893)
    origin = tuple(Fraction(generator.randint(800, 1200), 10) for _ in range(2))
    references = generator.sample(range(111, 998), 24)
    identities = generator.sample(range(0x10000, 0xfffff), 24)
    parts, equivalents = [], []
    for family_index, template in enumerate(supplier_templates()):
        for variant in range(4):
            base = copy.deepcopy(template)
            if family_index == 5:
                if variant == 1:
                    base = copy.deepcopy(supplier_templates()[1])
                    base.family, base.tape = 'orientation-review', 'TL'
                elif variant == 2:
                    base = copy.deepcopy(supplier_templates()[0])
                    base.family, base.tape = 'orientation-review', 'L'
                elif variant == 3:
                    base = base_part('orientation-review', [land((2, 0), [rectangle(-3, -.5, 3, .5), rectangle(-.5, -3, .5, 3)])], 'T')
            while True:
                theta = generator.choice(ANGLES)
                relative = generator.choice((-90, 0, 90, 180))
                if family_index == 3 and variant == 0:
                    theta, relative = 90, -90
                scale_x = Fraction(generator.choice((8, 10, 12)), 10)
                scale_y = Fraction(generator.choice((8, 10, 12)), 10)
                shift = tuple(Fraction(generator.randint(-30, 30), 10) for _ in range(2))
                bottom = bool(variant % 2)
                candidate = physical_transform(base, scale_x, scale_y, shift, variant, bottom, theta, relative)
                if family_index == 3 and variant == 0:
                    for record in candidate.pad_data:
                        record['omit_angle'] = True
                candidate.x, candidate.y = generator.randint(200, 2400) / 10, generator.randint(200, 1800) / 10
                if family_index != 5:
                    desired = (1, 3, 5, 7)[variant] if family_index != 1 else (0, 2, 4, 6)[variant]
                    candidate.tape = list(DIRECTIONS)[desired]
                if separated(candidate, origin) and (raw_inspection(candidate, origin) is None) == (family_index == 5):
                    break
            index = 4 * family_index + variant
            candidate.ref = generator.choice(('J', 'U', 'Q')) + str(references[index])
            candidate.package = 'Contact_' + format(identities[index], 'X')
            candidate.library = generator.choice(('Northline', 'Morrow', 'Avocet'))
            if variant % 2:
                for record in candidate.pad_data:
                    if record['name'] == '1':
                        record['name'] = 'A'
                sync(candidate)
            parts.append(candidate)
            equivalents.append(alternate(candidate, generator))
    generator.shuffle(parts)
    by_ref = {part.ref: part for part in equivalents}
    equivalents = [by_ref[part.ref] for part in parts]
    parts = saved_parts(parts, origin)
    equivalents = saved_parts(equivalents, origin)
    first = render_board(parts, origin, 'Interface contact carrier').encode()
    second = render_board(equivalents, origin, 'Interface contact carrier').encode()
    return first, second, tape_text(parts).encode(), inspection(parts, origin), inspection(equivalents, origin), parts, equivalents


def diagnostic_case():
    generator = random.Random(116041)
    origin = tuple(generator.randint(800, 1200) / 10 for _ in range(2))
    references = generator.sample(range(131, 997), 3)
    parts = []
    for index, family in enumerate(('missing_package', 'body-diagnostic', 'pin1-diagnostic')):
        part = Part(family, 'Contact_' + format(generator.getrandbits(32), 'X'), index == 2, 'TL' if index == 2 else '',
                    [('2', (-2, -2)), ('3', (2, 2))], [fab_rectangle(-3, -3, 3, 3)],
                    ref='J' + str(references[index]), bottom=generator.choice((False, True)),
                    x=generator.randint(200, 2400) / 10, y=generator.randint(200, 1800) / 10,
                    angle=generator.choice(ANGLES))
        if index == 1:
            part.shapes = []
            part.pads.append(('4', (3, 1)))
        parts.append(part)
    parts = saved_parts(parts, origin)
    return render_board(parts, origin, 'Contact review').encode(), tape_text(parts).encode(), inspection(parts, origin), parts


def causes(part, reels):
    result = set()
    datum = body_datum(part)
    if datum is None:
        result.add('body')
    row = reels.get(part.package)
    if row is None:
        result.add('tape')
    elif row['polar'] == 'Y' and datum is not None:
        probe = copy.copy(part)
        probe.polar, probe.tape = True, row['pin1_pos']
        if raw_inspection(probe, (0, 0)) is None:
            result.add('pin1')
    return result
