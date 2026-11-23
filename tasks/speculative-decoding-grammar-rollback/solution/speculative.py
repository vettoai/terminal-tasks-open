"""Batched draft/target generation for grammar-constrained records."""

import math
from functools import lru_cache

import torch

from generate import prompt_state
from sampling import probabilities


@lru_cache(maxsize=4096)
def scored_weights(logits, mask, temperature, top_p):
    return probabilities(torch.tensor(logits, dtype=torch.float64), torch.tensor(mask, dtype=torch.bool), temperature, top_p)


def scored_distribution(logits, mask, temperature, top_p):
    return scored_weights(tuple(logits.tolist()), tuple(mask.tolist()), temperature, top_p).clone()


def draw_measure(weights, sampler):
    resolution = getattr(sampler, "categorical_resolution", None)
    if resolution is None:
        return weights / weights.sum()
    values = [float(value) for value in weights.tolist()]
    total = 0.0
    for value in values:
        total += value
    masses = [0.0] * len(values)
    cumulative = 0.0
    covered = 0
    last = 0
    for token_id, value in enumerate(values):
        cumulative += value / total
        if value > 0:
            boundary = min(resolution, max(0, math.ceil(cumulative * resolution)))
            masses[token_id] = (boundary - covered) / resolution
            covered = boundary
            last = token_id
    masses[last] += (resolution - covered) / resolution
    return torch.tensor(masses, dtype=torch.float64)


def residual_draw(weights, sampler):
    if getattr(sampler, "categorical_resolution", None) is None:
        return sampler.categorical(weights)
    supported = [(token_id, value) for token_id, value in enumerate(weights.tolist()) if value > 0]
    remaining = sum(value for _, value in supported)
    for token_id, value in supported[:-1]:
        if sampler.bernoulli(min(1.0, value / remaining)):
            return token_id
        remaining -= value
    return supported[-1][0]


@torch.inference_mode()
def speculative_generate(target, draft, grammar, prompt_ids, *, num_draft=4, temperature, top_p, max_new_tokens, sampler):
    context = list(prompt_ids)
    output = []
    while len(output) < max_new_tokens:
        state = prompt_state(grammar, context)
        remaining = max_new_tokens - len(output)
        proposed = []
        masks = []
        proposal_probs = []
        for _ in range(min(num_draft, remaining)):
            row = draft(torch.tensor([context + proposed], dtype=torch.long))[0, -1]
            mask = grammar.allowed_tokens(state).clone()
            masks.append(mask)
            distribution = scored_distribution(row, mask, temperature, top_p)
            token_id = sampler.categorical(distribution.clone())
            proposed.append(token_id)
            proposal_probs.append(draw_measure(distribution, sampler))
            state = grammar.advance(state, token_id)
            if token_id == grammar.eos_id:
                break
        bonus_mask = grammar.allowed_tokens(state).clone()
        length = len(context)
        target_rows = target(torch.tensor([context + proposed], dtype=torch.long))[0]
        for position, token_id in enumerate(proposed):
            row = target_rows[length + position - 1]
            target_probs = draw_measure(scored_distribution(row, masks[position], temperature, top_p), sampler)
            draft_probs = proposal_probs[position]
            ratio = min(1.0, float(target_probs[token_id] / draft_probs[token_id]))
            if sampler.bernoulli(ratio):
                output.append(token_id)
                context.append(token_id)
                if token_id == grammar.eos_id or len(output) == max_new_tokens:
                    return output
            else:
                residual = torch.clamp(target_probs - draft_probs, min=0)
                residual = residual / residual.sum()
                replacement = residual_draw(residual, sampler)
                output.append(replacement)
                context.append(replacement)
                if replacement == grammar.eos_id:
                    return output
                break
        else:
            if len(output) < max_new_tokens:
                distribution = scored_distribution(target_rows[-1], bonus_mask, temperature, top_p)
                bonus = sampler.categorical(distribution)
                output.append(bonus)
                context.append(bonus)
                if bonus == grammar.eos_id:
                    return output
    return output
