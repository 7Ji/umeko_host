import pytest

from umeko_host.i18n import language, set_language


@pytest.fixture(autouse=True)
def english_ui() -> None:
    original = language()
    set_language("en")
    try:
        yield
    finally:
        set_language(original)
