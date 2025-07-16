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
    """Add reserve variables for solar/wind equipment"""
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
    if not storage_equipment and not thermal_equipment:
        model.add_continuous_variable(
            name=f"contracted_diff_up_{name}_{time}",
            lower_bound=0,
            upper_bound=max_power,
        )
        model.add_continuous_variable(
            name=f"contracted_diff_down_{name}_{time}",
            lower_bound=min_power,
            upper_bound=max_power,
        )
        model.add_continuous_variable(
            name=f"automated_contracted_diff_up_{name}_{time}",
            lower_bound=0,
            upper_bound=max_power,
        )
        model.add_continuous_variable(
            name=f"automated_contracted_diff_down_{name}_{time}",
            lower_bound=min_power,
            upper_bound=max_power,
        )

    if relaxed_reserves:
        model.add_continuous_variable(
            name=f"relaxed_reserves_{name}_{time}",
            lower_bound=min_power if not thermal_equipment else 0,
            upper_bound=0 if not thermal_equipment else min_power,
        )
