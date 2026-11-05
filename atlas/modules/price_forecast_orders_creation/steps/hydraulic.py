"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from xmlrpc.client import DateTime

from pyarrow.lib import duration

import atlas.config as cfg
from atlas import AbstractScenarioMatrix
from atlas.enums import OrderType
from atlas.modules.price_forecast_orders_creation.steps.abstract_step import AbstractOrderStep, StepResult


class HydraulicStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        """
        The formulation of hydro units follows the same fragment logic as in the DAO.
        The original input dispatch from Antares is converted into fragments first, which are priced
        based on the water values estimated according to the base StoredEnergy (again) from Antares.
        """
        result = StepResult()

        for equipment in self.dataset.hydro:
            stored_energy = equipment.stored_energy.get_forecast(
                self.parameters.default_exec_date,
                self.parameters.temporal.start_date - duration(days=2),
                self.parameters.penultimate_date,
            )

            # Track the case of non ReservoirManagement
            has_stored = True

            if not stored_energy.index:
                has_stored = False
            elif abs(stored_energy.max()) <= self.parameters.epsilon:
                cfg.logger.warning(f"Empty hydro equipment {equipment.name}")

            for time in self.orders_time:
                # Translate the Antares dispatch into fragments (with their volumes and prices)
                if has_stored:
                    local_stored_energy = stored_energy.get_value(time)
                else:
                    local_stored_energy = equipment.initial_level.get_value(time)

                base_water_value = self._extract_mean_from_scenario(
                    equipment.storage_marginal_value, local_stored_energy, time
                )

                qmax_sum = 0
                dispatch_reached = False

                for local_enum, local_percentage in enumerate(equipment.FragmentVolumes):
                    if dispatch_reached:
                        continue

                    # ------ Order Creation
                    qmax = local_percentage * equipment.MaximumPower.GetValue(time)

                    if qmax_sum + qmax > equipment.antares_dispatch.get_value(time):
                        qmax = equipment.antares_dispatch.get_value(time) - qmax_sum
                        dispatch_reached = True

                    price = max(base_water_value + equipment.FragmentPrices[local_enum], 0)

                    order = self.create_order(
                        time=time,
                        equipment=equipment,
                        order_type=OrderType.Sell,
                        price=price,
                        qmin=0,
                        qmax=qmax,
                        is_agent_tso=False,
                        suffix_name="_frag_" + str(local_enum),
                    )
                    if order is not None:
                        result.orders.append(order)

                    qmax_sum += qmax

        return result

    # Function extracting a "squared" mean from a ScenarioMatrix
    def _extract_mean_from_scenario(
        self, scenario_matrix: AbstractScenarioMatrix, index_input: float, time_input: DateTime
    ) -> float:
        """
        Function extracting the "squared" mean from a ScenarioMatrix, given an index_input and a time_input.
        Its aim is to return a linear interpolation of the values in the scenario_matrix between:
        - The index value preceeding index_input and the index value following index_input
        - The time preceeding time_input and the time following time_input
        IMPORTANT REMARK : We assume in this function that the index of
        the scenario_matrix is correctly ordered by increasing values
        """

        # --- Retrieve the index of the scenario_matrix and find the values preceeding and following index_input
        last_scenario_matrix_index = len(scenario_matrix.index) -1
        scenario_matrix_index = sorted(map(int,map(float, scenario_matrix.index)))

        preceding_index = "N/A"
        following_index = "N/A"
        current_enumeration = 0

        if not scenario_matrix_index:
            return 0

        # If the index_input is below the first (resp. above the last) index, send a warning and approximate index_input by the first (resp. last) index
        if index_input < scenario_matrix_index[0]:
            cfg.logger.warning(
                f"Squared mean function warning : The input index {str(index_input)} is below the first index {str(scenario_matrix_index[0])} of the ScenarioMatrix. "
                "Consequently, no index interpolation has been done, and the index_input is approximated by the first index"
            )
            preceding_index = scenario_matrix_index[0]
            following_index = scenario_matrix_index[0]

        elif index_input > scenario_matrix_index[last_scenario_matrix_index]:
            cfg.logger.warning(
                f"Squared mean function warning : The input index {str(index_input)} is above the last index {str(scenario_matrix_index[0])} of the ScenarioMatrix. "
                "Consequently, no index interpolation has been done, and the index_input is approximated by the last index"
            )
            preceding_index = scenario_matrix_index[last_scenario_matrix_index]
            following_index = scenario_matrix_index[last_scenario_matrix_index]

        # If the index_input is in [first_index, last_index]
        else:
            while current_enumeration <= last_scenario_matrix_index:
                current_index = scenario_matrix_index[current_enumeration]

                if current_index == index_input:
                    preceding_index = current_index
                    following_index = current_index

                elif index_input < current_index and preceding_index == "N/A":
                    preceding_index = scenario_matrix_index[current_enumeration - 1]
                    following_index = current_index

                current_enumeration += 1

        # --- Compute the linear interpolation between the preceeding time and the following time, for both the preceeding and the following index
        for index in scenario_matrix.indexes:
            timeseries_name = int(float(scenario_matrix.select(index).name))
            if timeseries_name == preceding_index:
                preceding_index_value = scenario_matrix.select(index).get_value(time_input)
            if timeseries_name == following_index:
                following_index_value = scenario_matrix.select(index).get_value(time_input)

        if preceding_index == following_index:
            return preceding_index_value

        preceding_to_following_index_difference = following_index - preceding_index
        preceding_to_input_index_difference = index_input - preceding_index

        return (
            preceding_index_value
            + (following_index_value - preceding_index_value)
            * preceding_to_input_index_difference
            / preceding_to_following_index_difference
        )
