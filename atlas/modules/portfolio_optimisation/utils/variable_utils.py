"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas.solver.solver_interface import OptimisationModel


def add_reserve_variables(
    model: OptimisationModel,
    name: str,
    time: DateTime,
    min_power: float,
    max_power: float,
    maximum_automated: float,
    relaxed_reserves: bool,
    storage_equipment: bool,
    thermal_equipment: bool,
):
    """
    Add reserve variables for solar/wind equipment.

    :param model: Optimization model
    :type model: OptimisationModel
    :param name: Equipment name
    :type name: str
    :param time: Current time period
    :type time: DateTime
    :param min_power: Minimum power output
    :type min_power: float
    :param max_power: Maximum power output
    :type max_power: float
    :param maximum_automated: Maximum automated reserve capacity
    :type maximum_automated: float
    :param relaxed_reserves: Whether to relax reserve constraints
    :type relaxed_reserves: bool
    :param storage_equipment: Whether this is storage equipment
    :type storage_equipment: bool
    :param thermal_equipment: Whether this is thermal equipment
    :type thermal_equipment: bool
    """
    model.add_continuous_variable(
        name=f"reserves_up_{name}_{time}",
        lower_bound=0,
        upper_bound=max_power,
    )
    model.add_continuous_variable(
        name=f"reserves_down_{name}_{time}",
        lower_bound=min_power if not thermal_equipment else 0,
        upper_bound=max_power,
    )
    model.add_continuous_variable(
        name=f"unprovided_reserves_up_{name}_{time}",
        lower_bound=0,
        upper_bound=max_power,
    )
    model.add_continuous_variable(
        name=f"unprovided_reserves_down_{name}_{time}",
        lower_bound=min_power if not thermal_equipment else 0,
        upper_bound=max_power,
    )
    model.add_continuous_variable(
        name=f"automated_reserves_up_{name}_{time}",
        lower_bound=0,
        upper_bound=maximum_automated,
    )
    if not storage_equipment:
        model.add_continuous_variable(
            name=f"automated_reserves_down_{name}_{time}",
            lower_bound=0,
            upper_bound=maximum_automated,
        )
    else:
        model.add_continuous_variable(
            name=f"automated_reserves_down_{name}_{time}",
            lower_bound=-maximum_automated,
            upper_bound=maximum_automated,
        )

    if relaxed_reserves:
        model.add_continuous_variable(
            name=f"relaxed_reserves_{name}_{time}",
            lower_bound=min_power if not thermal_equipment else 0,
            upper_bound=0 if not thermal_equipment else min_power,
        )
