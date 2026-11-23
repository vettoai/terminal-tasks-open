"""Wide-accumulation calculus for a fixed-field scalar replay loss."""

from functools import lru_cache, partial

import jax
import jax.numpy as jnp
import numpy as np
from jax import core
from jax._src import dispatch
from jax.interpreters import ad, batching, mlir


PARAMETERS = ("decay", "gain", "bias", "keep")


def outer(left, right):
    return left[..., :, None] * right[..., None, :]


@lru_cache(maxsize=16)
def jet(metadata, flat_bytes, retention_bytes, innovation_bytes, active_bytes):
    shapes, hidden_shape, event_shape = metadata
    flat = np.frombuffer(flat_bytes, np.float32).astype(np.float64)
    retention = np.frombuffer(retention_bytes, np.float32).reshape(event_shape)
    innovation = np.frombuffer(innovation_bytes, np.float32).reshape(event_shape).astype(np.float64)
    active = np.frombuffer(active_bytes, bool).reshape(event_shape[:2])
    batch, width = hidden_shape
    dimension = len(flat)
    params, basis = {}, {}
    cursor = 0
    for name, shape in zip(PARAMETERS, shapes):
        size = int(np.prod(shape))
        params[name] = flat[cursor:cursor + size].reshape(shape)
        derivative = np.zeros((batch, width, dimension), np.float64)
        if shape:
            derivative[:, np.arange(width), cursor + np.arange(width)] = 1
        else:
            derivative[..., cursor] = 1
        basis[name] = derivative
        cursor += size
    hidden = flat[cursor:cursor + batch * width].reshape(hidden_shape).copy()
    jacobian = np.zeros((batch, width, dimension), np.float64)
    for row, feature in np.ndindex(hidden_shape):
        jacobian[row, feature, cursor + row * width + feature] = 1
    cursor += batch * width
    events = flat[cursor:].reshape(event_shape)
    curvature = np.zeros((*hidden_shape, dimension, dimension), np.float64)
    gradient = np.zeros(dimension, np.float64)
    hessian = np.zeros((dimension, dimension), np.float64)
    value = 0.0
    denominator = max(int(active.sum()) * width, 1)
    keep = params["keep"]

    def accumulate(weight, current, first, second):
        nonlocal value, gradient, hessian
        value += np.sum(weight * current**2)
        gradient += 2 * np.sum((weight * current)[..., None] * first, axis=(0, 1))
        hessian += 2 * np.sum(weight[..., None, None] * (outer(first, first) + current[..., None, None] * second), axis=(0, 1))

    for moment, event in enumerate(events):
        event_basis = np.zeros_like(jacobian)
        for row, feature in np.ndindex(hidden_shape):
            event_basis[row, feature, cursor + moment * batch * width + row * width + feature] = 1
        position = params["decay"] * hidden + params["gain"] * event + params["bias"] + 0.2 * (2 * innovation[moment] - 1)
        first = params["decay"][..., None] * jacobian + hidden[..., None] * basis["decay"] + event[..., None] * basis["gain"] + params["gain"][..., None] * event_basis + basis["bias"]
        second = params["decay"][..., None, None] * curvature + outer(basis["decay"], jacobian) + outer(jacobian, basis["decay"]) + outer(basis["gain"], event_basis) + outer(event_basis, basis["gain"])
        proposal = np.tanh(position)
        exponential = np.exp(-2 * np.abs(position))
        slope = 4 * exponential / (1 + exponential)**2
        proposal_first = slope[..., None] * first
        proposal_second = slope[..., None, None] * second - (2 * proposal * slope)[..., None, None] * outer(first, first)
        gate = (retention[moment] < keep).astype(np.float64)
        next_first = gate[..., None] * (proposal_first / keep - proposal[..., None] * basis["keep"] / keep**2)
        next_second = gate[..., None, None] * (
            proposal_second / keep
            - (outer(proposal_first, basis["keep"]) + outer(basis["keep"], proposal_first)) / keep**2
            + 2 * proposal[..., None, None] * outer(basis["keep"], basis["keep"]) / keep**3
        )
        mask = active[moment, :, None]
        hidden = np.where(mask, gate * proposal / keep, hidden)
        jacobian = np.where(mask[..., None], next_first, jacobian)
        curvature = np.where(mask[..., None, None], next_second, curvature)
        accumulate(np.broadcast_to(mask, hidden_shape) / denominator, hidden, jacobian, curvature)
    accumulate(np.full(hidden_shape, 0.07), hidden, jacobian, curvature)
    return value, gradient, hessian


def host_operation(flat, retention, innovation, active, *direction, metadata, mode):
    value, gradient, hessian = jet(metadata, np.asarray(flat, np.float32).tobytes(), np.asarray(retention, np.float32).tobytes(), np.asarray(innovation, np.float32).tobytes(), np.asarray(active, bool).tobytes())
    result = value if mode == "value" else gradient if mode == "gradient" else hessian @ np.asarray(direction[0], np.float64)
    return np.asarray(result, np.float32)


value_primitive = core.Primitive("stream_replay_loss")
gradient_primitive = core.Primitive("stream_replay_loss_gradient")
hvp_primitive = core.Primitive("stream_replay_loss_hvp")


def lower(context, *values, metadata, mode):
    result = context.avals_out[0]
    def callback(*arguments):
        return jax.pure_callback(partial(host_operation, metadata=metadata, mode=mode), jax.ShapeDtypeStruct(result.shape, result.dtype), *arguments, vmap_method="sequential")
    return mlir.lower_fun(callback, multiple_results=False)(context, *values)


for primitive, mode in ((value_primitive, "value"), (gradient_primitive, "gradient"), (hvp_primitive, "hvp")):
    primitive.def_impl(partial(dispatch.apply_primitive, primitive))
    primitive.def_abstract_eval(lambda flat, *values, mode=mode, **params: core.ShapedArray(() if mode == "value" else flat.shape, np.dtype("float32")))
    mlir.register_lowering(primitive, partial(lower, mode=mode))


def batch(primitive, values, axes, *, metadata):
    size = next(value.shape[axis] for value, axis in zip(values, axes) if axis is not batching.not_mapped)
    aligned = tuple(batching.bdim_at_front(value, axis, size) for value, axis in zip(values, axes))
    return jax.lax.map(lambda arguments: primitive.bind(*arguments, metadata=metadata), aligned), 0


for primitive in (value_primitive, gradient_primitive, hvp_primitive):
    batching.primitive_batchers[primitive] = partial(batch, primitive)


def value_jvp(primals, tangents, *, metadata):
    gradient = gradient_primitive.bind(*primals, metadata=metadata)
    return value_primitive.bind(*primals, metadata=metadata), jnp.vdot(gradient, ad.instantiate_zeros(tangents[0]))


def gradient_jvp(primals, tangents, *, metadata):
    return gradient_primitive.bind(*primals, metadata=metadata), hvp_primitive.bind(*primals, ad.instantiate_zeros(tangents[0]), metadata=metadata)


ad.primitive_jvps[value_primitive] = value_jvp
ad.primitive_jvps[gradient_primitive] = gradient_jvp


def loss(params, hidden, events, active, retention, innovation):
    parameters = [jnp.asarray(params[name], jnp.float32) for name in PARAMETERS]
    metadata = (tuple(value.shape for value in parameters), hidden.shape, events.shape)
    flat = jnp.concatenate([*(value.reshape(-1) for value in parameters), hidden.reshape(-1), events.reshape(-1)])
    return value_primitive.bind(flat, retention, innovation, active, metadata=metadata)
