from __future__ import annotations

import math
import numpy as np
from PIL import Image

OWNER_SENTINEL = np.uint16(65535)


def allocation_counts(total_pixels: int, layer_count: int) -> list[int]:
    if layer_count < 1:
        raise ValueError("layer_count must be at least one")
    return [
        ((i + 1) * total_pixels) // layer_count - (i * total_pixels) // layer_count
        for i in range(layer_count)
    ]


def generate_ownership(
    width: int,
    height: int,
    layer_count: int,
    seed: int,
    mode: str = "pixel",
    territory: int = 55,
) -> np.ndarray:
    if width < 1 or height < 1:
        raise ValueError("Canvas dimensions must be positive")
    if not 1 <= layer_count <= 65534:
        raise ValueError("layer_count must be between 1 and 65,534")
    if mode == "pixel":
        return generate_pixel_ownership(width, height, layer_count, seed)
    if mode == "organic":
        return generate_organic_ownership(width, height, layer_count, seed, territory)
    raise ValueError(f"Unknown mode: {mode}")


def generate_pixel_ownership(
    width: int, height: int, layer_count: int, seed: int
) -> np.ndarray:
    total = width * height
    rng = np.random.Generator(np.random.PCG64(np.uint64(seed & 0xFFFFFFFFFFFFFFFF)))
    permutation = rng.permutation(total)
    owners = np.empty(total, dtype=np.uint16)
    cursor = 0
    for layer, count in enumerate(allocation_counts(total, layer_count)):
        next_cursor = cursor + count
        owners[permutation[cursor:next_cursor]] = np.uint16(layer)
        cursor = next_cursor
    return owners.reshape((height, width))


def _organic_cell_size(width: int, height: int, territory: int) -> float:
    territory = int(np.clip(territory, 0, 100))
    # Exponential mapping: 0 behaves close to pixel noise; 100 creates broad fields.
    maximum = max(2.0, min(width, height) / 4.0)
    return math.exp(math.log(1.0) * (1.0 - territory / 100.0) + math.log(maximum) * (territory / 100.0))


def _smooth_random_field(
    rng: np.random.Generator, width: int, height: int, cell_size: float
) -> np.ndarray:
    grid_w = max(2, int(math.ceil(width / max(1.0, cell_size))) + 2)
    grid_h = max(2, int(math.ceil(height / max(1.0, cell_size))) + 2)
    coarse = rng.random((grid_h, grid_w), dtype=np.float32)
    # PIL's floating-point bicubic resize gives a cheap deterministic spatial field
    # without pulling a scientific-computing stack into the desktop package.
    field_image = Image.fromarray(coarse, mode="F").resize(
        (width, height), Image.Resampling.BICUBIC
    )
    field = np.asarray(field_image, dtype=np.float32).copy()
    # Tiny jitter deterministically breaks interpolation ties while preserving shapes.
    field += rng.random((height, width), dtype=np.float32) * np.float32(1e-6)
    return field


def generate_organic_ownership(
    width: int,
    height: int,
    layer_count: int,
    seed: int,
    territory: int = 55,
) -> np.ndarray:
    total = width * height
    rng = np.random.Generator(np.random.PCG64(np.uint64(seed & 0xFFFFFFFFFFFFFFFF)))
    owners = np.full(total, OWNER_SENTINEL, dtype=np.uint16)
    counts = allocation_counts(total, layer_count)
    cell_size = _organic_cell_size(width, height, territory)

    # Sequential reduction rule: each layer can only claim pixels still unowned.
    # Every active layer receives its exact integer quota. The final layer receives
    # the remainder, guaranteeing no holes and no overlaps.
    for layer in range(layer_count - 1):
        quota = counts[layer]
        field = _smooth_random_field(rng, width, height, cell_size).reshape(-1)
        field[owners != OWNER_SENTINEL] = -np.inf
        chosen = np.argpartition(field, -quota)[-quota:]
        owners[chosen] = np.uint16(layer)

    owners[owners == OWNER_SENTINEL] = np.uint16(layer_count - 1)
    return owners.reshape((height, width))


def validate_ownership(owners: np.ndarray, layer_count: int) -> dict:
    if owners.ndim != 2:
        raise ValueError("Ownership map must be 2-dimensional")
    if owners.size == 0:
        raise ValueError("Ownership map cannot be empty")
    if int(owners.min()) < 0 or int(owners.max()) >= layer_count:
        raise ValueError("Ownership map contains an invalid owner")
    counts = np.bincount(owners.reshape(-1), minlength=layer_count)
    expected = np.asarray(allocation_counts(owners.size, layer_count), dtype=np.int64)
    return {
        "valid": bool(np.array_equal(counts, expected)),
        "counts": counts,
        "expected": expected,
        "total": int(owners.size),
    }
