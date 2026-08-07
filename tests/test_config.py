from procurelens.config import get_settings


def test_settings_defaults():
    s = get_settings()
    assert s.env in {"dev", "staging", "prod"}
    assert s.database_url.startswith("postgresql")
