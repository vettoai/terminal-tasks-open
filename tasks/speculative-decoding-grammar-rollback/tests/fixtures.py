"""Private finite probability experiments and an independent target oracle."""

from copy import deepcopy
from dataclasses import dataclass
import math
import random

import torch

from grammar import JsonGrammar
from tokenizer import BOS_ID, EOS_ID, TOKEN_IDS, VOCAB


class FiniteGrammar:
    eos_id = EOS_ID

    def __init__(self, transitions, accepting):
        self.transitions = transitions
        self.accepting = set(accepting)

    def initial_state(self):
        return {"node": 0}

    def allowed_tokens(self, state):
        mask = torch.zeros(256, dtype=torch.bool)
        mask[list(self.transitions[state["node"]])] = True
        return mask

    def advance(self, state, token_id):
        state["node"] = self.transitions[state["node"]].get(int(token_id), state["node"])
        return state

    def is_accepting(self, state):
        return state["node"] in self.accepting


def grammar_graph(grammar):
    """Describe the pristine finite graph without depending on state names."""
    states = [grammar.initial_state()]
    rows = []
    position = 0
    while position < len(states):
        state = states[position]
        transitions = {}
        for token_id, allowed in enumerate(grammar.allowed_tokens(state).tolist()):
            if not allowed:
                continue
            successor = grammar.advance(deepcopy(state), token_id)
            try:
                index = states.index(successor)
            except ValueError:
                index = len(states)
                states.append(successor)
            transitions[str(token_id)] = index
        rows.append({"accepting": bool(grammar.is_accepting(state)), "transitions": transitions})
        position += 1
    return {"rows": rows, "eos_id": int(grammar.eos_id)}


def process(raw, mask, temperature, top_p):
    """Independent scalar implementation, deliberately not sampling.probabilities."""
    entries = [(token_id, math.log(mass) / temperature) for token_id, mass in raw.items() if mass > 0 and bool(mask[token_id])]
    if not entries:
        raise ValueError("No allowed fixture mass")
    shift = max(value for _, value in entries)
    weighted = [(token_id, math.exp(value - shift)) for token_id, value in entries]
    total = sum(value for _, value in weighted)
    ordered = sorted(((token_id, value / total) for token_id, value in weighted), key=lambda entry: (-entry[1], entry[0]))
    retained = []
    cumulative = 0.0
    for token_id, probability in ordered:
        retained.append((token_id, probability))
        cumulative += probability
        if cumulative >= top_p:
            break
    normalizer = sum(value for _, value in retained)
    return {token_id: value / normalizer for token_id, value in retained}


@dataclass
class Fixture:
    name: str
    grammar: object
    limit: int
    target: dict
    draft: dict
    default: dict
    identical: bool = False
    prompt: tuple = (BOS_ID,)
    call_bound: int = 0
    head_position: int = 0

    def raw(self, kind, prefix):
        return getattr(self, kind).get(tuple(prefix), self.default)

    def payload(self):
        def rows(table):
            return [[list(prefix), {str(token): mass for token, mass in raw.items()}] for prefix, raw in table.items()]
        return {"name": self.name, "limit": self.limit, "grammar": grammar_graph(self.grammar), "target": rows(self.target), "draft": rows(self.draft), "default": {str(token): mass for token, mass in self.default.items()}}

    def expected(self, temperature, top_p, resolution=None):
        outputs = {}

        def visit(prefix, state, weight):
            generated = prefix[len(self.prompt):]
            if len(generated) == self.limit or (generated and generated[-1] == EOS_ID):
                outputs[tuple(generated)] = outputs.get(tuple(generated), 0.0) + weight
                return
            probs = process(self.raw("target", prefix), self.grammar.allowed_tokens(state), temperature, top_p)
            if resolution is not None:
                from quantiles import mapped
                probs = mapped(probs)
            for token_id, mass in probs.items():
                visit(prefix + (token_id,), self.grammar.advance(deepcopy(state), token_id), weight * mass)

        state = self.grammar.initial_state()
        for token_id in self.prompt[1:]:
            state = self.grammar.advance(state, token_id)
        visit(self.prompt, state, 1.0)
        return outputs


def construct():
    rng = random.Random(20261111)
    ordinary = sorted(token_id for token_id, piece in enumerate(VOCAB) if len(piece) == 1 and piece.isascii() and piece.isalnum())
    result = []

    first, second = rng.sample(ordinary, 2)
    probability = rng.choice([0.37, 0.43, 0.61, 0.67])
    grammar = FiniteGrammar([{first: 0, second: 0, EOS_ID: 0}], [0])
    constant = {first: probability, second: 1 - probability}
    result.append(("A", grammar, 6, lambda prefix, state, kind: constant, True))

    digits = sorted(rng.sample(sorted(TOKEN_IDS[str(value)] for value in (1, 2, 4, 6, 7, 9)), 3))
    json_grammar = JsonGrammar()
    forbidden = TOKEN_IDS["a"]

    def json_row(prefix, state, kind):
        if state.phase == "status_value":
            masses = (0.56, 0.24, 0.20) if kind == "target" else (0.14, 0.56, 0.30)
            return dict(zip([TOKEN_IDS['"ok"'], TOKEN_IDS['"failed"'], TOKEN_IDS[","]], masses))
        if state.phase == "count_first":
            return dict(zip(digits, (0.70, 0.15, 0.15) if kind == "target" else (0.15, 0.15, 0.70)))
        required = TOKEN_IDS["}"] if state.phase == "count_tail" else next(iter(torch.nonzero(json_grammar.allowed_tokens(state)).flatten().tolist()))
        return {required: 0.9, forbidden: 0.1}

    result.append(("B", json_grammar, 8, json_row, False))

    initial, continuing = rng.sample(ordinary, 2)
    grammar = FiniteGrammar([{initial: 1}, {EOS_ID: 1, continuing: 1}], [1])

    def eos_row(prefix, state, kind):
        return {initial: 0.8, EOS_ID: 0.2} if state["node"] == 0 else {EOS_ID: 0.65, continuing: 0.35}

    result.append(("C", grammar, 7, eos_row, True))

    selected = rng.sample(ordinary, 12)
    pairs = [selected[index:index + 2] for index in range(0, 8, 2)]
    required = selected[8:11] + [EOS_ID]
    excluded = selected[11]
    values = [rng.choice([0.41, 0.58, 0.69, 0.73]) for _ in range(4)]
    transitions = [{token_id: index + 1 for token_id in pair} for index, pair in enumerate(pairs)]
    transitions += [{token_id: min(index + 5, 7)} for index, token_id in enumerate(required)]
    grammar = FiniteGrammar(transitions, [7])

    def position_row(prefix, state, kind):
        index = state["node"]
        if index < 4:
            return dict(zip(pairs[index], (values[index], 1 - values[index]))) if kind == "target" else {pairs[index][0]: 0.8, excluded: 0.2}
        return {required[index - 4]: 0.9, excluded: 0.1}

    result.append(("D", grammar, 8, position_row, False))

    fixtures = []
    # Expand both models' reachable raw supports, including their proposed prefixes.
    for name, grammar, limit, rule, identical in result:
        target, draft = {}, {}
        pending = [((BOS_ID,), grammar.initial_state())]
        seen = set()
        while pending:
            prefix, state = pending.pop()
            if prefix in seen:
                continue
            seen.add(prefix)
            target[prefix] = rule(prefix, state, "target")
            draft[prefix] = rule(prefix, state, "draft")
            if len(prefix) - 1 >= limit:
                continue
            allowed = grammar.allowed_tokens(state)
            for token_id in sorted(set(target[prefix]) | set(draft[prefix])):
                if allowed[token_id] and token_id != EOS_ID:
                    pending.append((prefix + (token_id,), grammar.advance(deepcopy(state), token_id)))
        default = dict(target[(BOS_ID,)])
        if name == "A":
            default = dict(constant)
        if name == "C":
            default = {EOS_ID: 0.65, continuing: 0.35}
        fixtures.append(Fixture(name, grammar, limit, target, draft, default, identical))
    return fixtures


def validate_output(output, grammar, limit, prompt=(BOS_ID,)):
    if not isinstance(output, list) or len(output) > limit:
        return f"sequence length/type outside requested limit {limit}"
    state = grammar.initial_state()
    for token_id in prompt[1:]:
        state = grammar.advance(state, token_id)
    for position, token_id in enumerate(output):
        if type(token_id) is not int or not 0 <= token_id < 256:
            return f"invalid ID at {position}"
        if not grammar.allowed_tokens(state)[token_id]:
            return f"forbidden ID {token_id} at {position}"
        if token_id == grammar.eos_id:
            if not grammar.is_accepting(state) or position != len(output) - 1:
                return f"EOS at nonaccepting/nonfinal position {position}"
        state = grammar.advance(state, token_id)
    if not output or (output[-1] != grammar.eos_id and len(output) != limit):
        return "early non-EOS termination"
    return None
