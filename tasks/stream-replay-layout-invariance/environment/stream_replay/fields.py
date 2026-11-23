"""Retention and innovation fields for a chunk."""

import jax
import jax.numpy as jnp

from .address import INNOVATION, RETENTION, scalar_uniform
from .state import add_ticks


def sample(root, ids, clocks, width):
    features = jnp.arange(width, dtype=jnp.uint32)

    def at_time(clock_rows):
        def at_stream(identity, clock):
            def at_feature(feature):
                return (
                    scalar_uniform(root, identity, clock, RETENTION, feature),
                    scalar_uniform(root, identity, clock, INNOVATION, feature),
                )

            return jax.vmap(at_feature)(features)

        return jax.vmap(at_stream)(ids, clock_rows)

    return jax.vmap(at_time)(clocks)


def for_chunk(state, active):
    offsets = jnp.arange(active.shape[0], dtype=jnp.uint32)
    clocks = jax.vmap(lambda offset: add_ticks(state.clock, offset))(offsets)
    return sample(state.root, state.ids, clocks, state.hidden.shape[1])
