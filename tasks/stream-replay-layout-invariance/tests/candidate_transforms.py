"""Numerical invocation machinery for batched transformed replay calls."""

import jax
import jax.numpy as jnp


def calibration(replay, request):
    remat = request.get("remat", False)
    chunked = request.get("chunked", False)

    def forward(params, hidden, events, root, ids, clock, active):
        state = replay.create(root, ids, hidden, clock)
        if chunked:
            histories = []
            for start, stop in ((0, 1), (1, 2), (2, 3)):
                state, history = replay.advance(params, state, events[start:stop], active[start:stop], remat=remat)
                histories.append(history)
            history = jnp.concatenate(histories)
        else:
            state, history = replay.advance(params, state, events, active, remat=remat)
        return state, history

    def loss(params, hidden, events, root, ids, clock, active):
        if not chunked:
            return replay.objective(params, replay.create(root, ids, hidden, clock), events, active, remat=remat)
        final, history = forward(params, hidden, events, root, ids, clock, active)
        return jnp.sum(jnp.where(active[..., None], history**2, 0)) / jnp.maximum(active.sum() * hidden.shape[-1], 1) + 0.07 * jnp.sum(final.hidden**2)

    def evaluate(params, hidden, events, root, ids, clock, active, direction):
        arguments = (params, hidden, events, root, ids, clock, active)
        value, gradients = jax.value_and_grad(loss, argnums=(0, 1, 2))(*arguments)
        hvp = jax.jvp(lambda current: jax.grad(loss)(current, *arguments[1:]), (params,), (direction,))[1]
        final, history = forward(*arguments)
        return {
            "forward": {"hidden": final.hidden, "clock": final.clock, "ids": final.ids, "root": jax.random.key_data(final.root), "history": history, "implementation_matches": jnp.asarray(str(jax.random.key_impl(final.root)) == str(jax.random.key_impl(root)))},
            "derivatives": {"value": value, "params": gradients[0], "hidden": gradients[1], "events": gradients[2], "hvp": hvp},
        }

    for level in range(request.get("depth", 0)):
        evaluate = jax.vmap(evaluate, in_axes=(None, None, None, 0, None, None, None, None))
    compiled = jax.jit(evaluate)
    results = []
    for item in request["items"]:
        case = item["case"]
        state = case["state"]
        root = jax.random.wrap_key_data(jnp.asarray(item.get("roots", state["root"]), jnp.uint32), impl=state["implementation"])
        outputs = []
        for direction in item["directions"]:
            outputs.append(compiled(
                jax.tree.map(jnp.asarray, case["params"]), jnp.asarray(state["hidden"]),
                jnp.asarray(case["events"]), root, jnp.asarray(state["ids"]), jnp.asarray(state["clock"]),
                jnp.asarray(case["active"]), jax.tree.map(jnp.asarray, direction),
            ))
        results.append(outputs)
    return results


def ensemble(replay, request):
    outputs = []
    depth, remat = request.get("depth", 2), request.get("remat", False)
    for item in request["items"]:
        shared = set(item["shared"])

        def positions(name, value=None):
            if name == "params":
                base_rank = value.ndim - 2
                return (base_rank, base_rank + 1) if depth == 2 else (base_rank,)
            table = {"ids": (1, 3), "clock": (2, 3), "hidden": (1, 3), "events": (2, 4), "active": (1, 3)}
            if depth == 2:
                return table[name]
            return ({"ids": 1, "clock": 2, "hidden": 1, "events": 3, "active": 1}[name],)

        def pack(value, axes):
            value = jnp.asarray(value)
            if depth == 1:
                return jnp.moveaxis(value.reshape((6, *value.shape[2:])), 0, axes[0])
            return jnp.moveaxis(value, (0, 1), axes)

        def unpack(value, axes):
            if depth == 1:
                value = jnp.moveaxis(value, axes[0], 0)
                return value.reshape((2, 3, *value.shape[1:]))
            return jnp.moveaxis(value, axes, (0, 1))

        parameter_axes = {name: None if name in shared else positions("params", value) for name, value in item["params"].items()}
        params = {name: jnp.asarray(value) if parameter_axes[name] is None else pack(value, parameter_axes[name]) for name, value in item["params"].items()}
        state = item["state"]
        roots = jax.random.wrap_key_data(jnp.asarray(state["root"], jnp.uint32), impl=state["implementation"])
        if depth == 1:
            roots = roots.reshape((6,))
        packed = {name: pack(state[name] if name in state else item[name], positions(name)) for name in ("ids", "clock", "hidden", "events", "active")}

        def scalar(parameters, key, ids, clock, hidden, events, active):
            current = replay.create(key, ids, hidden, clock)
            final, history = replay.advance(parameters, current, events, active, remat=remat)
            value = replay.objective(parameters, current, events, active, remat=remat)
            return {"hidden": final.hidden, "history": history, "ids": final.ids, "clock": final.clock, "root": final.root, "value": value}

        def axes_at(level):
            def axis(axes):
                if axes is None:
                    return None
                return axes[level] - (1 if level == 1 and axes[0] < axes[1] else 0)
            return ({name: axis(axes) for name, axes in parameter_axes.items()}, 0, *(axis(positions(name)) for name in ("ids", "clock", "hidden", "events", "active")))

        out_axes = {"hidden": 1, "history": 2, "ids": 1, "clock": 1, "root": 0, "value": 0}
        mapped = jax.vmap(scalar, in_axes=axes_at(depth - 1), out_axes=out_axes)
        if depth == 2:
            mapped = jax.vmap(mapped, in_axes=axes_at(0), out_axes=out_axes)

        def canonical(result):
            restored = {}
            for name, value in result.items():
                if name in {"root", "value"}:
                    restored[name] = value if depth == 2 else value.reshape((2, 3, *value.shape[1:]))
                else:
                    axis = 2 if name == "history" else 1
                    restored[name] = unpack(value, (axis, axis + 1) if depth == 2 else (axis,))
            return restored

        def full(parameters, hidden, events, keys, identities, clocks, masks):
            return canonical(mapped(parameters, keys, identities, clocks, hidden, events, masks))

        if not request.get("linear", False):
            result = jax.jit(full)(params, packed["hidden"], packed["events"], roots, packed["ids"], packed["clock"], packed["active"])
            implementation = str(jax.random.key_impl(result["root"]))
            result["root"] = jax.random.key_data(result["root"])
            outputs.append({"implementation": implementation, **result})
            continue

        def calculate(parameters, hidden, events, tangent, cotangent, keys, identities, clocks, masks):
            def floating(current_params, current_hidden, current_events):
                result = full(current_params, current_hidden, current_events, keys, identities, clocks, masks)
                return {"hidden": result["hidden"], "history": result["history"]}
            def objective(current_params):
                return full(current_params, hidden, events, keys, identities, clocks, masks)["value"].sum()
            arguments = (parameters, hidden, events)
            _, linear = jax.jvp(floating, arguments, tangent)
            _, pullback = jax.vjp(floating, *arguments)
            backward = pullback(cotangent)
            objective_params = jax.grad(objective)(parameters)
            canonical_params = {name: jnp.broadcast_to(value, (2, 3, *value.shape)) if name in shared else unpack(value, parameter_axes[name]) for name, value in parameters.items()}
            canonical_tangent = {"params": {name: jnp.broadcast_to(value, (2, 3, *value.shape)) if name in shared else unpack(value, parameter_axes[name]) for name, value in tangent[0].items()}, "hidden": unpack(tangent[1], positions("hidden")), "events": unpack(tangent[2], positions("events"))}
            scalar_results = jax.vmap(jax.vmap(scalar_linear))(
                canonical_params, keys.reshape((2, 3)), unpack(identities, positions("ids")),
                unpack(clocks, positions("clock")), unpack(hidden, positions("hidden")),
                unpack(events, positions("events")), unpack(masks, positions("active")),
                canonical_tangent, cotangent,
            )
            return linear, backward, objective_params, scalar_results

        tangent = item["tangent"]
        parameter_tangent = {name: jnp.asarray(value) if parameter_axes[name] is None else pack(value, parameter_axes[name]) for name, value in tangent["params"].items()}
        directions = (parameter_tangent, pack(tangent["hidden"], positions("hidden")), pack(tangent["events"], positions("events")))

        def parameter_result(values):
            return {name: value if parameter_axes[name] is None else unpack(value, parameter_axes[name]) for name, value in values.items()}

        def scalar_linear(parameters, key, ids, clock, hidden, events, active, tangent, cotangent):
            def floating_member(current_params, current_hidden, current_events):
                result = scalar(current_params, key, ids, clock, current_hidden, current_events, active)
                return {"hidden": result["hidden"], "history": result["history"]}
            arguments = (parameters, hidden, events)
            _, linear = jax.jvp(floating_member, arguments, (tangent["params"], tangent["hidden"], tangent["events"]))
            _, pullback = jax.vjp(floating_member, *arguments)
            backward = pullback(cotangent)
            gradient = jax.grad(lambda current: scalar(current, key, ids, clock, hidden, events, active)["value"])(parameters)
            return {"jvp": linear, "vjp": {"params": backward[0], "hidden": backward[1], "events": backward[2]}, "objective_params": gradient}

        linear, backward, objective_params, mapped_linear = jax.jit(calculate)(
            params, packed["hidden"], packed["events"], directions,
            jax.tree.map(jnp.asarray, item["cotangent"]), roots, packed["ids"], packed["clock"], packed["active"],
        )
        outputs.append({
            "jvp": linear,
            "vjp": {"params": parameter_result(backward[0]), "hidden": unpack(backward[1], positions("hidden")), "events": unpack(backward[2], positions("events"))},
            "objective_params": parameter_result(objective_params), "mapped": mapped_linear,
        })
    return outputs


def ensemble_curvature(replay, request):
    outputs = []
    positions = {"ids": (1, 3), "clock": (2, 3), "hidden": (1, 3), "events": (2, 4), "active": (1, 3)}
    for item in request["items"]:
        shared = set(item["shared"])
        remat = item["layout"] == 1
        parameter_axes = {name: None if name in shared else (value.ndim - 2, value.ndim - 1) for name, value in item["params"].items()}

        def pack(value, axes):
            return jnp.asarray(value) if axes is None else jnp.moveaxis(jnp.asarray(value), (0, 1), axes)

        def parameters(values):
            return {name: pack(value, parameter_axes[name]) for name, value in values.items()}

        def canonical(values):
            return {name: value if parameter_axes[name] is None else jnp.moveaxis(value, parameter_axes[name], (0, 1)) for name, value in values.items()}

        def axes_at(level):
            def axis(axes):
                return None if axes is None else axes[level] - int(level == 1 and axes[0] < axes[1])
            return ({name: axis(axes) for name, axes in parameter_axes.items()}, 0, *(axis(positions[name]) for name in ("ids", "clock", "hidden", "events", "active")))

        def scalar(params, root, ids, clock, hidden, events, active):
            state = replay.create(root, ids, hidden, clock)
            return replay.objective(params, state, events, active, remat=remat)

        mapped = jax.vmap(jax.vmap(scalar, in_axes=axes_at(1)), in_axes=axes_at(0))

        def scalar_curvature(params, root, ids, clock, hidden, events, active, direction):
            def gradient(current):
                return jax.grad(scalar)(current, root, ids, clock, hidden, events, active)
            gradients, hvp = jax.jvp(gradient, (params,), (direction,))
            return {"params": gradients, "hvp": hvp}

        member_curvature = jax.vmap(jax.vmap(scalar_curvature, in_axes=(*axes_at(1), axes_at(1)[0])), in_axes=(*axes_at(0), axes_at(0)[0]))

        @jax.jit
        def calculate(params, roots, ids, clock, hidden, events, active, direction):
            def total(current):
                return mapped(current, roots, ids, clock, hidden, events, active).sum()
            value, gradients = jax.value_and_grad(total)(params)
            hvp = jax.jvp(jax.grad(total), (params,), (direction,))[1]
            members = member_curvature(params, roots, ids, clock, hidden, events, active, direction)
            return {"value": value, "params": canonical(gradients), "hvp": canonical(hvp), "members": members}

        state = item["state"]
        roots = jax.random.wrap_key_data(jnp.asarray(state["root"], jnp.uint32), impl=state["implementation"])
        arguments = tuple(pack(state[name] if name in state else item[name], positions[name]) for name in ("ids", "clock", "hidden", "events", "active"))
        outputs.append([calculate(parameters(item["params"]), roots, *arguments, parameters(direction)) for direction in item["directions"]])
    return outputs
