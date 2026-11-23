"""Raw-unit windows and private scalar-member curvature expectations."""

import numpy as np

import calibration_reference
from ensemble_fixtures import member


def ensembles(seed):
    rng = np.random.default_rng(np.random.SeedSequence([seed, 7]))
    for implementation in ("threefry2x32", "rbg"):
        for layout in range(2):
            shared = {"decay", "bias"} if layout == 0 else {"gain", "keep"}
            words = 2 if implementation == "threefry2x32" else 4
            state = {
                "implementation": implementation,
                "root": rng.integers(0, 2**32, (2, 3, words), dtype=np.uint32),
                "ids": rng.integers(0, 2**32, (2, 3, 2, 2), dtype=np.uint32),
                "clock": rng.integers(0, 2**32, (2, 3, 2, 2), dtype=np.uint32),
                "hidden": rng.normal(0, 0.2, (2, 3, 2, 3)).astype(np.float32),
            }
            state["ids"][1, 2, 0] = state["ids"][0, 0, 0]
            state["clock"][0, 1, 0, 0] = np.uint32(0xFFFFFFFF)
            state["clock"][1, 2, 1] = np.uint32(0xFFFFFFFF)
            active = rng.random((2, 3, 3, 2)) < 0.7
            active[..., 0] = [True, False, True]
            active[1, 2, :, 1] = True
            exponents = rng.permutation(np.concatenate(([60], rng.choice([12, 24, 36], 2, replace=False))))
            units = np.exp2(exponents)
            signs = rng.choice([-1, 1], 3)
            params = {}
            for name in ("decay", "gain", "bias", "keep"):
                base = (3,) if name in {"gain", "bias"} else ()
                shape = base if name in shared else (2, 3, *base)
                if name == "gain":
                    value = signs * rng.uniform(44.5, 45.5, shape) / units
                elif name == "bias":
                    value = rng.normal(0, 0.05, shape)
                else:
                    bounds = (0.15, 0.55) if name == "decay" else (0.7, 0.95)
                    value = rng.uniform(*bounds, shape)
                params[name] = np.asarray(value, np.float32)
            bands = rng.integers(1, 7, (2, 3))
            deep = ((bands[..., None] >> np.arange(3)) & 1).astype(bool)
            deep = deep[:, :, None, None, :]
            compact = rng.uniform(np.where(deep, 0.995, 0.22), np.where(deep, 1.005, 0.28), (2, 3, 3, 2, 3))
            events = (rng.choice([-1, 1], compact.shape) * compact * units).astype(np.float32)
            gain_only = {name: np.zeros_like(value) for name, value in params.items()}
            feature = int(np.flatnonzero(exponents == 60)[0])
            gain_only["gain"][..., feature] = signs[feature]
            keep_only = {name: np.zeros_like(value) for name, value in params.items()}
            keep_only["keep"] = np.ones_like(params["keep"])
            mixed = {
                name: np.asarray(signs * rng.uniform(0.02, 0.08, value.shape) if name == "gain" else rng.normal(0, 0.07, value.shape), np.float32)
                for name, value in params.items()
            }
            yield {"state": state, "params": params, "active": active, "events": events, "shared": sorted(shared), "layout": layout, "directions": [gain_only, keep_only, mixed]}


def expected(ensemble, direction):
    results = []
    for index in np.ndindex(2, 3):
        case = member(ensemble, index)
        member_direction = {name: value if name in ensemble["shared"] else value[index] for name, value in direction.items()}
        results.append(calibration_reference.evaluate(case, member_direction)["derivatives"])
    members = {
        kind: {
            name: np.stack([result[kind][name] for result in results]).reshape((2, 3, *case["params"][name].shape))
            for name in ensemble["params"]
        }
        for kind in ("params", "hvp")
    }
    joint = {
        kind: {name: value.sum(axis=(0, 1)) if name in ensemble["shared"] else value for name, value in leaves.items()}
        for kind, leaves in members.items()
    }
    return {"value": np.asarray(sum(result["value"] for result in results)), **joint, "members": members}
