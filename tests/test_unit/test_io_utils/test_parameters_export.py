from pathlib import Path

import pendulum
import pytest

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.io_utils.parameters import ExportParameters, MultiProcessingParameters, Parameters, SolverParameters
from atlas.io_utils.utils import FrozenBaseModel
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters, TaskModule
from atlas.orchestrator.module_registry import ModuleRegistry
from atlas.orchestrator.workflow.parameters import Step, WorkflowParameters


class DummyLeaf(FrozenBaseModel):
    value: int = 2


class DummyBranch(FrozenBaseModel):
    leaf: DummyLeaf = DummyLeaf()


class DummyTree(Parameters):
    branch: DummyBranch = DummyBranch()


PARAMETERS_DIR = Path("tests/dataset/parameters")
DATASET_PATH = Path("tests/dataset/day_ahead/day_ahead_input")
DAY_AHEAD_ORDERS_PARAMETERS = PARAMETERS_DIR / "day_ahead/day_ahead_orders.yml"
MARKET_CLEARING_PARAMETERS = PARAMETERS_DIR / "day_ahead/market_clearing.yml"
EXECUTION_DATE = pendulum.datetime(2028, 9, 26, 11)

TEMPORAL = {
    "start_date": "2028-09-27T00:00:00+02:00",
    "end_date": "2028-09-28T00:00:00+02:00",
    "execution_date": "2028-09-26T12:00:00+02:00",
}


class DummyModuleParameters(AbstractModuleParameters):
    """Parameters a module needs to be executed."""

    solver: SolverParameters = SolverParameters()  # type: ignore[call-arg]
    multiprocessing: MultiProcessingParameters = MultiProcessingParameters()
    export: ExportParameters = ExportParameters()

    ratio: float = 0.5
    count: int = 3
    flag: bool = True
    name: str = "dummy"
    output: Path
    optional_value: float | None = None


def test_dummy_tree(tmp_path):
    """Verify the recursive trees are accounted for"""
    tree = DummyTree.from_dict({"branch": {"leaf": {"value": 5}}})

    file_path = tmp_path / "exported.yaml"
    tree.parameters_to_yaml(file_path)
    assert DummyTree.from_file(file_path).branch.leaf.value == 5


def test_module_parameters_round_trip_from_parameter(tmp_path):
    """Test the dummy module parameters reload into the same parameters"""
    parameters = DummyModuleParameters(
        temporal=TEMPORAL,
        ratio=1,
        count=3,
        name="dummy",
        output=Path("output/"),
        optional_value=None,
        export=ExportParameters(export_results=True, export_dataset=True),
    )
    file_path = tmp_path / "exported.yaml"
    parameters.parameters_to_yaml(file_path)

    assert DummyModuleParameters.from_file(file_path) == parameters


@pytest.mark.parametrize(
    ("parameters_file", "module_name"),
    [
        ("day_ahead/day_ahead_orders.yml", "DayAheadOrders"),
        ("day_ahead/market_clearing.yml", "MarketClearing"),
        ("day_ahead/portfolio_optimisation.yml", "PortfolioOptimisation"),
        ("intraday/intraday_orders.yml", "IntradayOrders"),
        ("intraday/intraday_price_forecast.yml", "IntradayPriceForecast"),
        ("intraday/market_clearing.yml", "MarketClearing"),
        ("intraday/portfolio_optimisation_1.yml", "PortfolioOptimisation"),
        ("intraday/portfolio_optimisation_2.yml", "PortfolioOptimisation"),
    ],
)
def test_module_parameters_round_trip_from_file(parameters_file, module_name, tmp_path):
    """The exported yaml of every test dataset parameter file reloads into the same parameters."""

    parameters_class = ModuleRegistry.get(module_name).get_parameters_class()
    parameters = parameters_class.from_file(Path(__file__).parents[3] / PARAMETERS_DIR / parameters_file)
    file_path = tmp_path / "exported.yaml"
    parameters.parameters_to_yaml(file_path)
    assert parameters_class.from_file(file_path) == parameters


def test_workflow_parameters_round_trip_from_file(tmp_path):
    """The exported yaml of the test workflow reloads into the same parameters."""

    parameters = WorkflowParameters.from_file(Path(__file__).parents[3] / PARAMETERS_DIR / "day_ahead/workflow.yml")

    # parameters=ActionPlanParameters.from_file(Path(__file__).parents[3] / PARAMETERS_DIR / parameters_file)
    file_path = tmp_path / "exported.yaml"
    parameters.parameters_to_yaml(file_path)
    assert WorkflowParameters.from_file(file_path) == parameters


def test_workflow_parameters_round_trip_from_parameter(tmp_path):
    """Test the dummy workflow parameters reload into the same parameters"""
    parameters = WorkflowParameters(
        name="workflow",
        dataset_path=DATASET_PATH,
        export_final_state=False,
        steps=[
            Step(name="DayAheadOrders", module=ModuleRegistry.DayAheadOrders, parameters=DAY_AHEAD_ORDERS_PARAMETERS),
            Step(name="MarketClearing", module=ModuleRegistry.MarketClearing, parameters=MARKET_CLEARING_PARAMETERS),
        ],
    )
    file_path = tmp_path / "exported.yaml"
    parameters.parameters_to_yaml(file_path)
    assert WorkflowParameters.from_file(file_path) == parameters


def test_actionplan_parameters_round_trip_from_file(tmp_path):
    """The exported yaml of the test action plan parameter file reloads into the same parameters."""

    parameters = ActionPlanParameters.from_file(
        Path(__file__).parents[3] / PARAMETERS_DIR / "day_ahead/action_plan.yml"
    )
    file_path = tmp_path / "exported.yaml"
    parameters.parameters_to_yaml(file_path)
    assert ActionPlanParameters.from_file(file_path) == parameters


def test_actionplan_parameters_round_trip_from_parameter(tmp_path):
    """Test the dummy action plan parameters reload into the same parameters"""
    parameters = ActionPlanParameters(
        name="action_plan",
        dataset_path=DATASET_PATH,
        export_final_state=False,
        tasks=[
            TaskModule(
                name="DayAheadOrders",
                module=ModuleRegistry.DayAheadOrders,
                parameters=DAY_AHEAD_ORDERS_PARAMETERS,
                from_=EXECUTION_DATE,
                until=EXECUTION_DATE,
                frequency=pendulum.duration(days=1),
                priority=1,
            ),
            TaskModule(
                name="MarketClearing",
                module=ModuleRegistry.MarketClearing,
                parameters=MARKET_CLEARING_PARAMETERS,
                from_=EXECUTION_DATE,
                until=EXECUTION_DATE,
                frequency=pendulum.duration(days=1),
                priority=2,
            ),
        ],
    )
    file_path = tmp_path / "exported.yaml"
    parameters.parameters_to_yaml(file_path)
    assert ActionPlanParameters.from_file(file_path) == parameters
