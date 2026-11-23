"""Independent finite inverse-CDF measures and seeded continuation graphs."""

from itertools import combinations
import math
import random

from continuations import ordinary_pool
from fixtures import FiniteGrammar, Fixture, process
from native_continuations import reference_rows
from tokenizer import BOS_ID, EOS_ID


RESOLUTION = 65536
SETTINGS = ((1.0, 1.0), (0.7, 0.9))


def grid_masses(values):
    total = 0.0
    for value in values:
        total += float(value)
    cumulative, covered, last = 0.0, 0, None
    counts = [0] * 256
    for token, value in enumerate(values):
        cumulative += float(value) / total
        if value > 0:
            boundary = min(RESOLUTION, max(0, math.ceil(RESOLUTION * cumulative)))
            counts[token] = boundary - covered
            covered, last = boundary, token
    counts[last] += RESOLUTION - covered
    return [count / RESOLUTION for count in counts]


def mapped(raw):
    values = [raw.get(token, 0.0) for token in range(256)]
    return {token: mass for token, mass in enumerate(grid_masses(values)) if mass > 0}


def separated(raw, margin):
    values = [raw.get(token, 0.0) for token in range(256)]
    total = sum(values)
    cumulative = 0.0
    positive = [token for token, value in enumerate(values) if value > 0]
    for token in positive[:-1]:
        cumulative += values[token] / total
        scaled = cumulative * RESOLUTION
        nearest = min(RESOLUTION - 1, max(1, round(scaled)))
        if abs(cumulative - nearest / RESOLUTION) < margin:
            return False
    return True


def chain(name, prefill, leading, head, tails, target_head, draft_head):
    before = prefill + leading
    transitions = [{token: index + 1} for index, token in enumerate(before)] + [{}]
    target, draft = {}, {}
    prefix = (BOS_ID,)
    prefixes = {prefix}
    for token in before:
        target[prefix] = draft[prefix] = {token: 1.0}
        prefix += (token,)
        prefixes.add(prefix)
    target[prefix], draft[prefix] = target_head, draft_head
    accepting = []
    for token, tail in zip(head, tails):
        transitions[len(before)][token] = len(transitions)
        current = prefix + (token,)
        for suffix in tail:
            prefixes.add(current)
            target[current] = draft[current] = {suffix: 1.0}
            transitions.append({suffix: len(transitions) + 1})
            current += (suffix,)
        prefixes.add(current)
        target[current] = draft[current] = {EOS_ID: 1.0}
        accepting.append(len(transitions))
        transitions.append({EOS_ID: len(transitions)})
        prefixes.add(current + (EOS_ID,))
    fixture = Fixture(name, FiniteGrammar(transitions, accepting), len(leading) + 11,
                      target, draft, {EOS_ID: 1.0}, prompt=(BOS_ID,) + tuple(prefill),
                      call_bound=3, head_position=len(leading) + 1)
    return fixture, prefixes


def table_graphs():
    rng = random.Random(764903)
    pool = ordinary_pool()
    fixtures = []
    for position in range(1, 5):
        chosen = rng.sample(pool, 2 + position - 1 + 4 + 4 + 8)
        prefill = chosen[:2] if position in (2, 4) else []
        leading = chosen[2:position + 1]
        head = sorted(chosen[position + 1:position + 5])
        first = chosen[position + 5:position + 9]
        shared = chosen[position + 9:]
        mask = [token in head for token in range(256)]
        while True:
            target = [base + rng.choice((-2, -1, 0, 1, 2)) for base in (13, 19, 29, 39)]
            draft = [base + rng.choice((-2, -1, 0, 1, 2)) for base in (47, 31, 15, 7)]
            target = dict(zip(head, [value / sum(target) for value in target]))
            draft = dict(zip(head, [value / sum(draft) for value in draft]))
            if all(separated(process(raw, mask, temperature, top_p), 2**-19)
                   for raw in (target, draft) for temperature, top_p in SETTINGS):
                break
        fixture, _ = chain(f'G{position}', prefill, leading, head,
                           [[first[index]] + shared for index in range(4)], target, draft)
        fixtures.append(fixture)

    prefill, first, second, tail = rng.sample(pool, 4)
    first, second = sorted((first, second))
    epsilon = rng.choice((2**-22, 2**-21, 2**-20))
    grammar = FiniteGrammar([{prefill: 1}, {EOS_ID: 1, first: 2, second: 2},
                             {tail: 3}, {EOS_ID: 3}], [1, 3])
    prefix = (BOS_ID, prefill)
    target = {prefix: dict(zip((EOS_ID, first, second), (0.31, 0.51, 0.18)))}
    draft = {prefix: dict(zip((EOS_ID, first, second), (0.42, 0.58 - epsilon, epsilon)))}
    for token in (first, second):
        target[prefix + (token,)] = draft[prefix + (token,)] = {tail: 1.0}
        target[prefix + (token, tail)] = draft[prefix + (token, tail)] = {EOS_ID: 1.0}
    fixtures.append(Fixture('G5', grammar, 3, target, draft, {EOS_ID: 1.0}, prompt=prefix))

    chosen = rng.sample(pool, 20)
    head = sorted(chosen[4:8])
    epsilon = 1 / (4 * RESOLUTION)
    fixture, _ = chain('G6', chosen[:2], chosen[2:4], head,
                       [[chosen[8 + index]] + chosen[12:20] for index in range(4)],
                       dict(zip(head, (1/8-epsilon, 1/4, 1/4, 3/8+epsilon))),
                       dict(zip(head, (1/2-epsilon, 1/4, 1/8, 1/8+epsilon))))
    fixtures.append(fixture)
    return fixtures


def native_graphs(target, draft):
    rng = random.Random(848923)
    fixtures, all_prefixes, diagnostics = [], set(), []
    for position in range(1, 5):
        leading = rng.sample(ordinary_pool(), position - 1)
        pool = [token for token in ordinary_pool() if token not in leading]
        prefix = (BOS_ID,) + tuple(leading)
        target_row = reference_rows(target, [prefix])[prefix]
        draft_row = reference_rows(draft, [prefix])[prefix]
        candidates = list(combinations(pool, 2))
        rng.shuffle(candidates)
        for head in candidates:
            mask = [token in head for token in range(256)]
            laws = [[process(raw, mask, temperature, top_p) for raw in (target_row, draft_row)]
                    for temperature, top_p in SETTINGS]
            if all(len(raw) == 2 and separated(raw, 2**-18) for pair in laws for raw in pair) and all(mapped(pair[0]) != mapped(pair[1]) for pair in laws):
                break
        else:
            raise RuntimeError('No separated unequal native quantile head')
        tails = rng.sample([token for token in pool if token not in head], 18)
        fixture, prefixes = chain(f'QNF{position}', [], leading, head,
                                  [tails[:9], tails[9:]], {}, {})
        ordered = sorted(prefixes, key=lambda value: (len(value), value))
        fixture.target = reference_rows(target, ordered)
        fixture.draft = reference_rows(draft, ordered)
        fixture.default = fixture.target[fixture.prompt]
        fixtures.append(fixture)
        all_prefixes.update(prefixes)
        diagnostics.append({'fixture': fixture.name, 'head': list(head),
                            'laws': [[mapped(raw) for raw in pair] for pair in laws]})
    return fixtures, sorted(all_prefixes, key=lambda value: (len(value), value)), diagnostics
