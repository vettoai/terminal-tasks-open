"""Seeded native cutoff graphs with independent ordinary-prefix references."""

from copy import deepcopy
from dataclasses import dataclass, field
import math
import random

import torch

from continuations import ordinary_pool
from fixtures import FiniteGrammar, Fixture
from sampling import probabilities
from tokenizer import BOS_ID, EOS_ID


@dataclass
class NucleusFixture(Fixture):
    logits: dict = field(default_factory=dict)
    laws: dict = field(default_factory=dict)

    def expected(self, temperature, top_p, resolution=None):
        key = (temperature, top_p, resolution)
        if key not in self.laws:
            outputs = {}

            def visit(prefix, state, weight):
                generated = prefix[len(self.prompt):]
                if len(generated) == self.limit or (generated and generated[-1] == EOS_ID):
                    outputs[generated] = outputs.get(generated, 0.0) + weight
                    return
                values = probabilities(self.logits[prefix], self.grammar.allowed_tokens(state), temperature, top_p).tolist()
                if resolution is not None:
                    from quantiles import grid_masses
                    values = grid_masses(values)
                for token, mass in enumerate(values):
                    if mass > 0:
                        visit(prefix + (token,), self.grammar.advance(deepcopy(state), token), weight * mass)

            state = self.grammar.initial_state()
            for token in self.prompt[1:]:
                state = self.grammar.advance(state, token)
            visit(self.prompt, state, 1.0)
            self.laws[key] = outputs
        return self.laws[key]


def binary_mass(row, head, temperature):
    mask = torch.zeros(256, dtype=torch.bool)
    mask[head] = True
    weights = probabilities(row, mask, temperature, 1.0)
    token = max(head, key=lambda member: (float(weights[member]), -member))
    return token, float(weights[token])


def nucleus_fixtures(baseline, masked):
    rng = random.Random(934681)
    fixtures, diagnostics, all_prefixes = [], [], set()
    pool = ordinary_pool()
    with torch.inference_mode():
        for position in range(1, 5):
            temperature = 1.0 if position % 2 else 0.7
            candidates = []
            for attempt in range(256):
                prefill_length = rng.choice((1, 3, 6))
                roles = rng.sample(pool, prefill_length + position - 1 + 2 + 18)
                prefill = tuple(roles[:prefill_length])
                leading = tuple(roles[prefill_length:prefill_length + position - 1])
                head = roles[prefill_length + position - 1:prefill_length + position + 1]
                tails = [tuple(roles[-18:-9]), tuple(roles[-9:])]
                prompt = (BOS_ID,) + prefill
                context = prompt + leading
                raw = baseline(torch.tensor([context], dtype=torch.long))[0, -1].clone()
                highest, cutoff = binary_mass(raw, head, temperature)
                inputs = [context + (token,) + tails[branch][:4 - position] for branch, token in enumerate(head)]
                comparisons = [binary_mass(masked(torch.tensor([prefix], dtype=torch.long))[0, len(context) - 1], head, temperature) for prefix in inputs]
                deltas = [value - cutoff for _, value in comparisons]
                valid = 0.55 < cutoff < 0.9 and all(token == highest for token, _ in comparisons)
                valid = valid and deltas[0] * deltas[1] > 0 and all(abs(delta) > 128 * math.ulp(cutoff) for delta in deltas)
                candidates.append({'attempt': attempt, 'prompt': prompt, 'head_prefix': context, 'head': head, 'C': cutoff, 'D0': comparisons[0][1], 'D1': comparisons[1][1], 'accepted': valid})
                if valid:
                    break
            else:
                raise RuntimeError(f'No guarded native nucleus gap at head {position}: {candidates}')
            nearer = min((value for _, value in comparisons), key=lambda value: abs(value - cutoff))
            threshold = cutoff + (nearer - cutoff) / 2
            settings = (threshold, math.nextafter(threshold, cutoff))
            transitions = [{token: index + 1} for index, token in enumerate(prefill + leading)] + [{}]
            head_node = len(transitions) - 1
            accepting = []
            prefixes = {(BOS_ID,) + (prefill + leading)[:index] for index in range(len(prefill + leading) + 1)}
            for branch, token in enumerate(head):
                transitions[head_node][token] = len(transitions)
                prefix = context + (token,)
                for suffix in tails[branch]:
                    prefixes.add(prefix)
                    transitions.append({suffix: len(transitions) + 1})
                    prefix += (suffix,)
                prefixes.add(prefix)
                accepting.append(len(transitions))
                transitions.append({EOS_ID: len(transitions)})
                prefixes.add(prefix + (EOS_ID,))
            fixture = NucleusFixture(f'NC{position}', FiniteGrammar(transitions, accepting), position + 10, {}, {}, {}, prompt=prompt, call_bound=3, head_position=position)
            fixture.logits = {prefix: baseline(torch.tensor([prefix], dtype=torch.long))[0, -1].clone() for prefix in sorted(prefixes, key=lambda value: (len(value), value))}
            fixtures.append((fixture, temperature, settings))
            diagnostics.append({'fixture': fixture.name, 'candidates': candidates, 'temperature': temperature, 'C': cutoff, 'D0': comparisons[0][1], 'D1': comparisons[1][1], 't': threshold, 'settings': settings, 'highest': highest, 'head': head, 'inputs': inputs, 'head_prefix': context})
            all_prefixes.update(prefixes)
    return fixtures, sorted(all_prefixes, key=lambda value: (len(value), value)), diagnostics
