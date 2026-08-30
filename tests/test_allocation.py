import hashlib

import numpy as np

from pxcomp.alloc import (
    _sample_primitive_complexity,
    allocation_counts,
    generate_ownership,
    validate_ownership,
)


def test_integer_quota_covers_every_pixel():
    counts = allocation_counts(101, 10)
    assert sum(counts) == 101
    assert max(counts) - min(counts) <= 1


def test_pixel_random_is_exact_and_deterministic():
    first = generate_ownership(43, 29, 7, seed=991, mode="pixel")
    second = generate_ownership(43, 29, 7, seed=991, mode="pixel")
    assert np.array_equal(first, second)
    report = validate_ownership(first, 7)
    assert report["valid"]
    assert report["counts"].sum() == 43 * 29


def test_organic_is_exact_and_deterministic():
    first = generate_ownership(61, 47, 5, seed=12345, mode="organic", territory=68)
    second = generate_ownership(61, 47, 5, seed=12345, mode="organic", territory=68)
    assert np.array_equal(first, second)
    assert validate_ownership(first, 5)["valid"]


def test_vector_mixed_primitives_are_exact_and_deterministic():
    first = generate_ownership(
        83,
        61,
        6,
        seed=12345,
        mode="vector",
        territory=78,
        vector_points=12,
        point_spread=100,
        algorithm_version="1.2",
    )
    second = generate_ownership(
        83,
        61,
        6,
        seed=12345,
        mode="vector",
        territory=78,
        vector_points=12,
        point_spread=100,
        algorithm_version="1.2",
    )
    assert np.array_equal(first, second)
    report = validate_ownership(first, 6)
    assert report["valid"]
    assert report["counts"].sum() == 83 * 61


def test_max_primitive_points_randomizes_from_one_through_maximum():
    rng = np.random.Generator(np.random.PCG64(1234))
    complexities = [_sample_primitive_complexity(rng, 12) for _ in range(100)]
    assert set(complexities) == set(range(1, 13))


def test_one_and_two_point_primitive_modes_are_valid():
    one = generate_ownership(
        73,
        59,
        4,
        seed=9182,
        mode="vector",
        territory=70,
        vector_points=1,
        point_spread=100,
        algorithm_version="1.2",
    )
    two = generate_ownership(
        73,
        59,
        4,
        seed=9182,
        mode="vector",
        territory=70,
        vector_points=2,
        point_spread=100,
        algorithm_version="1.2",
    )
    assert validate_ownership(one, 4)["valid"]
    assert validate_ownership(two, 4)["valid"]
    assert not np.array_equal(one, two)


def test_point_spread_changes_vector_geometry():
    local = generate_ownership(
        89,
        67,
        5,
        seed=777,
        mode="vector",
        territory=65,
        vector_points=12,
        point_spread=15,
        algorithm_version="1.2",
    )
    full_canvas = generate_ownership(
        89,
        67,
        5,
        seed=777,
        mode="vector",
        territory=65,
        vector_points=12,
        point_spread=100,
        algorithm_version="1.2",
    )
    assert not np.array_equal(local, full_canvas)
    assert validate_ownership(local, 5)["valid"]
    assert validate_ownership(full_canvas, 5)["valid"]


def test_legacy_vector_11_has_stable_golden_map():
    legacy = generate_ownership(
        83,
        61,
        6,
        seed=12345,
        mode="vector",
        territory=78,
        vector_points=7,
        algorithm_version="1.1",
    )
    digest = hashlib.sha256(legacy.tobytes()).hexdigest()
    assert digest == "fc587ddd2af903cb29f66a798357bfbeddccc14f11de55c1ca85e979f7dcaf8c"
    assert validate_ownership(legacy, 6)["valid"]


def test_different_seed_changes_map():
    a = generate_ownership(40, 40, 4, seed=1, mode="organic", territory=55)
    b = generate_ownership(40, 40, 4, seed=2, mode="organic", territory=55)
    assert not np.array_equal(a, b)
