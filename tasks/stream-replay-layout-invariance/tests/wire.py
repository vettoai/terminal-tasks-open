"""Data-only JSON transport shared with the isolated operation worker."""

import json
import math

import numpy as np


MAX_BYTES = 8 * 1024 * 1024
MAX_ELEMENTS = 1024 * 1024
DTYPES = {"float32", "float64", "uint32", "int32", "int64", "bool"}


def encode(value):
    if isinstance(value, dict):
        return {name: encode(item) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    if hasattr(value, "shape") and hasattr(value, "dtype"):
        array = np.asarray(value)
        return {"array": {"dtype": str(array.dtype), "shape": list(array.shape), "data": array.ravel().tolist()}}
    if isinstance(value, np.generic):
        return value.item()
    return value


def decode(value):
    if isinstance(value, dict) and set(value) == {"array"}:
        description = value["array"]
        if not isinstance(description, dict) or set(description) != {"dtype", "shape", "data"}:
            raise ValueError("invalid array description")
        dtype, shape, data = description["dtype"], description["shape"], description["data"]
        if not isinstance(dtype, str) or dtype not in DTYPES:
            raise ValueError("invalid array dtype")
        if not isinstance(shape, list) or len(shape) > 8:
            raise ValueError("invalid array rank")
        if any(type(size) is not int or size < 0 or size > MAX_ELEMENTS for size in shape):
            raise ValueError("invalid array shape")
        count = math.prod(shape)
        if count > MAX_ELEMENTS or not isinstance(data, list) or len(data) != count:
            raise ValueError("invalid array element count")
        if any(type(item) not in (int, float, bool) for item in data):
            raise ValueError("invalid array element")
        return np.asarray(data, dtype=dtype).reshape(shape)
    if isinstance(value, dict):
        return {name: decode(item) for name, item in value.items()}
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


def dumps(value):
    payload = json.dumps(encode(value), allow_nan=False, separators=(",", ":")).encode()
    if len(payload) > MAX_BYTES:
        raise ValueError("wire payload too large")
    return payload


def loads(payload):
    if len(payload) > MAX_BYTES:
        raise ValueError("wire payload too large")
    return decode(json.loads(payload))
