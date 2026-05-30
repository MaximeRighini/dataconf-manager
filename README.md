# dataconf-manager

Reusable `DataManager` and `ConfigManager` for Python data pipelines.

> **Important:** This is not a standalone application. This code is built to be imported as a library.

---

## Table of Contents

- [Installation](#installation)
- [DataManager](#datamanager)
- [ConfigManager](#configmanager)
- [Code Quality](#code-quality)

---

## Installation

Add to your `pyproject.toml`:

```toml
dependencies = [
    "dataconf-manager @ git+https://github.com/MaximeRighini/dataconf-manager",
]
```

If you need Excel read/write support (`.xlsx`), install the `data` optional dependencies:

```toml
dependencies = [
    "dataconf-manager[data] @ git+https://github.com/MaximeRighini/dataconf-manager",
]
```

---

## DataManager

Reads and writes Polars DataFrames from/to **local disk** based on file extension.
Supports CSV, Parquet, Excel (.xlsx), and JSON (tabular only).

**Behavior:**

- Creates parent directories automatically on write.
- Logs a warning when overwriting an existing file.
- `overwrite=True` by default. Set `overwrite=False` to raise `FileExistsError` on conflict.
- Format-specific options (e.g. `sheet_name` for `.xlsx`) can be passed as `**kwargs`.
- Raises `FileNotFoundError` if the file does not exist on read.
- Raises `ValueError` for unsupported formats.

```python
from dataconf_manager import DataManager

dm = DataManager()

df = dm.read("data/input/products.csv")
df = dm.read("data/input/products.xlsx", sheet_name="Catalog")

dm.write(df, "data/output/results.parquet")
dm.write(df, "data/output/results.csv", overwrite=False)
```

---

## ConfigManager

Merges YAML configuration files from a structured config directory into a single flat config object,
with support for multi-layer overrides and dynamic anchor resolution.

This is useful when your project needs to behave differently across environments (dev, prod)
or markets (FR, EN) without scattering config values across multiple Python files.

**Behavior:**

- Layers are merged in the order defined by `priority_order` — later entries override earlier ones.
- Merge is **deep**: sub-dicts are merged at the key level, not replaced entirely. A `prod` layer
  that only defines `log_level` will not erase the other keys inherited from `general`.
- The config directory structure is not fixed. It is driven by `priority_order`. Developers define the
  layers that make sense for their project (e.g. `["general", "env"]` for a simple project,
  or `["general", "market", "env"]` for a multi-country pipeline).
- Anchor points (`{env}`, `{market}`) in YAML string values are resolved from context kwargs.
  Unresolvable anchors raise a `KeyError` immediately to fail fast and avoid silent misconfigurations.

```python
from dataconf_manager import ConfigManager

# A multi-country pipeline with environment-specific overrides.
# "general" sets the base config. "market" adds country-specific values.
# "env" has the final word — prod settings always win.
cm = ConfigManager(
    "config/",
    priority_order=["general", "market", "env"],
    env="prod",
    market="FR",
)

cm.get("pipeline.log_level")       # -> "WARNING"  (overridden by env/prod)
cm.get("pipeline.currency")        # -> "EUR"       (added by market/FR)
cm.get("pipeline.timeout", 30)     # -> 30           (absent — returns default)
cm.get("database.host")            # -> "prod-FR-db.internal.com" (resolved from "prod-{market}-db.internal.com")
```

**Two access styles are supported:**

```python
# .get() — returns default if absent, useful for optional config keys
cm.get("pipeline.timeout", 60)

# Attribute-style — fail-fast, raises AttributeError if key is missing
cm.data.df_product
cm.lca.emission_factors_kg_co2_per_kg_km.sea
```

**Example directory structure** (adapt to your `priority_order`):

```text
config/
├── general/        # base defaults — lowest priority
├── market/
│   ├── FR/         # France-specific overrides
│   └── EN/         # UK-specific overrides
└── env/
    ├── dev/        # development overrides
    └── prod/       # production overrides — highest priority
```

Each directory can contain any number of YAML files at any depth. All files are discovered recursively and merged within their layer.

> E2E tests are intentionally absent from this package. `DataManager` and `ConfigManager`
> are fully covered by unit tests with real file I/O via `tmp_path` and static fixtures.
> E2E tests belong in the projects that consume this package.

---

## Code Quality

Common tasks are available via `make` to simplify the developer experience.

```bash
make lint-fix      # Auto-fix formatting, style, and import order
make lint-verify   # Read-only checks — what CI runs
make test          # Run unit tests
make all           # lint-fix → lint-verify → test
make clean         # Remove all cache directories
```

This package enforces code quality at three stages to keep the codebase clean
and ensure that what works locally also works in CI.

1. **`make lint-verify`** runs Ruff and Mypy in read-only mode — catch style and type errors early.
2. **Pre-commit hooks** ensure badly formatted or broken code never reaches the remote repository.
3. **GitHub Actions** triggers on every push and blocks any pull request that fails linting or tests.
