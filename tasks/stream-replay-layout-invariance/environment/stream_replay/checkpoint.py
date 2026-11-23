"""Host-side JSON checkpoints.

Version 1 stores a two-word Threefry key as ``root`` alongside ``ids``,
``clock`` and ``hidden``. Version 2 adds ``implementation`` and stores the
complete key data in ``root``; the state fields retain their representation.
Each field uses nested JSON lists of the same shape as its array.
"""

import jax
import jax.numpy as jnp
import numpy as np

from .state import create


def dump(state):
    return {
        "version": 2,
        "implementation": str(jax.random.key_impl(state.root)),
        "root": np.asarray(jax.random.key_data(state.root)).tolist(),
        "ids": np.asarray(state.ids).tolist(),
        "clock": np.asarray(state.clock).tolist(),
        "hidden": np.asarray(state.hidden).tolist(),
    }


def load(snapshot):
    if snapshot["version"] not in (1, 2):
        raise ValueError("unsupported snapshot version")
    words = jnp.asarray(snapshot["root"][:2], dtype=jnp.uint32)
    root = jax.random.wrap_key_data(words, impl="threefry2x32")
    return create(root, snapshot["ids"], snapshot["hidden"], snapshot["clock"])
