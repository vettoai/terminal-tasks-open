"""Seeded native continuation graphs and independent causal conditionals."""

from itertools import combinations
import math
import random

import torch

from continuations import ordinary_pool
from fixtures import FiniteGrammar, Fixture
from tokenizer import BOS_ID, EOS_ID


def reference_rows(model, prefixes):
    rows = {}
    with torch.inference_mode():
        for prefix in prefixes:
            logits = model(torch.tensor([prefix], dtype=torch.long))[0, -1].double().tolist()
            shift = max(logits)
            rows[prefix] = {token: math.exp(value - shift) for token, value in enumerate(logits)}
    return rows


def native_continuations(target, draft):
    rng = random.Random(498731)
    pool = ordinary_pool()
    fixtures, diagnostics = [], []
    all_prefixes = set()
    for position in range(1, 5):
        leading = rng.sample(pool, position - 1)
        prefix = (BOS_ID,) + tuple(leading)
        target_row = reference_rows(target, [prefix])[prefix]
        draft_row = reference_rows(draft, [prefix])[prefix]
        candidates = list(combinations(pool, 2))
        rng.shuffle(candidates)
        for first, second in candidates:
            target_probability = target_row[first] / (target_row[first] + target_row[second])
            draft_probability = draft_row[first] / (draft_row[first] + draft_row[second])
            if target_probability != draft_probability:
                break
        else:
            raise RuntimeError('Native continuation construction has no unequal head pair')
        head = [first, second] if target_probability < draft_probability else [second, first]
        head_target = {token: target_row[token] / sum(target_row[member] for member in head) for token in head}
        head_draft = {token: draft_row[token] / sum(draft_row[member] for member in head) for token in head}
        transitions = [{token: index + 1} for index, token in enumerate(leading)] + [{}]
        accepting = []
        prefixes = {(BOS_ID,) + tuple(leading[:index]) for index in range(position)}
        tails = rng.sample(pool, 18)
        for branch, token in enumerate(head):
            transitions[position - 1][token] = len(transitions)
            current = prefix + (token,)
            for suffix_token in tails[branch * 9:(branch + 1) * 9]:
                prefixes.add(current)
                transitions.append({suffix_token: len(transitions) + 1})
                current += (suffix_token,)
            prefixes.add(current)
            accepting.append(len(transitions))
            transitions.append({EOS_ID: len(transitions)})
            prefixes.add(current + (EOS_ID,))
        fixture = Fixture(f'NF{position}', FiniteGrammar(transitions, accepting), position + 10, {}, {}, {}, call_bound=3, head_position=position)
        ordered = sorted(prefixes, key=lambda value: (len(value), value))
        fixture.target = reference_rows(target, ordered)
        fixture.draft = reference_rows(draft, ordered)
        fixture.default = fixture.target[fixture.prompt]
        fixtures.append(fixture)
        all_prefixes.update(prefixes)
        diagnostics.append({'fixture': fixture.name, 'head': head, 'target_law': head_target, 'draft_law': head_draft, 'rejection_branch': head[0], 'rejection_probability': sum(max(head_draft[token] - head_target[token], 0) for token in head)})
    return fixtures, sorted(all_prefixes, key=lambda value: (len(value), value)), diagnostics
