"""Retention-gated recurrent cell."""

import jax.numpy as jnp


def update(params, hidden, events, retention, innovation):
    proposal = jnp.tanh(
        params["decay"] * hidden
        + params["gain"] * events
        + params["bias"]
        + 0.2 * (2 * innovation - 1)
    )
    return jnp.where(retention < params["keep"], proposal / params["keep"], 0)
