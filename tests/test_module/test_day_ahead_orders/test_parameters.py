"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime, Duration
from pathlib import Path

import pytest
from pydantic import ValidationError

from atlas.enums import SolverEnum
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


def test_default_parameters():
    params = DayAheadOrdersParameters(start_date=DateTime.now(), end_date=DateTime.now(), execution_date=DateTime.now())
    assert params.output_folder == Path("DAO_lp_exports")
    assert params.export_lp == False
    assert params.proportional_reserves_penalty == True
    assert params.use_presolve == True
    assert params.automated_unprocured_reserves_penalty == 10000
    assert params.battery_smoothing_factor == 0.1
    assert params.ev_energy_coef == 1.5
    assert params.ev_smoothing_factor == 0.1
    assert params.epsilon == 0.001
    assert params.hydraulic_minimal_fragment_size == 100
    assert params.load_price == 3000
    assert params.manual_unprocured_reserves_penalty == 100
    assert params.phs_smoothing_factor == 0.2
    assert params.solver_duality_gap == 0.0001
    assert params.thermal_additional_hours == Duration(hours=12)
    assert params.battery_additional_hours == Duration(hours=48)
    assert params.battery_nb_fragments == 3
    assert params.ev_additional_hours == Duration(hours=144)
    assert params.ev_nb_fragments == 3
    assert params.phs_additional_hours == Duration(hours=144)
    assert params.phs_nb_fragments == 3
    assert params.solver_timeout == Duration(minutes=4)
    assert params.timestep == Duration(hours=1)
    assert params.price_forecasts_types == ["Medium", "High", "Low"]
    assert params.solver_name == "XPRESS"


def test_custom_parameters():
    params = DayAheadOrdersParameters(
        start_date=DateTime.now(),
        end_date=DateTime.now(),
        execution_date=DateTime.now(),
        timestep=Duration(minutes=15),
        solver_name=SolverEnum.XPRESS,
        automated_unprocured_reserves_penalty=1000,
        battery_smoothing_factor=0.2,
        ev_energy_coef=1.1,
        ev_smoothing_factor=0.2,
        epsilon=0.01,
        hydraulic_minimal_fragment_size=10,
        load_price=300,
        manual_unprocured_reserves_penalty=10,
        phs_smoothing_factor=0.3,
        solver_duality_gap=0.001,
        thermal_additional_hours=Duration(hours=10),
        battery_additional_hours=Duration(hours=40),
        battery_nb_fragments=2,
        ev_additional_hours=Duration(hours=100),
        ev_nb_fragments=2,
        phs_additional_hours=Duration(hours=100),
        phs_nb_fragments=2,
        solver_timeout=Duration(minutes=1),
        price_forecasts_types=["Medium"],
    )
    assert params.timestep == Duration(minutes=15)
    assert params.automated_unprocured_reserves_penalty == 1000
    assert params.battery_smoothing_factor == 0.2
    assert params.ev_energy_coef == 1.1
    assert params.ev_smoothing_factor == 0.2
    assert params.epsilon == 0.01
    assert params.hydraulic_minimal_fragment_size == 10
    assert params.load_price == 300
    assert params.manual_unprocured_reserves_penalty == 10
    assert params.phs_smoothing_factor == 0.3
    assert params.solver_duality_gap == 0.001
    assert params.thermal_additional_hours == Duration(hours=10)
    assert params.battery_additional_hours == Duration(hours=40)
    assert params.battery_nb_fragments == 2
    assert params.ev_additional_hours == Duration(hours=100)
    assert params.ev_nb_fragments == 2
    assert params.phs_additional_hours == Duration(hours=100)
    assert params.phs_nb_fragments == 2
    assert params.solver_timeout == Duration(minutes=1)
    assert params.price_forecasts_types == ["Medium"]


def test_invalid_timestep_raises():
    with pytest.raises(ValidationError):
        DayAheadOrdersParameters(timestep="")


def test_invalid_price_forecasts_types_raises():
    with pytest.raises(ValidationError):
        DayAheadOrdersParameters(price_forecasts_types=["test"])
