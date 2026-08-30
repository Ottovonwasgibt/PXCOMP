import numpy as np

from pxcomp.alloc import allocation_counts, generate_ownership, validate_ownership


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


def test_different_seed_changes_map():
    a = generate_ownership(40, 40, 4, seed=1, mode="organic", territory=55)
    b = generate_ownership(40, 40, 4, seed=2, mode="organic", territory=55)
    assert not np.array_equal(a, b)
