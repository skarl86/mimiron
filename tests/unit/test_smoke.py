"""기본 임포트 + 버전 확인."""


def test_version_string() -> None:
    import mimiron
    assert mimiron.__version__ == "0.1.0"


def test_schema_version_is_one() -> None:
    import mimiron
    assert mimiron.SCHEMA_VERSION == 1
