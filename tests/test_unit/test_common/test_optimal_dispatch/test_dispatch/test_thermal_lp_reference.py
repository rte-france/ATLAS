"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Characterisation of the thermal dispatch formulation against reference LP files.

The portfolio optimisation LP references only exercise one initial power profile per
combination. These build the thermal dispatch alone, for every combination and several
states of the unit before the horizon, so that the initial conditions and the constraints
around the start date are pinned whatever the path they take.

Set ``ATLAS_REGENERATE_THERMAL_LP=1`` to rewrite the references from the current formulation.
"""

import os
import tempfile
from pathlib import Path

import pendulum
import pytest

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput
from atlas.io_utils.parameters import DateParameters
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock
from atlas.solver.solver_helper import SolverHelper
from atlas.solver.solver_interface import OptimisationModel

REFERENCE_DIR = Path(__file__).parent / "lp_files" / "thermal_dispatch"
REGENERATE = os.environ.get("ATLAS_REGENERATE_THERMAL_LP") == "1"

START = pendulum.datetime(2024, 1, 1)
EXECUTION = START.subtract(days=1)
TIMESTEP = pendulum.duration(hours=1)
WINDOW = [START + k * TIMESTEP for k in range(6)]

DURATIONS = {
    1: {},
    2: {"shutdown_duration": pendulum.duration(hours=2)},
    3: {"minimum_stable_power_duration": pendulum.duration(hours=2)},
    4: {"startup_duration": pendulum.duration(hours=2)},
    5: {"shutdown_duration": pendulum.duration(hours=2), "minimum_stable_power_duration": pendulum.duration(hours=2)},
    6: {"startup_duration": pendulum.duration(hours=2), "minimum_stable_power_duration": pendulum.duration(hours=2)},
    7: {"shutdown_duration": pendulum.duration(hours=2), "startup_duration": pendulum.duration(hours=2)},
    8: {
        "shutdown_duration": pendulum.duration(hours=2),
        "startup_duration": pendulum.duration(hours=2),
        "minimum_stable_power_duration": pendulum.duration(hours=2),
    },
}

#: Power of the unit over the 8 hours before the horizon (maximum 200 MW, minimum 50 MW),
#: None when no power was planned yet (day zero).
PROFILES: dict[str, list[float] | None] = {
    "day_zero": None,
    "off": [0.0] * 8,
    "full": [200.0] * 8,
    "flat_then_down": [150.0] * 7 + [120.0],
    "starting": [0.0] * 5 + [25.0, 50.0, 100.0],
    "stopping": [200.0] * 4 + [100.0, 50.0, 25.0, 0.0],
    "below_minimum": [200.0] * 6 + [120.0, 30.0],
}


def _flat(value: float) -> Timeseries:
    return Timeseries.from_index(START.subtract(days=1), TIMESTEP, START.add(days=1), default_value=value)


def _equipment(combination: int, profile: list[float] | None) -> ThermalDispatchInput:
    control_block = ControlBlock(name="cb")
    market_area = MarketArea(name="ma", control_block=control_block)
    power = None
    if profile is not None:
        planned = Timeseries.from_values(START - len(profile) * TIMESTEP, TIMESTEP, profile)
        power = ForecastingMatrix().add(planned, EXECUTION)
    return ThermalDispatchInput(
        name="th",
        node=Node(name="node", control_block=control_block, market_area=market_area),
        portfolio=Portfolio(name="pf", control_block=control_block, market_area=market_area),
        maximum_power=_flat(200.0),
        minimum_power=_flat(50.0),
        maximum_gradient=1.0,
        minimum_time_on=pendulum.duration(hours=3),
        minimum_time_off=pendulum.duration(hours=2),
        power=power,
        **({"minimum_stable_power_duration": pendulum.duration(hours=0)} | DURATIONS[combination]),
    )


def _export_lp(combination: int, profile: str, path: Path) -> None:
    parameters = AbstractModuleParameters(
        temporal=DateParameters(
            start_date=START, end_date=WINDOW[-1] + TIMESTEP, execution_date=EXECUTION, timestep=TIMESTEP
        )
    )
    model = OptimisationModel("SCIP", f"thermal_{combination}_{profile}")
    dispatch = ThermalDispatch(_equipment(combination, PROFILES[profile]))
    dispatch.setup(model, parameters)
    dispatch.add_variables(WINDOW)
    for time in WINDOW:
        dispatch.add_constraints(model, time, parameters)
        if time in WINDOW[:-2]:
            dispatch.add_dd_and_gradient_constraints(model, time, time - TIMESTEP)
    model.set_direction("minimize")
    model.set_objective(sum(dispatch.power_level[time] for time in WINDOW))
    model.export_model(path)


@pytest.mark.parametrize("profile", sorted(PROFILES))
@pytest.mark.parametrize("combination", sorted(DURATIONS))
def test_formulation_matches_reference(combination, profile):
    reference = REFERENCE_DIR / f"combination-{combination}-{profile}.lp"
    if REGENERATE:
        REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
        _export_lp(combination, profile, reference)

    with tempfile.TemporaryDirectory() as tmpdir:
        generated = Path(tmpdir) / "generated.lp"
        _export_lp(combination, profile, generated)
        comparison = SolverHelper.compare_lp_problems(
            SolverHelper.read_lp_ortools(str(reference)),
            SolverHelper.read_lp_ortools(str(generated)),
            output_dir=tmpdir,
            pb1_name="Reference",
            pb2_name="Generated",
            tolerance=1e-9,
            normalize_names=True,
            keep_identical=False,
        )

    for category in ("objectives", "variables", "constraints"):
        assert comparison[category]["modified"] == 0, f"Modified {category}"
        assert comparison[category]["only_legacy"] == 0, f"{category} only in the reference"
        assert comparison[category]["only_atlas"] == 0, f"{category} only in the generated LP"
