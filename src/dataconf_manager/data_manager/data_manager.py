"""
DataManager: read and write Polars DataFrames from/to local disk.

Routing is based on file extension. No configuration required.

Design principles
-----------------
- Single responsibility. The DataManager only handles serialization.
  Business logic, validation, and transformation live elsewhere.
- Fail fast. Unsupported formats and missing files raise immediately
  with a clear message, rather than silently returning None or empty data.
- Non-destructive by default. Overwriting an existing file requires
  opt-in via overwrite=True and logs a warning when it happens.
- Format-agnostic interface. Format-specific options (e.g. sheet_name
  for .xlsx) are forwarded via **kwargs to the underlying Polars reader,
  keeping the public API stable as formats are added.

TODO @Maxime 2026-05-21: extend to support remote storage (S3, GCS, Azure Blob).
This would require abstracting read/write handlers behind a StorageBackend
interface and reorganizing into src/data_manager/local/ and
src/data_manager/remote/ sub-packages.

TODO @Maxime 2026-05-21: extend to support ML model serialization
(joblib, pickle, safetensors) via a dedicated ModelManager class.
"""

import logging
from pathlib import Path
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)

_SUPPORTED_READ_FORMATS: frozenset[str] = frozenset(
    {".csv", ".parquet", ".xlsx", ".json"}
)
_SUPPORTED_WRITE_FORMATS: frozenset[str] = frozenset(
    {".csv", ".parquet", ".xlsx", ".json"}
)


class DataManager:
    """
    Reads and writes Polars DataFrames from/to local disk based on file extension.

    Supported formats: CSV, Parquet, Excel (.xlsx), JSON (tabular only).
    Non-tabular JSON (arbitrary dicts or lists) is out of scope -- use json.load().
    Format-specific options (e.g. sheet_name for .xlsx) can be passed as **kwargs.

    TODO @Maxime 2026-05-21: extend to support remote storage (S3, GCS, Azure Blob).
    This would require abstracting read/write handlers behind a StorageBackend
    interface and reorganizing into src/data_manager/local/ and
    src/data_manager/remote/ sub-packages.

    TODO @Maxime 2026-05-21: extend to support ML model serialization
    (joblib, pickle, safetensors) via a dedicated ModelManager class.
    """

    def read(self, path: str | Path, **kwargs: Any) -> pl.DataFrame:
        """
        Reads a file from disk and returns a Polars DataFrame.

        Parameters
        ----------
        path:
            Path to the file to read.
        **kwargs:
            Forwarded to the underlying Polars reader.
            e.g. sheet_name="Sheet2" for .xlsx files.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ValueError
            If the file format is not supported.
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        ext: str = path.suffix.lower()
        if ext not in _SUPPORTED_READ_FORMATS:
            raise ValueError(
                f"Unsupported read format: '{ext}'. "
                f"Must be one of: {_SUPPORTED_READ_FORMATS}"
            )

        logger.info(f"Reading {ext} file from {path}")

        match ext:
            case ".csv":
                return pl.read_csv(path)
            case ".parquet":
                return pl.read_parquet(path)
            case ".xlsx":
                return pl.read_excel(path, **kwargs)  # type: ignore
            case ".json":
                return pl.read_json(path)
            case _:
                raise ValueError(f"Unsupported read format: '{ext}'")

    def write(self, df: pl.DataFrame, path: str | Path, overwrite: bool = True) -> None:
        """
        Writes a Polars DataFrame to disk.

        Creates parent directories automatically if they do not exist.
        Logs a warning when overwriting an existing file.

        Parameters
        ----------
        df:
            DataFrame to write.
        path:
            Destination file path.
        overwrite:
            If False, raises FileExistsError when the file already exists.
            Defaults to True.

        Raises
        ------
        ValueError
            If the file format is not supported.
        FileExistsError
            If the file already exists and overwrite is False.
        """
        path = Path(path)
        ext: str = path.suffix.lower()

        if ext not in _SUPPORTED_WRITE_FORMATS:
            raise ValueError(
                f"Unsupported write format: '{ext}'. "
                f"Must be one of: {_SUPPORTED_WRITE_FORMATS}"
            )

        if path.exists():
            if not overwrite:
                raise FileExistsError(
                    f"File already exists: {path}. Use overwrite=True to replace it."
                )
            logger.warning(f"Overwriting existing file: {path}")

        # Create parent directories if they do not exist
        path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Writing {ext} file to {path} ({df.height} rows, {df.width} cols)")

        match ext:
            case ".csv":
                df.write_csv(path)
            case ".parquet":
                df.write_parquet(path)
            case ".xlsx":
                df.write_excel(path)
            case ".json":
                df.write_json(path)
            case _:
                raise ValueError(f"Unsupported write format: '{ext}'")
