"""Private continuation and checkpoint-backed finite trees."""

from copy import deepcopy
import random

from fixtures import FiniteGrammar, Fixture
from tokenizer import BOS_ID, EOS_ID, TOKEN_IDS, VOCAB


def ordinary_pool():
    return sorted(token_id for token_id, piece in enumerate(VOCAB) if len(piece) == 1 and piece.isascii() and piece.isalnum())


def continuation_fixtures():
    rng = random.Random(481013)
    pool = ordinary_pool()
    fixtures = []
    for rejection_position in range(1, 5):
        leading = rng.sample(pool, rejection_position - 1)
        head = rng.sample(pool, 2)
        suffix_pairs = [rng.sample(pool, 2) for _ in range(9)]
        transitions = [{token: index + 1} for index, token in enumerate(leading)]
        transitions.append({token: rejection_position for token in head})
        transitions.extend({token: rejection_position + index + 1 for token in pair} for index, pair in enumerate(suffix_pairs))
        transitions.append({EOS_ID: rejection_position + 9})
        grammar = FiniteGrammar(transitions, [rejection_position + 9])
        target, draft = {}, {}
        initial = (BOS_ID,) + tuple(leading)
        for index, token in enumerate(leading):
            prefix = (BOS_ID,) + tuple(leading[:index])
            target[prefix] = draft[prefix] = {token: 1.0}
        target[initial] = dict(zip(head, (0.37, 0.63)))
        draft[initial] = {head[0]: 1.0}
        for branch, head_token in enumerate(head):
            prefix = initial + (head_token,)
            for index, pair in enumerate(suffix_pairs):
                selected = pair[branch] if index == 0 else rng.choice(pair)
                target[prefix] = draft[prefix] = {selected: 1.0}
                prefix += (selected,)
            target[prefix] = draft[prefix] = {EOS_ID: 1.0}
        default = {leading[0] if leading else head[0]: 1.0}
        fixtures.append(Fixture(f'F{rejection_position}', grammar, rejection_position + 10, target, draft, default, call_bound=3, head_position=rejection_position))
    return fixtures


def native_fixtures():
    rng = random.Random(620117)
    statuses = rng.sample(sorted(TOKEN_IDS[piece] for piece in ('"ok"', '"retry"', '"failed"')), 2)
    digits = rng.sample(sorted(TOKEN_IDS[str(value)] for value in range(10)), 2)
    pieces = [[TOKEN_IDS['{']], [TOKEN_IDS['"status":']], statuses, [TOKEN_IDS[',']], [TOKEN_IDS['"count":']], digits, [TOKEN_IDS['}']], [EOS_ID]]
    transitions = [{token: min(index + 1, 7) for token in members} for index, members in enumerate(pieces)]
    grammar = FiniteGrammar(transitions, [7])
    short_prompt = (BOS_ID, TOKEN_IDS['{'], TOKEN_IDS['"status":'])
    long_prompt = short_prompt + (statuses[0], TOKEN_IDS[','], TOKEN_IDS['"count":'])
    fixtures = [Fixture('N1', grammar, 6, {}, {}, {}, prompt=short_prompt), Fixture('N2', grammar, 3, {}, {}, {}, prompt=long_prompt)]
    prefixes = set()

    def visit(prefix, state):
        prefixes.add(prefix)
        for token in sorted(grammar.transitions[state['node']]):
            following = prefix + (token,)
            if token == EOS_ID:
                prefixes.add(following)
            else:
                visit(following, grammar.advance(deepcopy(state), token))

    visit((BOS_ID,), grammar.initial_state())
    return fixtures, sorted(prefixes, key=lambda prefix: (len(prefix), prefix))
