"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import pendulum
import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.result import MarketClearingResult

INPUT_DATASET_DIR = Path("tests/dataset/day_ahead/market_clearing_input")
PARAMETERS_PATH = Path("tests/dataset/parameters/day_ahead/market_clearing.yml")

INPUT_DATASET_ID_DIR = Path("tests/dataset/intraday/market_clearing_input")
PARAMETERS_ID_PATH = Path("tests/dataset/parameters/intraday/market_clearing.yml")


@pytest.fixture(scope="session")
def market_clearing_module() -> MarketClearingModule:
    return MarketClearingModule()


@pytest.fixture(scope="session")
def lp_export_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("market_clearing_run")


@pytest.fixture(scope="session")
def parameters(market_clearing_module: MarketClearingModule, lp_export_dir: Path) -> MarketClearingParameters:
    if not PARAMETERS_PATH.exists():
        pytest.skip(f"Market clearing parameters not found: {PARAMETERS_PATH}")
    params = market_clearing_module.import_parameters(PARAMETERS_PATH)
    params = params.evolve(
        export=params.export.evolve(run_dir=lp_export_dir), solver=params.solver.evolve(export_lp=True)
    )
    return params


@pytest.fixture(scope="session")
def atlas_data(parameters: MarketClearingParameters) -> AtlasDataset:
    if not INPUT_DATASET_DIR.exists():
        pytest.skip(f"Market clearing input dataset not found: {INPUT_DATASET_DIR}")
    data = AtlasDataset.from_directory(INPUT_DATASET_DIR)
    data.set_frequency_all(parameters.temporal.timestep, inplace=True)
    return data


@pytest.fixture(scope="session")
def input_dataset(
    market_clearing_module: MarketClearingModule,
    atlas_data: AtlasDataset,
    parameters: MarketClearingParameters,
) -> MarketClearingInputDataset:
    return market_clearing_module.import_data(atlas_data, parameters)


@pytest.fixture(scope="session")
def result(
    market_clearing_module: MarketClearingModule,
    atlas_data: AtlasDataset,
    parameters: MarketClearingParameters,
) -> tuple[MarketClearingResult, float]:
    start = pendulum.now()
    result = market_clearing_module.run(atlas_data, parameters)
    elapsed = (pendulum.now() - start).total_seconds()
    return result, elapsed


@pytest.fixture(scope="session")
def generated_lp_dir(result: tuple[MarketClearingResult, float], lp_export_dir: Path) -> Path:
    return lp_export_dir / "lp_export"


@pytest.fixture(scope="session")
def lp_export_id_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("market_clearing_id_run")


@pytest.fixture(scope="session")
def parameters_id(market_clearing_module: MarketClearingModule, lp_export_id_dir: Path) -> MarketClearingParameters:
    if not PARAMETERS_ID_PATH.exists():
        pytest.skip(f"Market clearing parameters not found: {PARAMETERS_ID_PATH}")
    params = market_clearing_module.import_parameters(PARAMETERS_ID_PATH)
    params = params.evolve(
        export=params.export.evolve(run_dir=lp_export_id_dir), solver=params.solver.evolve(export_lp=True)
    )
    return params


@pytest.fixture(scope="session")
def atlas_data_id(parameters: MarketClearingParameters) -> AtlasDataset:
    if not INPUT_DATASET_ID_DIR.exists():
        pytest.skip(f"Market clearing input dataset not found: {INPUT_DATASET_ID_DIR}")
    data = AtlasDataset.from_directory(INPUT_DATASET_ID_DIR)
    data.set_frequency_all(parameters.temporal.timestep, inplace=True)
    return data


@pytest.fixture(scope="session")
def input_dataset_id(
    market_clearing_module: MarketClearingModule,
    atlas_data_id: AtlasDataset,
    parameters_id: MarketClearingParameters,
) -> MarketClearingInputDataset:
    return market_clearing_module.import_data(atlas_data_id, parameters_id)


@pytest.fixture(scope="session")
def result_id(
    market_clearing_module: MarketClearingModule,
    atlas_data_id: AtlasDataset,
    parameters_id: MarketClearingParameters,
) -> tuple[MarketClearingResult, float]:
    start = pendulum.now()
    result = market_clearing_module.run(atlas_data_id, parameters_id)
    elapsed = (pendulum.now() - start).total_seconds()
    return result, elapsed


@pytest.fixture(scope="session")
def generated_lp_dir_id(result_id: tuple[MarketClearingResult, float], lp_export_id_dir: Path) -> Path:
    return lp_export_id_dir / "lp_export"
