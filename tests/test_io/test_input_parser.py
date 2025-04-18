import shutil
import tempfile
from pathlib import Path

import polars as pl
import pytest

import atlas.config as cfg
from atlas.io.input_parser import InputParser


# Dummy model to use in tests
class DummyModel:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# Patch the model mapping for testing
cfg.MODEL_MAPPING_NAME = {
    "dummy_model": DummyModel,
}


@pytest.fixture(scope="class")
def temp_dir_with_csv(request):
    """Creates a temporary directory with a test CSV file."""
    temp_dir = tempfile.mkdtemp()
    csv_path = Path(temp_dir) / "dummy_model.csv"
    csv_path.write_text("name,value\nfoo,1\nbar,2\n")

    request.cls.temp_dir = Path(temp_dir)
    request.cls.csv_path = csv_path
    yield

    shutil.rmtree(temp_dir)


@pytest.mark.usefixtures("temp_dir_with_csv")
class TestInputParser:
    def test_from_file_csv(self):
        df = InputParser.from_file(self.csv_path)
        assert isinstance(df, pl.DataFrame)
        assert df.shape == (2, 2)
        assert df.columns == ["name", "value"]

    def test_from_directory_instantiates_objects(self):
        results = InputParser.from_directory(self.temp_dir)
        assert "dummy_model" in results
        objects = results["dummy_model"]
        assert len(objects) == 2
        assert isinstance(objects[0], DummyModel)
        assert objects[0].name == "foo"
        assert objects[1].value == 2

    def test_parse_business_objects(self):
        results = InputParser.parse_business_objects(self.temp_dir)
        assert "dummy_model" in results
        assert isinstance(results["dummy_model"], pl.DataFrame)

    def test_load_metadata(self):
        metadata_path = self.temp_dir / "metadata.json"
        metadata_path.write_text('{"author": "test"}')
        meta = InputParser.load_metadata(self.temp_dir)
        assert meta["author"] == "test"

    def test_load_timeseries_profile(self):
        df = InputParser.load_timeseries_profile(self.temp_dir, self.csv_path.name)
        assert isinstance(df, pl.DataFrame)

    def test_missing_directory_raises(self):
        with pytest.raises(FileNotFoundError):
            InputParser.from_directory("non_existent_dir_xyz")
