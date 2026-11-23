"""Scalar random addresses used by the replay cell.

An address consists of the uint32 words [0x5354524D, id_low, id_high,
event_low, event_high, site, feature], in that order. Each word is folded
into the supplied scalar typed root. The resulting key draws one scalar
float32 uniform in [0, 1) with that root's implementation. Retention uses
site 17 and innovation uses site 29. Features are addressed individually;
adding a feature does not change an existing feature's draw.
"""

import jax
import jax.numpy as jnp


DOMAIN = 0x5354524D
RETENTION = 17
INNOVATION = 29


def scalar_uniform(root, identity, event, site, feature):
    key = root
    for word in (DOMAIN, identity[0], identity[1], event[0], event[1], site, feature):
        key = jax.random.fold_in(key, jnp.asarray(word, dtype=jnp.uint32))
    return jax.random.uniform(key, shape=(), dtype=jnp.float32, minval=0, maxval=1)
