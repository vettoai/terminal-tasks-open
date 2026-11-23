"""Sampling conventions shared by the generation paths.

Apply the grammar mask, divide allowed logits by temperature, select the
nucleus, and renormalize. Temperature is finite and strictly positive; top_p
is in (0, 1]. Nucleus selection retains the smallest descending-probability
prefix reaching top_p, breaking exact ties by lower token ID. Masked tokens
and negative-infinite logits have zero probability. Every reachable sampling
context must have positive allowed mass. Probability computations use float64.
All random choices belong to the caller-supplied sampler, not the models.
Sampler, CDFSampler and QuantileSampler share the seeded interface, also
available to caller-defined objects without inheritance. Categorical accepts
256 finite nonnegative entry weights with positive total. An absent or None
categorical_resolution denotes normalized-entry-weight selection; 65536 denotes
the uniform quantile grid documented by QuantileSampler. Scoring weights precede
that numerical selection and need not equal returned-token probabilities.
Writable argument storage may be consumed during a call; immutable iterables
and storage unsuitable for an in-place write use private scratch.
"""

import math
import random

import torch


class Sampler:
    """An independent seeded stream, passed to both generators by the caller."""

    categorical_resolution = None

    def __init__(self, seed):
        self.rng = random.Random(seed)

    def bernoulli(self, p):
        """Draw a Boolean with probability p in [0, 1]."""
        return self.rng.random() < float(p)

    def categorical(self, probs):
        """Draw from normalized entry weights without consuming their storage."""
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


class CDFSampler(Sampler):
    """Seeded CPU inverse-CDF sampling with cumulative-weight workspace.

    Categorical uses writable floating-point tensors, arrays and lists as its
    cumulative workspace. Immutable iterables and unsuitable buffers use private
    scratch. Selection always uses the normalized weights supplied on entry.
    Bernoulli uses the same independent stream as categorical.
    """

    def categorical(self, probs):
        """Draw a token ID, consuming safely writable argument storage."""
        entries = probs.tolist() if hasattr(probs, "tolist") else list(probs)
        values = [float(value) for value in entries]
        if len(values) != 256 or any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("Expected 256 finite nonnegative weights")
        total = sum(values)
        if not math.isfinite(total) or total <= 0:
            raise ValueError("Expected positive finite total weight")
        cumulative = []
        running = 0.0
        for value in values:
            running += value / total
            cumulative.append(running)
        if isinstance(probs, list):
            probs[:] = cumulative
        elif isinstance(probs, torch.Tensor):
            writable = not probs.is_inference() or torch.is_inference_mode_enabled()
            if writable and probs.device.type == "cpu" and probs.is_floating_point() and probs.ndim == 1 and probs.is_contiguous() and not probs.requires_grad:
                probs.copy_(torch.tensor(cumulative, dtype=probs.dtype))
        elif hasattr(probs, "flags"):
            if probs.flags.writeable and probs.flags.c_contiguous and probs.dtype.kind == "f":
                probs[:] = cumulative
        draw = self.rng.random()
        for token_id, (value, cutoff) in enumerate(zip(values, cumulative)):
            if value > 0 and draw < cutoff:
                return token_id
        return max(index for index, value in enumerate(values) if value > 0)


class QuantileSampler(Sampler):
    """CPU inverse-CDF selection from packed 16-bit uniform quantiles.

    Snapshot entries as Python float64 values, sum and accumulate normalized
    weights in ascending token-ID order. Select the first positive entry whose
    CDF is strictly greater than k/65536 for a uniform unsigned 16-bit k. The
    last positive entry handles rounding at the end of the CDF. Writable
    storage can hold the CDF; immutable or unsuitable buffers use scratch.
    Bernoulli retains ordinary scalar probability-p semantics.
    """

    categorical_resolution = 65536

    def categorical(self, probs):
        """Draw a token from the finite quantile grid using entry weights."""
        entries = probs.tolist() if hasattr(probs, "tolist") else list(probs)
        values = [float(value) for value in entries]
        if len(values) != 256 or any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("Expected 256 finite nonnegative weights")
        total = 0.0
        for value in values:
            total += value
        if not math.isfinite(total) or total <= 0:
            raise ValueError("Expected positive finite total weight")
        cumulative = []
        running = 0.0
        for value in values:
            running += value / total
            cumulative.append(running)
        if isinstance(probs, list):
            probs[:] = cumulative
        elif isinstance(probs, torch.Tensor):
            writable = not probs.is_inference() or torch.is_inference_mode_enabled()
            if writable and probs.device.type == "cpu" and probs.is_floating_point() and probs.ndim == 1 and probs.is_contiguous() and not probs.requires_grad:
                probs.copy_(torch.tensor(cumulative, dtype=probs.dtype))
        elif hasattr(probs, "flags"):
            if probs.flags.writeable and probs.flags.c_contiguous and probs.dtype.kind == "f":
                probs[:] = cumulative
        quantile = self.rng.getrandbits(16) / 65536
        for token_id, (value, cutoff) in enumerate(zip(values, cumulative)):
            if value > 0 and cutoff > quantile:
                return token_id
        return max(index for index, value in enumerate(values) if value > 0)


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
