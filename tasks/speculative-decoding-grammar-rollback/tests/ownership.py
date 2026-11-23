"""Fixed-seed finite continuation graphs for cursor-owned grammar state."""

import random

from continuations import ordinary_pool
from fixtures import FiniteGrammar, Fixture
from tokenizer import BOS_ID, EOS_ID


def ownership_fixtures():
    rng = random.Random(895043)
    fixtures = []
    for graph_index in range(8):
        rejection_position = 1 + graph_index % 4
        prefill_length = 0 if graph_index < 4 else 1 + graph_index % 2
        identifiers = iter(rng.sample(ordinary_pool(), 32))
        forbidden = next(identifiers)
        transitions = []
        target, draft = {}, {}

        def node():
            transitions.append({})
            return len(transitions) - 1

        def forced(prefix, current):
            token = next(identifiers)
            successor = node()
            transitions[current][token] = successor
            target[prefix] = draft[prefix] = {token: 0.86, forbidden: 0.14}
            return prefix + (token,), successor

        current = node()
        prefix = (BOS_ID,)
        for _ in range(prefill_length):
            prefix, current = forced(prefix, current)
        prompt = prefix
        for _ in range(rejection_position - 1):
            prefix, current = forced(prefix, current)
        head_tokens = [next(identifiers), next(identifiers)]
        first_masses = rng.choice(((0.56, 0.24), (0.52, 0.28), (0.48, 0.32)))
        target[prefix] = {**dict(zip(head_tokens, first_masses)), forbidden: 0.20}
        draft[prefix] = {**dict(zip(head_tokens, (0.16, 0.64))), forbidden: 0.20}
        accepting = []
        for head_token in head_tokens:
            branch = node()
            transitions[current][head_token] = branch
            branch_prefix, branch = forced(prefix + (head_token,), branch)
            choices = [next(identifiers), next(identifiers)]
            masses = rng.choice(((0.43, 0.37), (0.61, 0.19), (0.34, 0.46)))
            target[branch_prefix] = {**dict(zip(choices, masses)), forbidden: 0.20}
            draft[branch_prefix] = {**dict(zip(choices, (0.64, 0.16))), forbidden: 0.20}
            for choice in choices:
                tail = node()
                transitions[branch][choice] = tail
                tail_prefix = branch_prefix + (choice,)
                for _ in range(2):
                    tail_prefix, tail = forced(tail_prefix, tail)
                transitions[tail][EOS_ID] = tail
                accepting.append(tail)
                target[tail_prefix] = draft[tail_prefix] = {EOS_ID: 1.0}
                target[tail_prefix + (EOS_ID,)] = draft[tail_prefix + (EOS_ID,)] = {EOS_ID: 1.0}
        grammar = FiniteGrammar(transitions, accepting)
        fixtures.append(Fixture(f'G{graph_index + 1}', grammar, rejection_position + 5, target, draft, {EOS_ID: 1.0}, prompt=prompt))
    return fixtures
