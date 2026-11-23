"""Sampling conventions shared by the generation paths.

Apply the grammar mask, divide allowed logits by temperature, select the
nucleus, and renormalize. Temperature is finite and strictly positive; top_p
is in (0, 1]. Nucleus selection retains the smallest descending-probability
prefix reaching top_p, breaking exact ties by lower token ID. Masked tokens
and negative-infinite logits have zero probability. Every reachable sampling
context must have positive allowed mass. Probability computations use float64.
All random choices belong to the caller-supplied Sampler, not the models.
"""

import math
import random

import torch


class Sampler:
    """An independent seeded stream, passed to both generators by the caller."""

    def __init__(self, seed):
        self.rng = random.Random(seed)

    def bernoulli(self, p):
        """Draw a Boolean with probability p in [0, 1]."""
        return self.rng.random() < float(p)

    def categorical(self, probs):
        """Draw a token ID from a length-256 nonnegative probability vector."""
        values = probs.tolist() if hasattr(probs, "tolist") else list(probs)
        draw = self.rng.random() * sum(values)
        cumulative = 0.0
        last = 0
        for token_id, probability in enumerate(values):
            if probability > 0:
                last = token_id
                cumulative += probability
                if draw < cumulative:
                    return token_id
        return last


def probabilities(logits, mask, temperature, top_p):
    """Return the normalized masked/tempered/nucleus distribution.

    The logits and mask have shape [256]. Negative-infinite logits represent
    zero model support. An empty allowed support or unsupported parameter is
    an error. Ties are stable in vocabulary-ID order.
    """
    if not math.isfinite(temperature) or temperature <= 0 or not 0 < top_p <= 1:
        raise ValueError("Expected temperature > 0 and 0 < top_p <= 1")
    scores = logits.to(torch.float64).masked_fill(~mask, -torch.inf) / temperature
    probs = torch.softmax(scores, dim=-1)
    if not torch.isfinite(probs).all():
        raise ValueError("No positive allowed model mass")
    if top_p < 1:
        order = torch.argsort(probs, descending=True, stable=True)
        ranked = probs[order]
        keep = (torch.cumsum(ranked, dim=0) - ranked) < top_p
        filtered = torch.zeros_like(probs)
        filtered[order[keep]] = ranked[keep]
        probs = filtered / filtered.sum()
    return probs


def proposal_probabilities(logits, temperature):
    """Score vocabulary entries from a temperature-scaled logit row."""
    return torch.softmax(logits.to(torch.float64) / temperature, dim=-1)
