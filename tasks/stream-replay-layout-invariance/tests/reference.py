"""Independent scalar fields, NumPy replay and fixed-field derivatives."""

from functools import lru_cache

import jax
import jax.numpy as jnp
import numpy as np


@jax.jit
def scalar_field(root, identity, event, site, feature):
    key = root
    for word in (0x5354524D, identity[0], identity[1], event[0], event[1], site, feature):
        key = jax.random.fold_in(key, jnp.asarray(word, jnp.uint32))
    return jax.random.uniform(key, (), jnp.float32, minval=0, maxval=1)


def root_key(state):
    return jax.random.wrap_key_data(jnp.asarray(state["root"], jnp.uint32), impl=state["implementation"])


def fields(state, active):
    return cached_fields(
        state["implementation"], np.asarray(state["root"], np.uint32).tobytes(),
        np.asarray(state["ids"], np.uint32).tobytes(),
        np.asarray(state["clock"], np.uint32).tobytes(),
        np.asarray(active, bool).tobytes(), tuple(active.shape), state["hidden"].shape[1],
    )


@lru_cache(maxsize=128)
def cached_fields(implementation, key_bytes, id_bytes, clock_bytes, mask_bytes, shape, width):
    root = jax.random.wrap_key_data(jnp.asarray(np.frombuffer(key_bytes, np.uint32)), impl=implementation)
    identities = np.frombuffer(id_bytes, np.uint32).reshape(shape[1], 2)
    clocks = np.frombuffer(clock_bytes, np.uint32).reshape(shape[1], 2)
    mask = np.frombuffer(mask_bytes, bool).reshape(shape)
    retention = np.zeros((*shape, width), np.float32)
    innovation = np.zeros_like(retention)
    for row in range(shape[1]):
        number = int(clocks[row, 0]) + (int(clocks[row, 1]) << 32)
        for moment in range(shape[0]):
            if mask[moment, row]:
                address = np.array([number & 0xFFFFFFFF, number >> 32], np.uint32)
                for feature in range(width):
                    retention[moment, row, feature] = scalar_field(root, identities[row], address, 17, feature)
                    innovation[moment, row, feature] = scalar_field(root, identities[row], address, 29, feature)
                number = (number + 1) & 0xFFFFFFFFFFFFFFFF
    return retention, innovation


def clock_after(state, active):
    clocks = np.asarray(state["clock"], np.uint32)
    result = np.empty_like(clocks)
    for row, count in enumerate(np.sum(active, axis=0)):
        number = (int(clocks[row, 0]) + (int(clocks[row, 1]) << 32) + int(count)) & 0xFFFFFFFFFFFFFFFF
        result[row] = [number & 0xFFFFFFFF, number >> 32]
    return result


def forward(case):
    state, params, events, active = (case[name] for name in ("state", "params", "events", "active"))
    retention, innovation = fields(state, active)
    hidden = np.array(state["hidden"], dtype=np.float32, copy=True)
    history = np.empty(events.shape, np.float32)
    for moment in range(len(events)):
        proposal = np.tanh(
            params["decay"] * hidden + params["gain"] * events[moment] + params["bias"]
            + np.float32(0.2) * (np.float32(2) * innovation[moment] - np.float32(1))
        )
        proposed = np.where(retention[moment] < params["keep"], proposal / params["keep"], np.float32(0))
        hidden = np.where(active[moment, :, None], proposed, hidden)
        history[moment] = hidden
    final = {name: np.array(value, copy=True) if name != "implementation" else value for name, value in state.items()}
    final["clock"] = clock_after(state, active)
    final["hidden"] = hidden
    numerator = np.sum(np.where(active[..., None], history * history, np.float32(0)), dtype=np.float32)
    denominator = max(int(np.sum(active)) * hidden.shape[1], 1)
    value = numerator / np.float32(denominator) + np.float32(0.07) * np.sum(hidden * hidden, dtype=np.float32)
    return {"state": final, "history": history, "value": value}


def derivatives(case, direction=None):
    retention, innovation = (jnp.asarray(value) for value in fields(case["state"], case["active"]))
    mask = jnp.asarray(case["active"])
    hidden = jnp.asarray(case["state"]["hidden"])
    events = jnp.asarray(case["events"])
    params = jax.tree.map(jnp.asarray, case["params"])

    def fixed_loss(parameters, initial, inputs):
        def step(current, items):
            event, active, keep_field, noise = items
            proposal = jnp.tanh(
                parameters["decay"] * current + parameters["gain"] * event + parameters["bias"]
                + 0.2 * (2 * noise - 1)
            )
            current = jnp.where(active[:, None], jnp.where(keep_field < parameters["keep"], proposal / parameters["keep"], 0), current)
            return current, current

        final, history = jax.lax.scan(step, initial, (inputs, mask, retention, innovation))
        return jnp.sum(jnp.where(mask[..., None], history ** 2, 0)) / jnp.maximum(mask.sum() * initial.shape[1], 1) + 0.07 * jnp.sum(final ** 2)

    value, gradients = jax.jit(jax.value_and_grad(fixed_loss, argnums=(0, 1, 2)))(params, hidden, events)
    result = {"value": value, "params": gradients[0], "hidden": gradients[1], "events": gradients[2]}
    if direction is not None:
        result["hvp"] = jax.jit(lambda parameters, tangent: jax.jvp(
            jax.grad(lambda current: fixed_loss(current, hidden, events)), (parameters,), (tangent,)
        )[1])(params, jax.tree.map(jnp.asarray, direction))
    return jax.tree.map(np.asarray, result)
