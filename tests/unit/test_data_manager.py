import logging
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from dataconf_manager import DataManager


@pytest.fixture
def dm() -> DataManager:
    return DataManager()


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"]})


# -------------------------------------------------------------------------
# read + write — round trip per format
# -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    ["data.csv", "data.parquet", "data.json"],
    ids=["csv", "parquet", "json"],
)
def test_read_write_round_trip(
    tmp_path: Path, dm: DataManager, sample_df: pl.DataFrame, filename: str
) -> None:
    path = tmp_path / filename
    dm.write(sample_df, path)
    assert_frame_equal(dm.read(path), sample_df)


def test_read_write_round_trip_xlsx(
    tmp_path: Path, dm: DataManager, sample_df: pl.DataFrame
) -> None:
    # Excel is tested separately as it requires sheet_name kwarg support
    path = tmp_path / "data.xlsx"
    dm.write(sample_df, path)
    assert_frame_equal(dm.read(path), sample_df)


def test_read_xlsx_with_sheet_name(
    tmp_path: Path, dm: DataManager, sample_df: pl.DataFrame
) -> None:
    path = tmp_path / "data.xlsx"
    sample_df.write_excel(path, worksheet="MySheet")
    assert_frame_equal(dm.read(path, sheet_name="MySheet"), sample_df)


# -------------------------------------------------------------------------
# read — error cases
# -------------------------------------------------------------------------


def test_read_file_not_found(tmp_path: Path, dm: DataManager) -> None:
    with pytest.raises(FileNotFoundError, match="File not found"):
        dm.read(tmp_path / "missing.csv")


@pytest.mark.parametrize(
    "filename",
    ["data.txt", "data.xml", "data.html"],
    ids=["txt", "xml", "html"],
)
def test_read_unsupported_format(
    tmp_path: Path, dm: DataManager, filename: str
) -> None:
    path = tmp_path / filename
    path.touch()
    with pytest.raises(ValueError, match="Unsupported read format"):
        dm.read(path)


# -------------------------------------------------------------------------
# write — behavior
# -------------------------------------------------------------------------
def test_write_creates_parent_directories(
    tmp_path: Path, dm: DataManager, sample_df: pl.DataFrame
) -> None:
    path = tmp_path / "nested" / "deep" / "data.csv"
    dm.write(sample_df, path)
    assert path.exists()


def test_write_overwrite_true_replaces_file(
    tmp_path: Path, dm: DataManager, sample_df: pl.DataFrame
) -> None:
    path = tmp_path / "data.csv"
    dm.write(sample_df, path)
    new_df = pl.DataFrame({"id": [99], "name": ["New"]})
    dm.write(new_df, path, overwrite=True)
    assert_frame_equal(dm.read(path), new_df)


def test_write_overwrite_logs_warning(
    tmp_path: Path,
    dm: DataManager,
    sample_df: pl.DataFrame,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / "data.csv"
    dm.write(sample_df, path)
    with caplog.at_level(logging.WARNING):
        dm.write(sample_df, path, overwrite=True)
    assert "Overwriting existing file" in caplog.text


# -------------------------------------------------------------------------
# write — error cases
# -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    ["data.txt", "data.xml", "data.html"],
    ids=["txt", "xml", "html"],
)
def test_write_unsupported_format(
    tmp_path: Path, dm: DataManager, sample_df: pl.DataFrame, filename: str
) -> None:
    with pytest.raises(ValueError, match="Unsupported write format"):
        dm.write(sample_df, tmp_path / filename)


def test_write_overwrite_false_raises_if_file_exists(
    tmp_path: Path, dm: DataManager, sample_df: pl.DataFrame
) -> None:
    path = tmp_path / "data.csv"
    dm.write(sample_df, path)
    with pytest.raises(FileExistsError, match="File already exists"):
        dm.write(sample_df, path, overwrite=False)
