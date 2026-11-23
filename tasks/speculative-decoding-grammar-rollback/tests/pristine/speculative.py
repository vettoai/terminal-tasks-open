"""Batched draft/target generation for grammar-constrained records."""

from copy import deepcopy

import torch

from generate import prompt_state
from sampling import probabilities, proposal_probabilities


@torch.inference_mode()
def speculative_generate(target, draft, grammar, prompt_ids, *, num_draft=4, temperature, top_p, max_new_tokens, sampler):
    context = list(prompt_ids)
    state = prompt_state(grammar, context)
    output = []
    while len(output) < max_new_tokens:
        proposed = []
        draft_rows = []
        before_final = deepcopy(state)
        for _ in range(min(num_draft, max_new_tokens - len(output))):
            row = draft(torch.tensor([context + proposed], dtype=torch.long))[0, -1]
            distribution = probabilities(row, grammar.allowed_tokens(state), temperature, top_p)
            token_id = sampler.categorical(distribution)
            before_final = deepcopy(state)
            proposed.append(token_id)
            draft_rows.append(row)
            state = grammar.advance(state, token_id)
        length = len(context)
        target_rows = target(torch.tensor([context + proposed], dtype=torch.long))[0]
        for position, token_id in enumerate(proposed):
            row = target_rows[length + position - 1]
            target_probs = probabilities(row, grammar.allowed_tokens(state), temperature, top_p)
            draft_probs = proposal_probabilities(draft_rows[position], temperature)
            ratio = min(1.0, float(target_probs[token_id] / draft_probs[token_id]))
            if sampler.bernoulli(ratio):
                output.append(token_id)
                context.append(token_id)
            else:
                replacement = sampler.categorical(proposal_probabilities(row, temperature))
                output.append(replacement)
                context.append(replacement)
                state = grammar.advance(state, replacement)
                break
        else:
            if len(output) < max_new_tokens:
                bonus_probs = probabilities(target_rows[-1], grammar.allowed_tokens(before_final), temperature, top_p)
                bonus = sampler.categorical(bonus_probs)
                output.append(bonus)
                context.append(bonus)
                state = grammar.advance(before_final, bonus)
        if output and output[-1] == grammar.eos_id:
            break
    return output
