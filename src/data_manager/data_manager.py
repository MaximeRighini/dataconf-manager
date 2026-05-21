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
    Reads and writes DataFrames from/to local disk based on file extension.

    Supported formats: CSV, Parquet, Excel (.xlsx), JSON (tabular only).
    Non-tabular JSON (arbitrary dicts or lists) is out of scope. use json.load().
    Format-specific options (e.g. sheet_name for .xlsx) can be passed as **kwargs.

    TODO @Maxime 2026-05-21: extend to support remote storage (S3, GCS, Azure Blob).
    This would require abstracting read/write handlers behind a StorageBackend
    interface and reorganizing into src/data_manager/local/ and
    src/data_manager/remote/ sub-packages.

    TODO @Maxime 2026-05-21: extend to support ML model serialization (joblib, pickle,
    safetensors) via a dedicated ModelManager class.
    """

    def read(self, path: str | Path, **kwargs: Any) -> pl.DataFrame:
        """
        Reads a file from disk and returns a Polars DataFrame.

        Raises ValueError for unsupported formats.
        Raises FileNotFoundError if the file does not exist.
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        ext = path.suffix.lower()
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

        Creates parent directories if they do not exist.
        Logs a warning when overwriting an existing file.
        Raises ValueError for unsupported formats.

        Args:
            df: DataFrame to write.
            path: Destination file path.
            overwrite: If False, raises FileExistsError when the file already exists.
        """
        path = Path(path)
        ext = path.suffix.lower()

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
