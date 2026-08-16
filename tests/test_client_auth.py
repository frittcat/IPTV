import pytest

from backend.client_auth import hash_password, normalize_username, verify_password


def test_password_hash_round_trip():
    encoded = hash_password("correct-horse-battery-staple")
    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password("correct-horse-battery-staple", encoded)
    assert not verify_password("wrong-password", encoded)


def test_username_is_normalized_and_restricted():
    assert normalize_username("  Mauro.Jr  ") == "mauro.jr"
    with pytest.raises(ValueError):
        normalize_username("ab")
    with pytest.raises(ValueError):
        normalize_username("nome com espaco")


def test_password_minimum_length():
    with pytest.raises(ValueError):
        hash_password("short")
