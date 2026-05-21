import pytest

from config_manager.config_manager import ConfigManager, _deep_merge

# -------------------------------------------------------------------------
# _deep_merge
# -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base, override, expected",
    [
        (
            {"log_level": "INFO"},
            {"log_level": "WARNING"},
            {"log_level": "WARNING"},
        ),
        (
            {"log_level": "INFO"},
            {"currency": "EUR"},
            {"log_level": "INFO", "currency": "EUR"},
        ),
        (
            {"pipeline": {"log_level": "INFO", "timeout": 30}},
            {"pipeline": {"log_level": "WARNING"}},
            {"pipeline": {"log_level": "WARNING", "timeout": 30}},
        ),
        (
            {"pipeline": "simple"},
            {"pipeline": {"log_level": "INFO"}},
            {"pipeline": {"log_level": "INFO"}},
        ),
        (
            {"log_level": "INFO"},
            {},
            {"log_level": "INFO"},
        ),
        (
            {},
            {"log_level": "WARNING"},
            {"log_level": "WARNING"},
        ),
    ],
    ids=[
        "simple_override",
        "new_key_added",
        "deep_merge_preserves_untouched_keys",
        "non_dict_replaced_by_dict",
        "empty_override",
        "empty_base",
    ],
)
def test_deep_merge(base: dict, override: dict, expected: dict) -> None:
    assert _deep_merge(base, override) == expected


# -------------------------------------------------------------------------
# ConfigManager.get — merge correctness
# -------------------------------------------------------------------------


def test_get_overridden_by_env(config_dir) -> None:
    cm = ConfigManager(config_dir, env="prod", market="FR")
    assert cm.get("pipeline.log_level") == "WARNING"


def test_get_preserved_from_general(config_dir) -> None:
    cm = ConfigManager(config_dir, env="prod", market="FR")
    assert cm.get("pipeline.timeout") == 30


def test_get_added_by_market_fr(config_dir) -> None:
    cm = ConfigManager(config_dir, env="prod", market="FR")
    assert cm.get("pipeline.currency") == "EUR"


def test_get_added_by_market_en(config_dir) -> None:
    cm = ConfigManager(config_dir, env="prod", market="EN")
    assert cm.get("pipeline.currency") == "GBP"


def test_get_database_port_preserved_from_general(config_dir) -> None:
    cm = ConfigManager(config_dir, env="prod", market="FR")
    assert cm.get("database.port") == 5432


def test_get_returns_default_if_absent(config_dir) -> None:
    cm = ConfigManager(config_dir, env="prod", market="FR")
    assert cm.get("pipeline.missing_key", 42) == 42


def test_get_returns_none_if_absent_and_no_default(config_dir) -> None:
    cm = ConfigManager(config_dir, env="prod", market="FR")
    assert cm.get("pipeline.missing_key") is None


# -------------------------------------------------------------------------
# ConfigManager — anchor resolution
# -------------------------------------------------------------------------


def test_anchor_resolved_from_context(config_dir) -> None:
    cm = ConfigManager(config_dir, env="prod", market="FR")
    assert cm.get("database.host") == "prod-FR-db.internal.com"


def test_anchor_unresolvable_raises(config_dir) -> None:
    with pytest.raises(KeyError, match="market"):
        ConfigManager(config_dir)  # no context provided


# -------------------------------------------------------------------------
# ConfigManager — priority order
# -------------------------------------------------------------------------


def test_env_wins_over_market_in_default_priority(config_dir) -> None:
    """env comes after market in default priority — env must win."""
    cm = ConfigManager(config_dir, env="prod", market="FR")
    # prod sets log_level: WARNING, which must override general's INFO
    # market/FR does not set log_level, so env/prod is the final word
    assert cm.get("pipeline.log_level") == "WARNING"


def test_market_wins_over_general_in_default_priority(config_dir) -> None:
    """market comes after general — market host must override general's localhost."""
    cm = ConfigManager(config_dir, env="dev", market="FR")
    assert cm.get("database.host") == "fr-db.internal.com"


def test_custom_priority_env_before_market(config_dir) -> None:
    """When market comes last, market host must win over general's localhost."""
    cm = ConfigManager(
        config_dir,
        priority_order=["general", "env", "market"],
        env="prod",
        market="FR",
    )
    # market/FR sets host: fr-db.internal.com
    # env/prod sets host: prod-{market}-db.internal.com -> prod-FR-db.internal.com
    # market comes last -> market wins
    assert cm.get("database.host") == "fr-db.internal.com"


def test_missing_layer_skipped(tmp_path) -> None:
    """A config dir without a market layer should not raise."""
    general = tmp_path / "general"
    general.mkdir()
    (general / "settings.yaml").write_text("pipeline:\n  log_level: INFO\n")
    cm = ConfigManager(tmp_path, env="prod")
    assert cm.get("pipeline.log_level") == "INFO"
