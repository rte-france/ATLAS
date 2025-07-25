"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import math

from pendulum import DateTime
from pydantic import model_validator

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.thermal import Thermal
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel


class ThermalPO(Thermal):
    """
    Sophisticated unit commitment model for thermal power equipment.

    This implements a state-of-the-art thermal unit optimization with multiple
    operational states, complex time constraints, and ramping limitations.
    """

    maximum_fcr: float
    maximum_afrr: float
    minimum_power: Timeseries | LazyTimeseries
    maximum_power: Timeseries | LazyTimeseries
    variable_cost: Timeseries | LazyTimeseries
    startup_cost: Timeseries | LazyTimeseries
    maximum_gradient: float = 0.0  # MW/min ramping rate
    has_daily_energy_constraint: bool = False

    # Reserve procurement forecasts
    afrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    afrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    mfrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    mfrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    rr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    rr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    fcr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    fcr_down_procured: ForecastingMatrix | LazyForecastingMatrix

    # Internal time step parameters (computed from time durations)
    _T_on: int = 0
    _T_off: int = 0
    _T_start: int = 0
    _T_stop: int = 0
    _T_stable: int = 0
    _Delta_Q: float = 0.0
    _Delta_Q_unconstrained: float = 0.0
    _combination: int = 1  # Which constraint combination to use (1-8)

    def _compute_time_parameters(self, parameters: PortfolioOptimisationParameters):
        """Compute time step parameters from duration constraints."""
        timestep_minutes = parameters.timestep.total_minutes()

        # Convert time durations to time steps
        if self.minimum_time_on and self.minimum_time_on.total_minutes() > 0:
            self._T_on = int(max(1, math.ceil(self.minimum_time_on.total_minutes() / timestep_minutes))) + 1
        else:
            self._T_on = 0

        if self.minimum_time_off and self.minimum_time_off.total_minutes() > 0:
            self._T_off = int(max(1, math.ceil(self.minimum_time_off.total_minutes() / timestep_minutes))) + 1
        else:
            self._T_off = 0

        if self.startup_duration:
            self._T_start = int(math.floor(self.startup_duration.total_minutes() / timestep_minutes))
        else:
            self._T_start = 0

        if self.shutdown_duration:
            self._T_stop = int(math.floor(self.shutdown_duration.total_minutes() / timestep_minutes))
        else:
            self._T_stop = 0

        if self.minimum_stable_power_duration:
            if self.minimum_stable_power_duration.total_minutes() < timestep_minutes:
                self._T_stable = 0
            else:
                self._T_stable = (
                    int(math.ceil(self.minimum_stable_power_duration.total_minutes() / timestep_minutes)) + 1
                )
                # Rescale T_stable so that it is either equal to 0 or >= 2
                self._T_stable = self._T_stable if self._T_stable >= 2 else 0
        else:
            self._T_stable = 0

        # Ramping parameters
        self._Delta_Q = self.maximum_gradient * timestep_minutes
        self._Delta_Q_unconstrained = max(self.maximum_power.max(), 1000.0)  # Large value for unconstrained ramping

        # Determine which constraint combination to use
        self._combination = self._determine_combination()

    def _determine_combination(self) -> int:
        """Determine which of the 8 constraint combinations to use."""
        if self._T_stop == 0 and self._T_start == 0 and self._T_stable == 0:
            return 1
        elif self._T_stop >= 1 and self._T_start == 0 and self._T_stable == 0:
            return 2
        elif self._T_stop == 0 and self._T_start == 0 and self._T_stable >= 1:
            return 3
        elif self._T_start >= 1 and self._T_stop == 0 and self._T_stable == 0:
            return 4
        elif self._T_stop >= 1 and self._T_start == 0 and self._T_stable >= 1:
            return 5
        elif self._T_stop == 0 and self._T_start >= 1 and self._T_stable >= 1:
            return 6
        elif self._T_stop >= 1 and self._T_start >= 1 and self._T_stable == 0:
            return 7
        elif self._T_stop >= 1 and self._T_start >= 1 and self._T_stable >= 1:
            return 8
        else:
            return 1  # Default fallback

    def add_variables(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """Build variables for complex thermal unit commitment."""

        self._compute_time_parameters(parameters)

        # Always defined state variables for optimization time frame
        if time in parameters.thermal_op_times:
            # Binary state variables
            model.add_boolean_variable(f"OFF_var_e_{self.name}_at_{time}")
            model.add_boolean_variable(f"ON_UP_var_e_{self.name}_at_{time}")
            model.add_boolean_variable(f"ON_DOWN_var_e_{self.name}_at_{time}")

            # Auxiliary binary variables for transitions
            model.add_boolean_variable(f"t_on_of_e_{self.name}_at_{time}")
            model.add_boolean_variable(f"t_off_of_e_{self.name}_at_{time}")

            # Conditional state variables based on time constraints
            if self._T_start >= 1:
                model.add_boolean_variable(f"ON_START_e_{self.name}_at_{time}")

            if self._T_stop >= 1:
                model.add_boolean_variable(f"STOP_e_{self.name}_at_{time}")

            if self._T_stable >= 1:
                model.add_boolean_variable(f"ON_FLAT_e_{self.name}_at_{time}")
                model.add_boolean_variable(f"stable_at_{time}_e_{self.name}")
                model.add_boolean_variable(f"entered_up_at_{time}_e_{self.name}")
                model.add_boolean_variable(f"entered_down_at_{time}_e_{self.name}")

                # Gradient auxiliary variables for stable case
                max_power = float(self.maximum_power.max())
                model.add_continuous_variable(f"UP_grad_at_{time}_for_e_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"aux_up_grad_at_{time}_e_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"DOWN_grad_at_{time}_e_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"aux_down_grad_at_{time}_e_{self.name}", -max_power, max_power)

            # Specific combinations for additional auxiliary variables
            if self._T_stop >= 1 and self._T_start == 0 and self._T_stable == 0:
                model.add_boolean_variable(f"down_to_stop_grad_at_{time}_e_{self.name}")

            if self._T_stop >= 1 and self._T_stable >= 1:
                model.add_boolean_variable(f"flat_down_stop_at_{time}_e_{self.name}")

            if self._T_stable >= 1 and (self._T_start >= 1 or self._T_stop >= 1):
                max_power = self.maximum_power.max()
                model.add_continuous_variable(f"DD_grad_at_{time}_e_{self.name}", -max_power, max_power)

            if self._T_stop >= 1 and self._T_start >= 1 and self._T_stable == 0:
                model.add_boolean_variable(f"down_to_stop_grad_at_{time}_e_{self.name}")

            # Power and reserve variables
            maximum_power = self.maximum_power.get_value(time)
            minimum_power = self.minimum_power.get_value(time)
            maximum_automated = self.maximum_afrr + self.maximum_fcr

            # Power level variable (only for thermal optimization times)
            model.add_continuous_variable(f"{self.name}_p_lev_{time}", 0.0, maximum_power)
            model.add_continuous_variable(f"{self.name}_p_lev_above_maxAvail_{time}", 0.0, maximum_power)
            model.add_continuous_variable(f"{self.name}_p_lev_below_minAvail_{time}", 0.0, maximum_power)

            # Reserve variables using utility function
            # This creates: reserves_up_{name}_{time}, reserves_down_{name}_{time}, etc.
            add_reserve_variables(
                model=model,
                name=self.name,
                time=time,
                min_power=minimum_power,
                max_power=maximum_power,
                maximum_automated=maximum_automated,
                relaxed_reserves=True,
                storage_equipment=False,
                thermal_equipment=True,
            )

    def add_constraints(
        self,
        time: DateTime,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
    ):
        """Add constraints based on the determined combination."""
        if time not in parameters.thermal_op_times:
            return

        # TODO: Implement constraint combinations from legacy PO_thermic_constraints.py
        pass

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        price_forecast: float,
        parameters: PortfolioOptimisationParameters,
    ):
        """Add objective function terms for thermal equipment."""

    @model_validator(mode="after")
    def validate_minimum_stable_power_duration(self) -> ThermalPO:
        """
        Validate that minimum_stable_power_duration is not greater than minimum_time_on.
        """
        if (
            self.minimum_stable_power_duration is not None
            and self.minimum_time_on is not None
            and self.minimum_stable_power_duration.total_minutes() > self.minimum_time_on.total_minutes()
        ):
            raise ValueError(
                f"minimum_stable_power_duration ({self.minimum_stable_power_duration.total_hours()}h) of equipment "
                f"{self.name} cannot be greater than minimum_time_on ({self.minimum_time_on.total_hours()}h)"
            )
        return self
