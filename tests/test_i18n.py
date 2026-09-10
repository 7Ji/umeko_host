from umeko_host.i18n import detect_language, language, set_language, tr


def test_language_detection_defaults_to_english() -> None:
    assert detect_language("en_US") == "en"
    assert detect_language("de_DE") == "en"
    assert detect_language("zh_TW") == "en"
    assert detect_language("zh_CN") == "zh_CN"
    assert detect_language("zh-Hans-SG") == "zh_CN"


def test_translation_and_english_fallback() -> None:
    original = language()
    try:
        set_language("zh_CN")
        assert tr("Frame: {value}", value=12) == "帧: 12"
        set_language("en")
        assert tr("Frame: {value}", value=12) == "Frame: 12"
    finally:
        set_language(original)
