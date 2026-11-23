"""Chunk replay and its training objective.

Ensembles carry member-specific roots, IDs, clocks, hidden values, events and
activity. Parameter leaves may be shared or mapped independently. Callers use
normal JAX in_axes/out_axes to place ensemble dimensions outside the public
time/batch/feature shapes, including non-leading storage axes and two nested
ensemble dimensions. Floating replay outputs, objective first derivatives and
parameter Hessian-vector products have independent scalar-member semantics
with fixed random draws. For a sum of member objectives, shared-leaf gradients
and products accumulate the member contributions; mapped leaves retain their
ensemble positions. Rematerialization changes recomputation, not this meaning.
"""

import jax
import jax.numpy as jnp

from . import cell, fields
from .state import StreamState, add_ticks


def advance(params, state, events, active, *, remat=False):
    events = jnp.asarray(events, dtype=jnp.float32)
    active = jnp.asarray(active, dtype=jnp.bool_)
    if events.ndim != 3 or events.shape[1:] != state.hidden.shape:
        raise ValueError("events must have shape [time, batch, width]")
    if active.shape != events.shape[:2]:
        raise ValueError("active must match the time and batch dimensions")
    if events.shape[0] == 0:
        return state, jnp.empty(events.shape, dtype=jnp.float32)
    retention, innovation = fields.for_chunk(state, active)

    def step(hidden, inputs):
        event, mask, keep_field, noise_field = inputs
        proposed = cell.update(params, hidden, event, keep_field, noise_field)
        hidden = jnp.where(mask[:, None], proposed, hidden)
        return hidden, hidden

    replay_step = jax.checkpoint(step) if remat else step
    hidden, history = jax.lax.scan(
        replay_step, state.hidden, (events, active, retention, innovation)
    )
    clock = add_ticks(state.clock, active.sum(axis=0, dtype=jnp.uint32))
    return StreamState(state.root, state.ids, clock, hidden), history


def objective(params, state, events, active, *, remat=False):
    final, history = advance(params, state, events, active, remat=remat)
    numerator = jnp.sum(jnp.where(active[..., None], history * history, 0))
    denominator = jnp.maximum(jnp.sum(active) * state.hidden.shape[1], 1)
    return numerator / denominator + 0.07 * jnp.sum(final.hidden * final.hidden)
