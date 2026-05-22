"""
ConfigManager: merge multi-layer YAML configs into a single flat config.

The config directory is structured in layers. Each layer is a subdirectory
containing one or more YAML files at arbitrary depth. Layers are discovered,
merged in priority order, and anchor points resolved before the config
is exposed via a simple dot-notation API.

Design principles
-----------------
- YAML over Python. Config files can be edited without touching the codebase
  and are safe to hand to non-developers. Python config files can execute
  arbitrary code on import, which is a security risk in production.
- Priority order as explicit contract. The developer defines the merge order
  at instantiation time. Later layers override earlier ones. Nothing is implicit.
- Deep merge, not shallow replace. A prod layer that only defines log_level
  does not erase the other keys inherited from general.
- Fail fast on unresolvable anchors. {anchor} placeholders that cannot be
  resolved from context kwargs raise a KeyError immediately, rather than
  propagating silently into the pipeline as literal strings.
- Context-driven folder resolution. If a layer name matches a context key
  (e.g. layer "market" + context market="FR"), the manager descends into
  the matching subdirectory automatically.

TODO @Maxime 2026-05-21: extend to support remote config sources
(e.g. AWS SSM, GCP Secret Manager) by abstracting file discovery
behind a ConfigBackend interface.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_SUPPORTED_CONFIG_FORMATS: frozenset[str] = frozenset({".yaml", ".yml"})

# Default priority order: later entries override earlier ones (lowest to highest).
# Can be overridden at instantiation to match any config directory structure.
_DEFAULT_PRIORITY_ORDER: list[str] = ["general", "market", "env"]


class ConfigManager:
    """
    Reads and merges YAML configuration files from a structured config directory.

    YAML is preferred over Python config files for two reasons:
    - Separation of concerns: config files can be edited without touching the
      codebase, and safely read by non-developers (ops, data teams).
    - Environment safety: Python config files can execute arbitrary code on
      import, which is a security risk in production environments.

    Config layers are merged in the order defined by priority_order
    (lowest to highest priority). Each layer overrides the previous one
    via deep merge -- sub-dicts are merged at the key level, not replaced.

    Example directory structure and priority order::

        config/
        ├── general/   # base defaults
        ├── market/    # country-specific overrides (e.g. FR/, EN/)
        └── env/       # environment-specific overrides (e.g. prod/, dev/)

        priority_order = ["general", "market", "env"]

    Anchor points (e.g. {env}, {market}) in YAML string values are resolved
    from context kwargs. Unresolvable anchors raise a KeyError immediately
    to avoid silent misconfigurations.

    Example::

        # Given this config structure:
        #   config/
        #   ├── general/settings.yaml   -> { pipeline: { log_level: INFO } }
        #   ├── market/FR/settings.yaml -> { pipeline: { currency: EUR } }
        #   └── env/prod/settings.yaml  -> { pipeline: { log_level: WARNING } }
        #
        # After merge (general < market/FR < env/prod):
        #   { pipeline: { log_level: WARNING, currency: EUR } }
        #
        # env/prod overrides log_level from general.
        # market/FR adds currency without erasing log_level.

        cm = ConfigManager(
            "config/",
            priority_order=["general", "market", "env"],
            env="prod",
            market="FR",
        )
        cm.get("pipeline.log_level")       # -> "WARNING"  (overridden by env/prod)
        cm.get("pipeline.currency")        # -> "EUR"      (added by market/FR)
        cm.get("pipeline.timeout", 30)     # -> 30         (absent, returns default)

    TODO @Maxime 2026-05-21: extend to support remote config sources
    (e.g. AWS SSM, GCP Secret Manager) by abstracting file discovery
    behind a ConfigBackend interface.
    """

    def __init__(
        self,
        config_dir: str | Path,
        priority_order: list[str] = _DEFAULT_PRIORITY_ORDER,
        **context: str,
    ) -> None:
        """
        Parameters
        ----------
        config_dir:
            Root config directory.
        priority_order:
            Ordered list of config layer subdirectory names.
            Later entries override earlier ones.
            Defaults to ["general", "market", "env"].
        **context:
            Runtime values for anchor replacement and folder resolution.
            Keys must match anchor points used in YAML values.
            e.g. env="prod", market="FR"
        """
        self._config_dir = Path(config_dir)
        self._priority_order = priority_order
        self._context = context
        self._config = self._build_config()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """
        Returns a config value using dot-notation key traversal.

        Parameters
        ----------
        key:
            Dot-separated key path, e.g. "database.host".
        default:
            Value returned if the key is absent. Defaults to None.
        """
        keys = key.split(".")
        value = self._config
        for k in keys:
            if not isinstance(value, dict) or k not in value:
                return default
            value = value[k]
        return value

    # -------------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------------

    def _build_config(self) -> dict[str, Any]:
        """
        Discovers all config layers in priority order, merges them, and
        resolves anchor points. Called once at instantiation.
        """
        merged: dict[str, Any] = {}
        for layer in self._priority_order:
            layer_dir = self._config_dir / layer

            # If context has a matching key, descend one level deeper.
            # e.g. market/ -> market/FR/ if context has market="FR"
            if layer in self._context:
                layer_dir = layer_dir / self._context[layer]

            if not layer_dir.exists():
                logger.debug(f"Config layer '{layer}' not found -- skipping.")
                continue

            layer_config = self._load_layer(layer_dir)
            merged = _deep_merge(merged, layer_config)
            logger.info(f"Merged config layer: '{layer}'")

        return self._resolve_anchors(merged)

    def _load_layer(self, layer_dir: Path) -> dict[str, Any]:
        """
        Recursively reads and merges all YAML files in a layer directory.

        Files are processed in sorted order to ensure deterministic merge
        behavior when multiple files exist in the same layer.
        """
        merged: dict[str, Any] = {}
        for yaml_file in sorted(layer_dir.rglob("*")):
            if yaml_file.suffix.lower() not in _SUPPORTED_CONFIG_FORMATS:
                continue
            logger.debug(f"Loading config file: {yaml_file}")
            with yaml_file.open(encoding="utf-8") as f:
                content = yaml.safe_load(f) or {}
            merged = _deep_merge(merged, content)
        return merged

    def _resolve_anchors(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Recursively resolves {anchor} placeholders in all string values.

        Raises KeyError if an anchor cannot be resolved from context --
        fails fast to avoid silent misconfigurations downstream.
        """
        resolved: dict[str, Any] = {}
        for key, value in config.items():
            if isinstance(value, dict):
                resolved[key] = self._resolve_anchors(value)
            elif isinstance(value, str):
                try:
                    resolved[key] = value.format_map(self._context)
                except KeyError as e:
                    raise KeyError(
                        f"Unresolvable anchor {e} in config key '{key}'. "
                        f"Available context: {list(self._context.keys())}"
                    ) from e
            else:
                resolved[key] = value
        return resolved


# -------------------------------------------------------------------------
# Module-level helpers
# -------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merges override into base.

    Nested dicts are merged at the key level -- override does not erase
    entire sub-dicts, only the keys it explicitly defines.
    """
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
