"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pendulum import DateTime

import atlas.config as cfg
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.objects.equipment.thermal import Thermal
from atlas.solver.model_var import ModelVar
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes


class ThermalOptimizationModel(OptimisationModel):
    """
    This class modelize the optimization program associated to the thermic units. It only
    performs the optimization for one unit, passed as an argument.
    Optimization is done over the extended optimization period, ie between start_date - epsilon
    and end_optimization_date + epsilon where epsilon is an additional time corresponding to
    the maximum between the minimum duration time and the startup duration.
    Optimization is done with respect to a given price sequence given.
    """

    RESERVES_UP_EQUIP_KEY = "reservesUp_equip_"
    RESERVES_DOWN_EQUIP_KEY = "reservesDown_equip_"
    UNPROVIDED_RESERVES_UP_KEY = "unprovidedReservesUp_equip_"
    UNPROVIDED_RESERVES_DOWN_KEY = "unprovidedReservesDown_equip_"
    RELAXED_RESERVES_KEY = "relaxedReserves_equip_"
    AUTOMATED_RESERVES_UP_KEY = "automatedReservesUp_equip_"
    AUTOMATED_RESERVES_DOWN_KEY = "automatedReservesDown_equip_"
    CONTRACTED_DIFFERENCE_UP_KEY = "contractedDifferenceUp_equip_"
    CONTRACTED_DIFFERENCE_DOWN_KEY = "contractedDifferenceDown_equip_"
    AUTOMATED_CONTRACTED_DIFFERENCE_UP_KEY = "automatedContractedDifferenceUp_equip_"
    AUTOMATED_CONTRACTED_DIFFERENCE_DOWN_KEY = "automatedContractedDifferenceDown_equip_"
    AUX_UP_GRAD_AT_KEY = "aux_up_grad_at_"
    AUX_DOWN_GRAD_AT_KEY = "aux_down_grad_at_"
    OFF_EQUIP_AT_KEY = "OFF_equip_"
    ON_DOWN_EQUIP_AT_KEY = "ON_DOWN_equip_"
    ON_UP_EQUIP_AT_KEY = "ON_UP_equip_"
    START_EQUIP_AT_KEY = "START_equip_"
    STOP_EQUIP_AT_KEY = "STOP_equip_"
    ON_FLAT_EQUIP_AT_KEY = "ON_FLAT_equip_"
    TURNED_ON_EQUIP_AT_KEY = "turned_on_equip_"
    TURNED_OFF_EQUIP_AT_KEY = "turned_off_equip_"
    STABLE_AT_KEY = "stable_at_"
    ENTERED_UP_AT_KEY = "entered_up_at_"
    ENTERED_DOWN_AT_KEY = "entered_down_at_"
    POWER_EQUIP_KEY = "power_equip_"
    UP_GRAD_AT_KEY = "UP_grad_at_"
    DOWN_GRAD_AT_KEY = "DOWN_grad_at_"

    extended_start_date: DateTime
    q_lower: Timeseries
    q_upper: Timeseries
    reserves_up_procured: Timeseries
    reserves_down_procured: Timeseries
    feasible_automated_reserves_up_procured: Timeseries
    feasible_automated_reserves_down_procured: Timeseries
    last_power: Timeseries
    last_date: DateTime | None
    start_date_minus_one: DateTime
    time_frame_union_minus_one: list[DateTime]
    start_time_steps: range
    stop_time_steps: range

    def __init__(
        self,
        parameters: DayAheadOrdersParameters,
        thermal_unit: ThermalDAO,
        prices: Timeseries,
        price_type: str,
        solver_options: SolverOptions,
    ):
        """
        :param parameters: a DayAheadOrdersParameters instance
        :type parameters: DayAheadOrdersParameters
        :param thermal_unit: a Thermal instance
        :type thermal_unit: ThermalDAO
        :param prices: a price timeseries based on which optimization will be conducted.
        :type prices: Timeseries
        :param price_type: the price_type
        :type price_type: str
        :param solver_options: the solver options
        :type solver_options: SolverOptions
        """
        super().__init__(
            solver_name=parameters.solver.solver_name,
            name=f"Optimization program for thermal unit {thermal_unit.name}",
            options=solver_options,
        )
        self.parameters: DayAheadOrdersParameters = parameters
        # Quick sanity check on the class of the equipment supplied as input.
        if not isinstance(thermal_unit, Thermal):
            cfg.logger.error(f"Equipement {thermal_unit.name} is not of type thermic.")
            raise ValueError("Wrong equipment type for the thermic optimization program.")
        self.thermal_unit: ThermalDAO = thermal_unit
        self.prices: Timeseries = prices
        self.price_type: str = price_type
        self.time_frame: list[DateTime] = []
        self.previous_time_frame: list[DateTime] = []
        self.q = ModelVar(
            lambda t: self.get_variable(self.power_equip_at(t)),
            lambda t: self.add_continuous_variable(self.power_equip_at(t), 0, self.q_upper.get_value(t)),
        )
        self.OFF = ModelVar(
            lambda t: self.get_variable(self.off_equip_at(t)), lambda t: self.add_boolean_variable(self.off_equip_at(t))
        )
        self.ON_DOWN = ModelVar(
            lambda t: self.get_variable(self.on_down_equip_at(t)),
            lambda t: self.add_boolean_variable(self.on_down_equip_at(t)),
        )
        self.ON_UP = ModelVar(
            lambda t: self.get_variable(self.on_up_equip_at(t)),
            lambda t: self.add_boolean_variable(self.on_up_equip_at(t)),
        )
        self.START = ModelVar(
            lambda t: self.get_variable(self.start_equip_at(t)),
            lambda t: self.add_boolean_variable(self.start_equip_at(t)),
        )
        self.STOP = ModelVar(
            lambda t: self.get_variable(self.stop_equip_at(t)),
            lambda t: self.add_boolean_variable(self.stop_equip_at(t)),
        )
        self.ON_FLAT = ModelVar(
            lambda t: self.get_variable(self.on_flat_equip_at(t)),
            lambda t: self.add_boolean_variable(self.on_flat_equip_at(t)),
        )
        # Corresponding to the variable defined in sec. 6.1.1
        self.turned_on = ModelVar(
            lambda t: self.get_variable(self.turned_on_equip_at(t)),
            lambda t: self.add_continuous_variable(self.turned_on_equip_at(t), 0, 1),
        )
        # Corresponding to the variable defined in sec. 6.1.2
        self.turned_off = ModelVar(
            lambda t: self.get_variable(self.turned_off_equip_at(t)),
            lambda t: self.add_continuous_variable(self.turned_off_equip_at(t), 0, 1),
        )
        # This auxiliary variable indicates when the unit enters the FLAT state
        self.stable = ModelVar(
            lambda t: self.get_variable(self.stable_at(t)),
            lambda t: self.add_continuous_variable(self.stable_at(t), 0, 1),
        )
        # This variable replaces ON_UP in the definition of the gradient and will bound the gradient for only one time step
        self.entered_up = ModelVar(
            lambda t: self.get_variable(self.entered_up_at(t)),
            lambda t: self.add_continuous_variable(self.entered_up_at(t), 0, 1),
        )
        # Same as single_on_up but for on down
        self.entered_down = ModelVar(
            lambda t: self.get_variable(self.entered_down_at(t)),
            lambda t: self.add_continuous_variable(self.entered_down_at(t), 0, 1),
        )
        # This variable will be implemented in the gradient and bound the upward gradient
        self.U = ModelVar(
            lambda t: self.get_variable(self.up_grad_at(t)),
            lambda t: self.add_continuous_variable(self.up_grad_at(t), self.Q_min, self.Q_max),
        )
        # This variable will be implemented in the gradient and bound the downward gradient
        self.D = ModelVar(
            lambda t: self.get_variable(self.down_grad_at(t)),
            lambda t: self.add_continuous_variable(self.down_grad_at(t), self.Q_min, self.Q_max),
        )
        # Power gradients
        # Definition of the gradients_time_frame : starts at start_date - time_step and goes until T-1
        # Gradients are defined on a "shifted" time frame.
        self.gradients_time_frame = generate_datetimes(
            self.parameters.temporal.start_date - self.parameters.temporal.timestep,
            self.parameters.temporal.end_date
            + self.thermal_unit.additional_hours
            - 2 * self.parameters.temporal.timestep,
            self.parameters.temporal.timestep,
        )

        self.T_on: int = 0
        self.T_off: int = 0
        self.T_stable: int = 0
        self.T_start: int = 0
        self.T_stop: int = 0
        self.maximum_automated: float = 0.0
        self.automated_unsupplied_reserves: float = 0.0
        self.delta_q: float = 0.0
        self.delta_q_unconstrained: float = 0.0
        self.Q_max: float = 0.0
        self.Q_min: float = 0.0

        self._initial_setup()
        self._define_time_frame_variables()

    def off_equip_at(self, t: DateTime) -> str:
        return f"{self.OFF_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def on_down_equip_at(self, t: DateTime) -> str:
        return f"{self.ON_DOWN_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def on_up_equip_at(self, t: DateTime) -> str:
        return f"{self.ON_UP_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def start_equip_at(self, t: DateTime) -> str:
        return f"{self.START_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def stop_equip_at(self, t: DateTime) -> str:
        return f"{self.STOP_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def on_flat_equip_at(self, t: DateTime) -> str:
        return f"{self.ON_FLAT_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def turned_on_equip_at(self, t: DateTime) -> str:
        return f"{self.TURNED_ON_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def turned_off_equip_at(self, t: DateTime) -> str:
        return f"{self.TURNED_OFF_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def stable_at(self, t: DateTime) -> str:
        return f"{self.STABLE_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def entered_up_at(self, t: DateTime) -> str:
        return f"{self.ENTERED_UP_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def entered_down_at(self, t: DateTime) -> str:
        return f"{self.ENTERED_DOWN_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def power_equip_at(self, t: DateTime) -> str:
        return f"{self.POWER_EQUIP_KEY}{self.thermal_unit.name}_at_{t}"

    def up_grad_at(self, t: DateTime) -> str:
        return f"{self.UP_GRAD_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def down_grad_at(self, t: DateTime) -> str:
        return f"{self.DOWN_GRAD_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def reserves_up_equip_at(self, t: DateTime) -> str:
        return f"{self.RESERVES_UP_EQUIP_KEY}{self.thermal_unit.name}_at_{t}"

    def reserves_down_equip_at(self, t: DateTime) -> str:
        return f"{self.RESERVES_DOWN_EQUIP_KEY}{self.thermal_unit.name}_at_{t}"

    def unprovided_reserves_up_at(self, t: DateTime) -> str:
        return f"{self.UNPROVIDED_RESERVES_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def unprovided_reserves_down_at(self, t: DateTime) -> str:
        return f"{self.UNPROVIDED_RESERVES_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    def relaxed_reserves_at(self, t: DateTime) -> str:
        return f"{self.RELAXED_RESERVES_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_reserves_up_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_RESERVES_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_reserves_down_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_RESERVES_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    def contracted_difference_up_at(self, t: DateTime) -> str:
        return f"{self.CONTRACTED_DIFFERENCE_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def contracted_difference_down_at(self, t: DateTime) -> str:
        return f"{self.CONTRACTED_DIFFERENCE_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_contracted_difference_up_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_CONTRACTED_DIFFERENCE_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_contracted_difference_down_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_CONTRACTED_DIFFERENCE_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    def aux_down_grad_at(self, t: DateTime) -> str:
        return f"{self.AUX_DOWN_GRAD_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def aux_up_grad_at(self, t: DateTime) -> str:
        return f"{self.AUX_UP_GRAD_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def _initial_setup(self) -> None:
        self._compute_duration_params()
        self._build_time_frames()
        self._setup_bounds()
        self._setup_reserves()

    def _load_reserve_forecast(self, attribute, end: DateTime) -> Timeseries:
        default = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            end,
            0,
        )
        if attribute:
            return attribute.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                end,
            )
        return default

    def _compute_duration_params(self) -> None:
        timestep = self.parameters.temporal.timestep
        unit = self.thermal_unit

        if unit.minimum_time_on.total_hours() > 0:
            self.T_on = int(max(1, math.ceil(unit.minimum_time_on / timestep))) + 1
        else:
            self.T_on = 0

        if unit.minimum_time_off.total_hours() > 0:
            self.T_off = int(max(1, math.ceil(unit.minimum_time_off / timestep))) + 1
        else:
            self.T_off = 0

        self.T_start = int(math.floor(unit.startup_duration / timestep))
        self.T_stop = int(math.floor(unit.shutdown_duration / timestep))

        minimum_stable_power_duration = unit.minimum_stable_power_duration
        if minimum_stable_power_duration >= timestep:
            self.T_stable = int(math.ceil(minimum_stable_power_duration / timestep)) + 1
        else:
            self.T_stable = 0
        self.T_stable = self.T_stable if self.T_stable >= 2 else 0

    def _build_time_frames(self) -> None:
        temporal = self.parameters.temporal
        end_date = temporal.end_date + self.thermal_unit.additional_hours - temporal.timestep
        self.time_frame = generate_datetimes(temporal.start_date, end_date, temporal.timestep)

        T_traceback = int(max(self.T_on + self.T_start, self.T_off + self.T_stop)) + 1
        for k in range(1, T_traceback + 1):
            self.previous_time_frame.append(temporal.start_date - k * temporal.timestep)
        self.extended_start_date = self.previous_time_frame[-1]

        if self.thermal_unit.power:
            self.last_power = self.thermal_unit.power.get_forecast(
                temporal.execution_date,
                self.extended_start_date,
                temporal.start_date - temporal.timestep,
                default_value=0.0,
            )
        else:
            self.last_power = Timeseries.from_index(
                self.extended_start_date,
                temporal.timestep,
                temporal.start_date - temporal.timestep,
                0,
            )
        self.last_date = self.last_power.last_date()

    def _setup_bounds(self) -> None:
        self.q_lower = Timeseries.from_timeseries(self.thermal_unit.minimum_power)
        self.q_upper = Timeseries.from_timeseries(self.thermal_unit.maximum_power)
        self.delta_q = self.thermal_unit.maximum_gradient * self.parameters.temporal.timestep.total_minutes()
        self.delta_q_unconstrained = self.thermal_unit.maximum_power.max()

    def _setup_reserves(self) -> None:
        unit = self.thermal_unit
        end = unit.additional_hours + self.parameters.temporal.end_date

        fcr_up = self._load_reserve_forecast(unit.fcr_up_procured, end)
        fcr_down = self._load_reserve_forecast(unit.fcr_down_procured, end)
        afrr_up = self._load_reserve_forecast(unit.afrr_up_procured, end)
        afrr_down = self._load_reserve_forecast(unit.afrr_down_procured, end)
        mfrr_up = self._load_reserve_forecast(unit.mfrr_up_procured, end)
        mfrr_down = self._load_reserve_forecast(unit.mfrr_down_procured, end)
        rr_up = self._load_reserve_forecast(unit.rr_up_procured, end)
        rr_down = self._load_reserve_forecast(unit.rr_down_procured, end)

        maximum_afrr = unit.maximum_afrr if unit.maximum_afrr is not None else 0.0
        maximum_fcr = unit.maximum_fcr if unit.maximum_fcr is not None else 0.0
        self.maximum_automated = maximum_afrr + maximum_fcr

        self.reserves_up_procured = mfrr_up + rr_up
        self.reserves_down_procured = mfrr_down + rr_down

        afrr_up_f = afrr_up.filter(self.time_frame, inplace=False)
        afrr_down_f = afrr_down.filter(self.time_frame, inplace=False)
        fcr_up_f = fcr_up.filter(self.time_frame, inplace=False)
        fcr_down_f = fcr_down.filter(self.time_frame, inplace=False)

        self.feasible_automated_reserves_up_procured = afrr_up_f.clip(
            upper_bound=maximum_afrr, inplace=False
        ) + fcr_up_f.clip(upper_bound=maximum_fcr, inplace=False)
        self.feasible_automated_reserves_down_procured = afrr_down_f.clip(
            upper_bound=maximum_afrr, inplace=False
        ) + fcr_down_f.clip(upper_bound=maximum_fcr, inplace=False)

        self.automated_unsupplied_reserves += (
            (afrr_up_f - maximum_afrr).clip(lower_bound=0, inplace=False)
            + (fcr_up_f - maximum_fcr).clip(lower_bound=0, inplace=False)
            + (afrr_down_f - maximum_afrr).clip(lower_bound=0, inplace=False)
            + (fcr_down_f - maximum_fcr).clip(lower_bound=0, inplace=False)
        ).sum()

        cfg.logger.debug(f"automated unsupplied reserves : {self.automated_unsupplied_reserves}")

    def _define_time_frame_variables(self) -> None:
        """
        STEP 1 : Definition of the state, auxiliary and control variables over the time_frame.
        :return: none
        """

        # 1.1. Control variables :
        #    - the power output of the unit
        #    - the reserves of the unit and the mirror variables
        #    - contracted difference which corresponds to max(procured - provided, 0).
        for t in self.time_frame:
            q_upper_t = self.q_upper.get_value(t)
            # Control variables
            self.q.set_model_var(t)
            self.add_continuous_variable(self.reserves_up_equip_at(t), 0, q_upper_t)
            self.add_continuous_variable(self.reserves_down_equip_at(t), 0, q_upper_t)
            self.add_continuous_variable(self.unprovided_reserves_up_at(t), 0, q_upper_t)
            self.add_continuous_variable(self.unprovided_reserves_down_at(t), 0, q_upper_t)
            self.add_continuous_variable(self.relaxed_reserves_at(t), 0, self.q_lower.get_value(t))
            self.add_continuous_variable(self.automated_reserves_up_at(t), 0, self.maximum_automated)
            self.add_continuous_variable(self.automated_reserves_down_at(t), 0, self.maximum_automated)
            self.add_continuous_variable(self.contracted_difference_up_at(t), 0, q_upper_t)
            self.add_continuous_variable(self.contracted_difference_down_at(t), 0, q_upper_t)
            self.add_continuous_variable(self.automated_contracted_difference_up_at(t), 0, q_upper_t)
            self.add_continuous_variable(self.automated_contracted_difference_down_at(t), 0, q_upper_t)
            # State variables
            self.OFF.set_model_var(t)
            self.ON_UP.set_model_var(t)
            self.ON_DOWN.set_model_var(t)
            # Auxiliary variables
            self.turned_on.set_model_var(t)
            self.turned_off.set_model_var(t)
            # Conditional state variables
            if self.T_start >= 1:
                self.START.set_model_var(t)
            if self.T_stop >= 1:
                self.STOP.set_model_var(t)
            if self.T_stable >= 1:
                self.ON_FLAT.set_model_var(t)

        if self.T_start >= 1:
            self.start_time_steps = range(1, self.T_start - 1)
        if self.T_stop >= 1:
            self.stop_time_steps = range(1, self.T_stop - 1)
        if self.T_stable >= 1:
            self.start_date_minus_one = self.parameters.temporal.start_date - self.parameters.temporal.timestep
            self.ON_FLAT.set_model_var(self.start_date_minus_one)
            self.ON_DOWN.set_model_var(self.start_date_minus_one)
            self.ON_UP.set_model_var(self.start_date_minus_one)

        # 1.3.2. Create the condtionnal auxiliary variables if necessary.

        # Variable indicating that the unit is stable at t (sec. 6.1.3)
        # and variables to constrain the gradient U[t], D[t] and tilde_U[t], tilde_D[t] (defined in sec 6.2.4.)
        if self.T_stable >= 1:
            # Define the time_frame_union_minus_one which includes the start_date_minus_one time step.
            self.time_frame_union_minus_one = generate_datetimes(
                self.parameters.temporal.start_date - self.parameters.temporal.timestep,
                self.parameters.temporal.end_date
                + self.thermal_unit.additional_hours
                - self.parameters.temporal.timestep,
                self.parameters.temporal.timestep,
            )

            # Define dummy bounds for the gradient auxiliaries
            self.Q_max = self.delta_q_unconstrained
            self.Q_min = -self.Q_max

            for t in self.time_frame_union_minus_one:
                # Define the auxiliary variables of this state.
                self.stable.set_model_var(t)
                self.entered_up.set_model_var(t)
                self.entered_down.set_model_var(t)

            for t in self.time_frame:
                # Initialize the gradient auxiliaries.
                self.U.set_model_var(t)
                self.D.set_model_var(t)
                self.add_continuous_variable(
                    self.aux_up_grad_at(t),
                    self.Q_min,
                    self.Q_max,
                )
                self.add_continuous_variable(
                    self.aux_down_grad_at(t),
                    self.Q_min,
                    self.Q_max,
                )

    def create_objective_function(self, direction: Literal["maximize", "minimize"] = "maximize") -> None:
        """
        STEP 2 : Creation of objective function
        :param direction: the direction of the objective function
        :type direction: Literal["maximize", "minimize"]
        :return: None
        """
        # Set-up the objective function given by eq. (2) in the documentation.
        # If self.T_stable = 0, we don't need to include automatedContractedReservesUp and automatedContractedReservesDown to the objective function.
        # otherwise we need to include them.
        self.set_direction(direction)

        dt_h = self.parameters.temporal.timestep.total_hours()
        manual_pen = self.parameters.manual_unprocured_reserves_penalty * dt_h
        auto_pen = self.parameters.automated_unprocured_reserves_penalty * dt_h

        self.add_objective(
            objective_expr=(
                sum(
                    self.q.get_value(t)
                    * dt_h
                    * (self.prices.get_value(t) - self.thermal_unit.variable_cost.get_value(t))
                    - self.turned_on.get_value(t) * self.thermal_unit.startup_cost.get_value(t)
                    - manual_pen
                    * (
                        self.get_variable(self.contracted_difference_up_at(t))
                        + self.get_variable(self.contracted_difference_down_at(t))
                    )
                    - auto_pen
                    * (
                        self.get_variable(self.automated_contracted_difference_up_at(t))
                        + self.get_variable(self.automated_contracted_difference_down_at(t))
                    )
                    for t in self.time_frame
                )
                - auto_pen * self.automated_unsupplied_reserves
            ),
        )

    def _solution_ts(self, getter: Callable[[DateTime], float]) -> Timeseries:
        return Timeseries.from_values(
            start_date=self.parameters.temporal.start_date,
            frequency=self.parameters.temporal.timestep,
            values=[getter(t) for t in self.time_frame],
        )

    def _export_lp_if_requested(self) -> None:
        if self.parameters.solver.export_lp:
            output_path = self.parameters.get_output_dir() / "lp_export"
            output_path.mkdir(parents=True, exist_ok=True)
            lp_file_path = output_path / f"{self.thermal_unit.name}_price_{self.price_type}.lp"
            self.export_model(str(lp_file_path))

    def _extract_results(self) -> dict[str, Timeseries]:
        results: dict[str, Timeseries] = {}

        q_star = self._solution_ts(lambda t: self.q.get_model_var(t).solution_value())
        if abs(q_star.min() - 0.0) <= 1e-6 and abs(q_star.max() - 0.0) <= 1e-6:
            cfg.logger.debug(
                f"*** Info *** The optimal solution for the unit {self.thermal_unit.name} is such that "
                "the unit remains offline and delivers no power output."
            )

        results["q"] = q_star
        results["contracted_difference_up"] = self._solution_ts(
            lambda t: self.get_variable(self.contracted_difference_up_at(t)).solution_value()
        )
        results["contracted_difference_down"] = self._solution_ts(
            lambda t: self.get_variable(self.contracted_difference_down_at(t)).solution_value()
        )
        results["automated_contracted_difference_up"] = self._solution_ts(
            lambda t: self.get_variable(self.automated_contracted_difference_up_at(t)).solution_value()
        )
        results["automated_contracted_difference_down"] = self._solution_ts(
            lambda t: self.get_variable(self.automated_contracted_difference_down_at(t)).solution_value()
        )
        results["ON_UP"] = self._solution_ts(lambda t: self.ON_UP.get_model_var(t).solution_value())
        results["ON_DOWN"] = self._solution_ts(lambda t: self.ON_DOWN.get_model_var(t).solution_value())
        results["OFF"] = self._solution_ts(lambda t: self.OFF.get_model_var(t).solution_value())

        if self.T_start >= 1:
            results["START"] = self._solution_ts(lambda t: self.START.get_model_var(t).solution_value())
        if self.T_stop >= 1:
            results["STOP"] = self._solution_ts(lambda t: self.STOP.get_model_var(t).solution_value())
        if self.T_stable >= 1:
            results["ON_FLAT"] = self._solution_ts(lambda t: self.ON_FLAT.get_model_var(t).solution_value())

        return results

    def solve_thermal_optimization(self) -> dict[str, Timeseries]:
        self._export_lp_if_requested()

        cfg.logger.info(f"Optimisation model '{self.name}' with price type '{self.price_type}'")
        self.solve()

        status = self.solution_info.status if self.solution_info else None
        cfg.logger.debug(f"Solver status: {status}")
        cfg.logger.debug(f"Objective function value: {self._objective}")

        return self._extract_results()

    def add_daily_energy_constraint(self) -> None:
        """
        Add daily energy constraint to the optimization model.
        This constraint limits the total energy output per day.
        Should be called once after all combination constraints are added.

        :return: None
        """
        if self.thermal_unit.has_daily_energy_constraint and self.thermal_unit.maximum_daily_energy is not None:
            dt_days = self.parameters.temporal.timestep.total_days()

            steps_by_day: dict[datetime, list] = {}
            for t in self.time_frame:
                key = datetime(t.year, t.month, t.day)
                steps_by_day.setdefault(key, []).append(t)

            for date, matching_steps in steps_by_day.items():
                constraint_expr = sum(
                    self.q.get_value(t) for t in matching_steps
                ) <= self.thermal_unit.maximum_daily_energy.get_value(date) * dt_days * len(matching_steps)
                self.add_constraint(constraint_expr, f"energy_limit_of_{self.thermal_unit.name}_at_{date}")

    def is_day_zero(self) -> bool:
        """
        See if the program needs to be initialized as DayZero or not
        :return: if the program needs to be initialized as DayZero or not
        :rtype: bool
        """
        if len(self.last_power) == 0:
            # Initialization of the program as DayZero and warn the user
            cfg.logger.info("The program is initialized for the first time.")
            day_zero = True  # Boolean to keep track of the status
        elif self.last_date != self.parameters.temporal.start_date - self.parameters.temporal.timestep:
            # last_date doesn't match start_date - time_step (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
            cfg.logger.warning(
                f"The last_date found in Power of equipement {self.thermal_unit.name} "
                "does not match the start_date of the current program. \n "
                "The program will be initialized as DayZero."
            )
            day_zero = True
        else:
            day_zero = False
            # Setting up the initial conditions of the program
        return day_zero
