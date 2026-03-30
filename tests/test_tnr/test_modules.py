from pathlib import Path

import pytest

from atlas import AtlasDataset, DayAheadOrdersModule, MarketClearingModule, PortfolioOptimisationModule
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.timing import timer
from atlas.workflow.current_input_state import CurrentInputState
from atlas.workflow.handler.cis_handler import CISHandler

DATA_DIR = Path("tests/dataset/data/")
PARAMS_DIR = Path("tests/dataset/parameters/")

MODULE_CONFIGS = [
    (DayAheadOrdersModule, PARAMS_DIR / "day_ahead.yml", DATA_DIR / "day_ahead_input"),
    (MarketClearingModule, PARAMS_DIR / "market_clearing.yml", DATA_DIR / "market_clearing_input"),
    (PortfolioOptimisationModule, PARAMS_DIR / "portfolio_optimisation.yml", DATA_DIR / "portfolio_optimisation_input"),
]


def run_module(module_class: type[AbstractModule], config_path: Path, dataset_path: Path) -> None:
    input_data = AtlasDataset.from_directory(dataset_path)
    cis = CurrentInputState(input_data)
    module = module_class()
    parameters = module.get_parameters_class().from_file(config_path)
    output_dataset = module.run(input_data, parameters)
    CISHandler.apply(output_dataset.change_sets, cis)


@pytest.mark.parametrize("module_class, config_path, dataset_path", MODULE_CONFIGS)
def test_module_runs_successfully(
    module_class: type[AbstractModule],
    config_path: Path,
    dataset_path: Path,
):
    if not config_path.exists():
        pytest.skip(f"Module config not found: {config_path}")

    with timer() as t:
        run_module(module_class, config_path, dataset_path)

    print(f"\n⏱ {module_class.__name__}: {t()}s")
