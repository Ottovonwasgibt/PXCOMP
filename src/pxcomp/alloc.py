from __future__ import annotations

import math
import numpy as np
from PIL import Image, ImageDraw

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
    vector_points: int = 7,
) -> np.ndarray:
    if width < 1 or height < 1:
        raise ValueError("Canvas dimensions must be positive")
    if not 1 <= layer_count <= 65534:
        raise ValueError("layer_count must be between 1 and 65,534")
    if mode == "pixel":
        return generate_pixel_ownership(width, height, layer_count, seed)
    if mode == "organic":
        return generate_organic_ownership(width, height, layer_count, seed, territory)
    if mode == "vector":
        return generate_vector_ownership(
            width,
            height,
            layer_count,
            seed,
            territory=territory,
            vector_points=vector_points,
        )
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
    maximum = max(2.0, min(width, height) / 4.0)
    return math.exp(
        math.log(1.0) * (1.0 - territory / 100.0)
        + math.log(maximum) * (territory / 100.0)
    )


def _smooth_random_field(
    rng: np.random.Generator, width: int, height: int, cell_size: float
) -> np.ndarray:
    grid_w = max(2, int(math.ceil(width / max(1.0, cell_size))) + 2)
    grid_h = max(2, int(math.ceil(height / max(1.0, cell_size))) + 2)
    coarse = rng.random((grid_h, grid_w), dtype=np.float32)
    field_image = Image.fromarray(coarse, mode="F").resize(
        (width, height), Image.Resampling.BICUBIC
    )
    field = np.asarray(field_image, dtype=np.float32).copy()
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

    for layer in range(layer_count - 1):
        quota = counts[layer]
        field = _smooth_random_field(rng, width, height, cell_size).reshape(-1)
        field[owners != OWNER_SENTINEL] = -np.inf
        chosen = np.argpartition(field, -quota)[-quota:]
        owners[chosen] = np.uint16(layer)

    owners[owners == OWNER_SENTINEL] = np.uint16(layer_count - 1)
    return owners.reshape((height, width))


def _vector_span(territory: int) -> float:
    territory = int(np.clip(territory, 0, 100))
    t = territory / 100.0
    return 0.12 + 0.88 * (t**0.72)


def _random_polygon(
    rng: np.random.Generator,
    width: int,
    height: int,
    point_count: int,
    territory: int,
) -> list[tuple[int, int]]:
    point_count = int(np.clip(point_count, 3, 32))
    span = _vector_span(territory)

    span_w = max(3, min(width, int(round(width * span * rng.uniform(0.72, 1.0)))))
    span_h = max(3, min(height, int(round(height * span * rng.uniform(0.72, 1.0)))))

    x0 = 0 if span_w >= width else int(rng.integers(0, width - span_w + 1))
    y0 = 0 if span_h >= height else int(rng.integers(0, height - span_h + 1))

    xs = rng.uniform(x0, x0 + max(1, span_w - 1), size=point_count)
    ys = rng.uniform(y0, y0 + max(1, span_h - 1), size=point_count)

    cx = float(xs.mean())
    cy = float(ys.mean())
    angles = np.arctan2(ys - cy, xs - cx)
    order = np.argsort(angles)

    points = [
        (
            int(np.clip(round(xs[i]), 0, width - 1)),
            int(np.clip(round(ys[i]), 0, height - 1)),
        )
        for i in order
    ]

    compact: list[tuple[int, int]] = []
    for point in points:
        if not compact or point != compact[-1]:
            compact.append(point)
    if len(compact) >= 3:
        return compact

    return [
        (x0, y0),
        (min(width - 1, x0 + span_w - 1), y0),
        (x0, min(height - 1, y0 + span_h - 1)),
    ]


def _polygon_available_pixels(
    owners: np.ndarray,
    points: list[tuple[int, int]],
) -> tuple[np.ndarray, np.ndarray]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x0, x1 = max(0, min(xs)), min(owners.shape[1] - 1, max(xs))
    y0, y1 = max(0, min(ys)), min(owners.shape[0] - 1, max(ys))

    if x1 < x0 or y1 < y0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)

    local_points = [(x - x0, y - y0) for x, y in points]
    mask_image = Image.new("1", (x1 - x0 + 1, y1 - y0 + 1), 0)
    ImageDraw.Draw(mask_image).polygon(local_points, fill=1)
    mask = np.asarray(mask_image, dtype=bool)

    available = owners[y0 : y1 + 1, x0 : x1 + 1] == OWNER_SENTINEL
    local_y, local_x = np.nonzero(mask & available)
    return local_y.astype(np.int64) + y0, local_x.astype(np.int64) + x0


def _take_crisp_slice(
    ys: np.ndarray,
    xs: np.ndarray,
    count: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    if count >= xs.size:
        return ys, xs
    if count <= 0:
        return ys[:0], xs[:0]

    theta = float(rng.uniform(0.0, math.tau))
    c = math.cos(theta)
    s = math.sin(theta)
    score = (
        xs.astype(np.float64) * c
        + ys.astype(np.float64) * s
        + 1e-7 * (xs.astype(np.float64) * -s + ys.astype(np.float64) * c)
    )
    selected = np.argpartition(score, count - 1)[:count]
    return ys[selected], xs[selected]


def _finish_with_vector_cut(
    owners: np.ndarray,
    layer: int,
    quota_remaining: int,
    rng: np.random.Generator,
) -> None:
    ys, xs = np.nonzero(owners == OWNER_SENTINEL)
    chosen_y, chosen_x = _take_crisp_slice(ys, xs, quota_remaining, rng)
    owners[chosen_y, chosen_x] = np.uint16(layer)


def generate_vector_ownership(
    width: int,
    height: int,
    layer_count: int,
    seed: int,
    territory: int = 70,
    vector_points: int = 7,
) -> np.ndarray:
    """Allocate exact equal shares as hard-edged vector-derived cutout territories."""
    total = width * height
    if layer_count == 1:
        return np.zeros((height, width), dtype=np.uint16)

    vector_points = int(np.clip(vector_points, 3, 32))
    rng = np.random.Generator(np.random.PCG64(np.uint64(seed & 0xFFFFFFFFFFFFFFFF)))
    owners = np.full((height, width), OWNER_SENTINEL, dtype=np.uint16)
    counts = allocation_counts(total, layer_count)

    for layer in range(layer_count - 1):
        remaining = counts[layer]
        attempts = 0
        max_attempts = max(96, vector_points * 24)

        while remaining > 0 and attempts < max_attempts:
            points = _random_polygon(
                rng,
                width,
                height,
                point_count=vector_points,
                territory=territory,
            )
            ys, xs = _polygon_available_pixels(owners, points)
            attempts += 1
            if xs.size == 0:
                continue

            take = min(remaining, int(xs.size))
            chosen_y, chosen_x = _take_crisp_slice(ys, xs, take, rng)
            owners[chosen_y, chosen_x] = np.uint16(layer)
            remaining -= take

        if remaining > 0:
            _finish_with_vector_cut(owners, layer, remaining, rng)

    owners[owners == OWNER_SENTINEL] = np.uint16(layer_count - 1)
    return owners


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
