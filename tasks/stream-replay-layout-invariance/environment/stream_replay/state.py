"""State carried between event-stream chunks."""

from typing import NamedTuple

import jax
import jax.numpy as jnp


class StreamState(NamedTuple):
    root: jax.Array
    ids: jax.Array
    clock: jax.Array
    hidden: jax.Array


def create(root, ids, hidden, clock=None):
    ids = jnp.asarray(ids, dtype=jnp.uint32)
    hidden = jnp.asarray(hidden, dtype=jnp.float32)
    if ids.ndim != 2 or ids.shape[1] != 2:
        raise ValueError("ids must have shape [batch, 2]")
    if hidden.ndim != 2 or hidden.shape[0] != ids.shape[0] or hidden.shape[1] == 0:
        raise ValueError("hidden must have shape [batch, width] with width > 0")
    if root.shape != () or not jax.dtypes.issubdtype(root.dtype, jax.dtypes.prng_key):
        raise ValueError("root must be a scalar typed key")
    if str(jax.random.key_impl(root)) not in {"threefry2x32", "rbg"}:
        raise ValueError("unsupported root implementation")
    clock = jnp.zeros_like(ids) if clock is None else jnp.asarray(clock, dtype=jnp.uint32)
    if clock.shape != ids.shape:
        raise ValueError("clock must have shape [batch, 2]")
    return StreamState(root, ids, clock, hidden)


def select(state, rows):
    rows = jnp.asarray(rows)
    return StreamState(state.root, state.ids[rows], state.clock[rows], state.hidden[rows])


def add_ticks(clock, ticks):
    ticks = jnp.asarray(ticks, dtype=jnp.uint32)
    low = clock[..., 0] + ticks
    high = clock[..., 1] + (low < clock[..., 0]).astype(jnp.uint32)
    return jnp.stack((low, high), axis=-1)
