"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""


def test_the_shared_builder_declares_the_power_of_each_step_of_the_window(build_thermal_dispatch, model):
    equipment, _, window = build_thermal_dispatch()

    for time in window:
        assert f"{equipment.name}_power_level_{time}" in model.variables
