"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from types import SimpleNamespace

import pendulum

from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.utils.result_extraction import _extract_hydro

TIMES = [pendulum.datetime(2028, 9, 27, hour) for hour in range(3)]


def _values(times: list, values: list[float]) -> Timeseries:
    return Timeseries({"time": times, "value": values})


class TestHydroExtraction:
    def test_fragments_are_summed_on_the_union_of_their_timesteps(self):
        # fragment 0 is too small to bid at the last timestep, fragment 2 is never kept
        hydro = SimpleNamespace(name="hy", fragment_data={0: None, 1: None, 2: None})
        solution = {
            "hy_power_level_frag_0": _values(TIMES[:2], [10.0, 10.0]),
            "hy_power_level_frag_1": _values(TIMES, [5.0, 5.0, 15.0]),
            "hy_stored_energy": _values(TIMES, [100.0, 90.0, 80.0]),
        }

        schedule = _extract_hydro(hydro, solution)

        assert schedule.power.values == [15.0, 15.0, 15.0]
        assert schedule.stored_energy.values == [100.0, 90.0, 80.0]
