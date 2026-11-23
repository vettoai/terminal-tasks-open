"""Local high-precision kernels for scaled activation sensitivities."""

from functools import partial

import jax
import jax.numpy as jnp
import numpy as np
from jax import core
from jax._src import dispatch
from jax.interpreters import ad, batching, mlir
from jaxlib.mlir import ir
from jaxlib.mlir.dialects import stablehlo


slope_primitive = core.Primitive("stream_replay_scaled_slope")
slope_dot_primitive = core.Primitive("stream_replay_scaled_slope_dot")
affine_primitive = core.Primitive("stream_replay_affine_pair")
affine_primitive.multiple_results = True


def abstract(*values):
    return core.ShapedArray(values[0].shape, np.dtype("float32"))


def lower(context, *values, directional=False):
    shape = context.avals_in[0].shape
    wide = ir.RankedTensorType.get(shape, ir.F64Type.get())
    narrow = ir.RankedTensorType.get(shape, ir.F32Type.get())
    operands = [stablehlo.ConvertOp(wide, value).result for value in values]

    def constant(value):
        return mlir.ir_constant(np.full(shape, value, np.float64))

    def add(left, right):
        return stablehlo.AddOp(left, right).result

    def multiply(left, right):
        return stablehlo.MulOp(left, right).result

    factor, high, low = operands[:3]
    position = add(high, low)
    exponential = stablehlo.ExpOp(multiply(constant(-2), stablehlo.AbsOp(position).result)).result
    denominator = add(constant(1), exponential)
    slope = stablehlo.DivOp(multiply(constant(4), exponential), multiply(denominator, denominator)).result
    result = multiply(slope, factor)
    if directional:
        factor_dot, high_dot, low_dot = operands[3:]
        curvature = multiply(multiply(constant(-2), stablehlo.TanhOp(position).result), result)
        result = add(multiply(slope, factor_dot), multiply(curvature, add(high_dot, low_dot)))
    return [stablehlo.ConvertOp(narrow, result).result]


for primitive, directional in ((slope_primitive, False), (slope_dot_primitive, True)):
    primitive.def_impl(partial(dispatch.apply_primitive, primitive))
    primitive.def_abstract_eval(abstract)
    mlir.register_lowering(primitive, partial(lower, directional=directional))


def lower_affine(context, *values):
    shape = context.avals_in[0].shape
    wide = ir.RankedTensorType.get(shape, ir.F64Type.get())
    narrow = ir.RankedTensorType.get(shape, ir.F32Type.get())
    decay, hidden, gain, events, bias, noise = [stablehlo.ConvertOp(wide, value).result for value in values]
    first = stablehlo.MulOp(decay, hidden).result
    second = stablehlo.MulOp(gain, events).result
    total = stablehlo.AddOp(stablehlo.AddOp(stablehlo.AddOp(first, second).result, bias).result, noise).result
    high = stablehlo.ConvertOp(narrow, total).result
    residual = stablehlo.SubtractOp(total, stablehlo.ConvertOp(wide, high).result).result
    return [high, stablehlo.ConvertOp(narrow, residual).result]


affine_primitive.def_impl(partial(dispatch.apply_primitive, affine_primitive))
affine_primitive.def_abstract_eval(lambda *values: (abstract(*values), abstract(*values)))
mlir.register_lowering(affine_primitive, lower_affine)


def batch(primitive, values, axes):
    size = next(value.shape[axis] for value, axis in zip(values, axes) if axis is not batching.not_mapped)
    aligned = [batching.bdim_at_front(value, axis, size) for value, axis in zip(values, axes)]
    return primitive.bind(*aligned), (0, 0) if primitive.multiple_results else 0


batching.primitive_batchers[slope_primitive] = partial(batch, slope_primitive)
batching.primitive_batchers[slope_dot_primitive] = partial(batch, slope_dot_primitive)
batching.primitive_batchers[affine_primitive] = partial(batch, affine_primitive)


def slope_jvp(primals, tangents):
    tangents = [ad.instantiate_zeros(value) for value in tangents]
    return slope_primitive.bind(*primals), slope_dot_primitive.bind(*primals, *tangents)


ad.primitive_jvps[slope_primitive] = slope_jvp


def weighted_slope(factor, high, low):
    return slope_primitive.bind(*jnp.broadcast_arrays(factor, high, low))


def affine_pair(*values):
    return affine_primitive.bind(*jnp.broadcast_arrays(*values))


linear_primitive = core.Primitive("stream_replay_linear_product")
reduction_primitive = core.Primitive("stream_replay_product_reduction")
reduction_dot_primitive = core.Primitive("stream_replay_product_reduction_dot")


def broadcast_dimensions(full_shape, small_shape, batch_ndim):
    intrinsic = len(small_shape) - batch_ndim
    return tuple(range(batch_ndim)) + tuple(range(len(full_shape) - intrinsic, len(full_shape)))


def lower_linear(context, coefficient, tangent, *, batch_ndim):
    result_type = mlir.aval_to_ir_type(context.avals_out[0])
    dimensions = broadcast_dimensions(context.avals_in[0].shape, context.avals_in[1].shape, batch_ndim)
    tangent = stablehlo.BroadcastInDimOp(result_type, tangent, mlir.dense_int_array(dimensions)).result
    return [stablehlo.MulOp(coefficient, tangent).result]


def lower_reduction(context, *values, target_shape, batch_ndim, directional=False):
    full_shape = context.avals_in[0].shape
    wide = ir.RankedTensorType.get(full_shape, ir.F64Type.get())
    operands = [stablehlo.ConvertOp(wide, value).result for value in values]
    product = stablehlo.MulOp(operands[0], operands[1]).result
    if directional:
        first = stablehlo.MulOp(operands[2], operands[1]).result
        second = stablehlo.MulOp(operands[0], operands[3]).result
        product = stablehlo.AddOp(first, second).result
    retained = broadcast_dimensions(full_shape, target_shape, batch_ndim)
    axes = tuple(axis for axis in range(len(full_shape)) if axis not in retained)
    if axes:
        result_type = ir.RankedTensorType.get(target_shape, ir.F64Type.get())
        reduction = stablehlo.ReduceOp([result_type], [product], [mlir.ir_constant(np.asarray(0, np.float64))], mlir.dense_int_array(axes))
        scalar_type = ir.RankedTensorType.get((), ir.F64Type.get())
        block = reduction.regions[0].blocks.append(scalar_type, scalar_type)
        with ir.InsertionPoint(block):
            stablehlo.ReturnOp([stablehlo.AddOp(*block.arguments).result])
        product = reduction.result
    return [stablehlo.ConvertOp(mlir.aval_to_ir_type(context.avals_out[0]), product).result]


linear_primitive.def_impl(partial(dispatch.apply_primitive, linear_primitive))
linear_primitive.def_abstract_eval(lambda coefficient, tangent, **params: coefficient)
mlir.register_lowering(linear_primitive, lower_linear)
for primitive, directional in ((reduction_primitive, False), (reduction_dot_primitive, True)):
    primitive.def_impl(partial(dispatch.apply_primitive, primitive))
    primitive.def_abstract_eval(lambda *values, target_shape, **params: core.ShapedArray(target_shape, np.dtype("float32")))
    mlir.register_lowering(primitive, partial(lower_reduction, directional=directional))


def linear_batch(primitive, values, axes, *, batch_ndim, **params):
    size = next(value.shape[axis] for value, axis in zip(values, axes) if axis is not batching.not_mapped)
    aligned = [batching.bdim_at_front(value, axis, size) for value, axis in zip(values, axes)]
    if "target_shape" in params:
        params["target_shape"] = (size, *params["target_shape"])
    return primitive.bind(*aligned, batch_ndim=batch_ndim + 1, **params), 0


for primitive in (linear_primitive, reduction_primitive, reduction_dot_primitive):
    batching.primitive_batchers[primitive] = partial(linear_batch, primitive)


def linear_jvp(primals, tangents, *, batch_ndim):
    coefficient, tangent = primals
    coefficient_dot, tangent_dot = [ad.instantiate_zeros(value) for value in tangents]
    result = linear_primitive.bind(coefficient, tangent, batch_ndim=batch_ndim)
    directional = linear_primitive.bind(coefficient_dot, tangent, batch_ndim=batch_ndim) + linear_primitive.bind(coefficient, tangent_dot, batch_ndim=batch_ndim)
    return result, directional


def linear_transpose(cotangent, coefficient, tangent, *, batch_ndim):
    if isinstance(cotangent, ad.Zero):
        return tuple(ad.Zero(value.aval) if ad.is_undefined_primal(value) else None for value in (coefficient, tangent))
    coefficient_gradient = linear_primitive.bind(cotangent, tangent, batch_ndim=batch_ndim) if ad.is_undefined_primal(coefficient) else None
    tangent_gradient = reduction_primitive.bind(coefficient, cotangent, target_shape=tangent.aval.shape, batch_ndim=batch_ndim) if ad.is_undefined_primal(tangent) else None
    return coefficient_gradient, tangent_gradient


def reduction_jvp(primals, tangents, **params):
    tangents = [ad.instantiate_zeros(value) for value in tangents]
    return reduction_primitive.bind(*primals, **params), reduction_dot_primitive.bind(*primals, *tangents, **params)


ad.primitive_jvps[linear_primitive] = linear_jvp
ad.primitive_transposes[linear_primitive] = linear_transpose
ad.primitive_jvps[reduction_primitive] = reduction_jvp


def weighted_apply(coefficient, tangent):
    return linear_primitive.bind(coefficient, tangent, batch_ndim=0)
