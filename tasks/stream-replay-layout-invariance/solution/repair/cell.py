"""Retention-gated recurrent cell."""

import jax
import jax.numpy as jnp
from jax import lax

from .precision import affine_pair, weighted_apply, weighted_slope


def affine(decay, hidden, gain, events, bias, noise):
    ordinary = decay * hidden + gain * events + bias + noise
    high, low = affine_pair(*jax.tree.map(lax.stop_gradient, (decay, hidden, gain, events, bias, noise)))
    return ordinary + lax.stop_gradient(high - ordinary), low


@jax.custom_jvp
def proposal(decay, hidden, gain, events, bias, noise):
    high, low = affine(decay, hidden, gain, events, bias, noise)
    half = jnp.exp(-jnp.abs(high)) * jnp.exp(-jnp.sign(high) * low)
    tail = jnp.sign(high) * (1 - 2 * half * half / (1 + half * half))
    return jnp.where(jnp.abs(high) > 4, tail, jnp.tanh(high + low))


@proposal.defjvp
def proposal_jvp(primals, tangents):
    decay, hidden, gain, events, bias, noise = primals
    decay_dot, hidden_dot, gain_dot, events_dot, bias_dot, noise_dot = tangents
    high, low = affine(*primals)
    result = proposal(*primals)
    tangent = (
        weighted_apply(weighted_slope(hidden, high, low), decay_dot)
        + weighted_apply(weighted_slope(decay, high, low), hidden_dot)
        + weighted_apply(weighted_slope(events, high, low), gain_dot)
        + weighted_apply(weighted_slope(gain, high, low), events_dot)
        + weighted_apply(weighted_slope(jnp.ones_like(high), high, low), bias_dot)
        + weighted_apply(weighted_slope(jnp.ones_like(high), high, low), noise_dot)
    )
    return result, tangent


def update(params, hidden, events, retention, innovation):
    value = proposal(params["decay"], hidden, params["gain"], events, params["bias"], 0.2 * (2 * innovation - 1))
    return jnp.where(retention < params["keep"], value / params["keep"], 0)
