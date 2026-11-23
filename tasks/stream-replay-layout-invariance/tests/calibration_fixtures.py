"""Verification-time raw-unit profiles, kept separate from ordinary fixtures."""

import numpy as np


def profiles(seed):
    rng = np.random.default_rng(np.random.SeedSequence([seed, 5]))
    result = {"moderate": [], "deep": [], "discriminating": []}
    for implementation in ("threefry2x32", "rbg"):
        words = 2 if implementation == "threefry2x32" else 4
        for band in ("moderate", "deep", "discriminating"):
            for draw in range(1 if band == "discriminating" else 6):
                vector = draw % 2 == 1 or band == "discriminating"
                shape = (3,) if vector else ()
                state = {
                    "implementation": implementation,
                    "root": rng.integers(0, 2**32, words, dtype=np.uint32),
                    "ids": rng.integers(0, 2**32, (2, 2), dtype=np.uint32),
                    "clock": rng.integers(0, 2**32, (2, 2), dtype=np.uint32),
                    "hidden": rng.normal(0, 0.2, (2, 3)).astype(np.float32),
                }
                active = rng.random((3, 2)) < 0.7
                active[:, 0] = [True, False, True]
                exponents = rng.choice([12, 24, 36], size=shape) if band == "moderate" else np.full(shape, 60)
                units = np.exp2(exponents)
                compact = (0.98, 1.02) if band == "moderate" else (0.995, 1.005)
                events = (rng.choice([-1, 1], (3, 2, 3)) * rng.uniform(*compact, (3, 2, 3)) * units).astype(np.float32)
                magnitudes = (9.5, 13.5) if band == "moderate" else (44.5, 45.5)
                params = {
                    "decay": np.asarray(rng.uniform(0.15, 0.55, shape), np.float32),
                    "gain": np.asarray(rng.choice([-1, 1], size=shape) * rng.uniform(*magnitudes, shape) / units, np.float32),
                    "bias": np.asarray(rng.normal(0, 0.05, shape), np.float32),
                    "keep": np.asarray(rng.uniform(0.65, 1), np.float32),
                }
                if band == "deep" and draw % 3 == 0:
                    params["keep"] = np.asarray(1, np.float32)
                if band == "deep" and draw % 3 == 1:
                    active[:] = False
                    active[draw % 3, draw % 2] = True
                if band == "discriminating":
                    state["hidden"][:] = 0
                    active[:] = False
                    active[1, 0] = True
                    events = (rng.choice([-1, 1], (3, 2, 3)) * 2.0**60).astype(np.float32)
                    params = {"decay": np.zeros(3, np.float32), "gain": (rng.choice([-1, 1], 3) * 46 * 2.0**-60).astype(np.float32), "bias": np.zeros(3, np.float32), "keep": np.asarray(1, np.float32)}
                mixed = {name: np.asarray(rng.normal(0, 0.07, value.shape), np.float32) for name, value in params.items()}
                unit = {name: np.zeros_like(value) for name, value in params.items()}
                if vector:
                    unit["gain"][draw % 3] = 1
                else:
                    unit["gain"] = np.asarray(1, np.float32)
                roots = rng.integers(0, 2**32, (2, 2, words), dtype=np.uint32)
                case = {"state": state, "params": params, "events": events, "active": active}
                result[band].append((case, [unit, mixed], roots))
    return result
