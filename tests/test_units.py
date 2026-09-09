import pytest

from shortener.codegen import encode_base62, generate_code
from shortener.validation import ValidationError, validate_alias, validate_ttl, validate_url


class TestValidateUrl:
    def test_accepts_http_and_https(self):
        assert validate_url("https://example.com/page") == "https://example.com/page"
        assert validate_url("http://example.com") == "http://example.com"

    def test_rejects_missing_scheme(self):
        with pytest.raises(ValidationError):
            validate_url("example.com")

    def test_rejects_javascript_scheme(self):
        with pytest.raises(ValidationError):
            validate_url("javascript:alert(1)")

    def test_rejects_ftp_scheme(self):
        with pytest.raises(ValidationError):
            validate_url("ftp://example.com/file")

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationError):
            validate_url("   ")

    def test_rejects_non_string(self):
        with pytest.raises(ValidationError):
            validate_url(12345)

    def test_rejects_control_characters(self):
        with pytest.raises(ValidationError):
            validate_url("https://example.com/\x00page")


class TestValidateAlias:
    def test_accepts_valid_alias(self):
        assert validate_alias("my-co_de1") == "my-co_de1"

    def test_rejects_spaces(self):
        with pytest.raises(ValidationError):
            validate_alias("no spaces")

    def test_rejects_too_short(self):
        with pytest.raises(ValidationError):
            validate_alias("ab")

    def test_rejects_reserved_words(self):
        with pytest.raises(ValidationError):
            validate_alias("analytics")


class TestValidateTtl:
    def test_none_passthrough(self):
        assert validate_ttl(None) is None

    def test_accepts_positive_int(self):
        assert validate_ttl(60) == 60
        assert validate_ttl("120") == 120

    def test_rejects_zero_or_negative(self):
        with pytest.raises(ValidationError):
            validate_ttl(0)
        with pytest.raises(ValidationError):
            validate_ttl(-5)

    def test_rejects_non_numeric(self):
        with pytest.raises(ValidationError):
            validate_ttl("soon")


class TestBase62:
    def test_zero(self):
        assert encode_base62(0) == "0"

    def test_roundtrip_is_unique_across_range(self):
        codes = [encode_base62(n) for n in range(1, 500)]
        assert len(codes) == len(set(codes))


class TestGenerateCode:
    def test_generates_code_of_requested_length(self):
        code = generate_code(lambda c: False, seed="https://example.com", length=7)
        assert len(code) == 7

    def test_retries_on_collision_then_succeeds(self):
        seen = {"first-collision"}

        def code_exists(c):
            if c not in seen:
                return False
            return True

        # First call: everything "exists" until we stop checking -> force
        # generate_code to keep retrying by making the first N codes collide.
        calls = {"n": 0}

        def flaky_exists(c):
            calls["n"] += 1
            return calls["n"] <= 2  # first two attempts collide

        code = generate_code(flaky_exists, seed="https://example.com", length=7)
        assert isinstance(code, str)
        assert calls["n"] == 3

    def test_raises_when_always_colliding(self):
        with pytest.raises(RuntimeError):
            generate_code(lambda c: True, seed="https://example.com", max_attempts=3)
