"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any, cast

from pendulum import DateTime, Duration

from atlas.models.equipment.equipment import Equipment
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.models.control_block import ControlBlockPO
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.market_area import MarketAreaPO
from atlas.modules.portfolio_optimisation.models.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.get_fragment_price import _get_fragment_data
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_power, get_reserve, get_upstream_energy
from atlas.modules.portfolio_optimisation.utils.imbalance_price import estimate_imbalance_prices
from atlas.solver.solver_interface import OptimisationModel


class PortfolioPO(Portfolio):
    market_area: MarketAreaPO
    control_block: ControlBlockPO
    equipments: dict[str, list[Equipment]]

    def add_variables(
        self,
        model: OptimisationModel,
        times: list[DateTime],
        parameters: PortfolioOptimisationParameters,
    ):
        """Build portfolio-level optimization variables."""

        for time in times:
            residual_energy = self._compute_residual_energy(time, parameters)
            maximum_power, maximum_energy = self._compute_power_and_energy(time, parameters)

            self._add_imbalance_variables(model, time, residual_energy, maximum_energy, parameters)
            self._add_contract_difference_variables(model, time, maximum_power)

    def add_constraints(self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        if time in parameters.target_times:
            self._add_global_constraints(time, model, parameters)
            if any(self.equipments.get(tech, []) for tech in ["thermal", "hydro", "storage", "wind", "solar"]):
                self._add_reserves_constraints(time, model, parameters)

    def _add_reserves_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        sum_reserves_up_var = sum(
            model.get_variable(f"reserves_up_{obj.name}_{time}") for t in self.equipments for obj in self.equipments[t]
        )
        sum_reserves_down_var = sum(
            model.get_variable(f"reserves_down_{obj.name}_{time}")
            for t in self.equipments
            for obj in self.equipments[t]
        )
        sum_automated_reserves_up_var = sum(
            model.get_variable(f"automated_reserves_up_{obj.name}_{time}")
            for t in self.equipments
            for obj in self.equipments[t]
        )
        sum_automated_reserves_down_var = sum(
            model.get_variable(f"automated_reserves_down_{obj.name}_{time}")
            for t in self.equipments
            for obj in self.equipments[t]
        )

        (
            reserves_up,
            reserves_down,
            automated_reserves_up,
            automated_reserves_down,
            maximum_power,
            maximum_energy,
        ) = self._compute_reserves_and_power_for_time(time, parameters)

        model.add_constraint(
            model.get_variable(f"contracted_diff_up_{self.name}_{time}") >= reserves_up - sum_reserves_up_var
        )

        model.add_constraint(
            model.get_variable(f"contracted_diff_down_{self.name}_{time}") >= reserves_down - sum_reserves_down_var
        )

        model.add_constraint(
            model.get_variable(f"auto_contracted_diff_up_{self.name}_{time}")
            >= automated_reserves_up - sum_automated_reserves_up_var
        )

        model.add_constraint(
            model.get_variable(f"auto_contracted_diff_down_{self.name}_{time}")
            >= automated_reserves_down - sum_automated_reserves_down_var
        )

    def _add_global_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Add global portfolio constraints."""
        # Power balance constraint
        residual_energy = self._compute_residual_energy(time, parameters)
        max_overall_imbal = max(residual_energy * parameters.maximum_imbalance)
        sum_power_variables = self._get_sum_power_level_variables(model, time, parameters)

        power_balance_constraint = (
            model.get_variable(f"{self.name}_small_imbalance_up_{time}")
            + model.get_variable(f"{self.name}_large_imbalance_up_{time}")
            - model.get_variable(f"{self.name}_small_imbalance_down_{time}")
            - model.get_variable(f"{self.name}_large_imbalance_down_{time}")
            == residual_energy - sum_power_variables
        )
        model.add_constraint(power_balance_constraint, name=f"power_balance_{time}")

        # Imbalance limits
        up_imbalance_limit = (
            model.get_variable(f"{self.name}_small_imbalance_up_{time}")
            + model.get_variable(f"{self.name}_large_imbalance_up_{time}")
            <= max_overall_imbal
        )
        model.add_constraint(up_imbalance_limit, name=f"up_imbalance_limit_{time}")

        down_imbalance_limit = (
            model.get_variable(f"{self.name}_small_imbalance_down_{time}")
            + model.get_variable(f"{self.name}_large_imbalance_down_{time}")
            <= max_overall_imbal
        )
        model.add_constraint(down_imbalance_limit, name=f"down_imbalance_limit_{time}")

    def add_objective(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        for time in parameters.target_times:
            self._add_imbalance_cost_terms(
                model,
                time,
                *estimate_imbalance_prices(time, self.market_area, self.control_block, parameters),
                parameters.timestep,
            )

            self._add_reserve_penalty_terms(model, time, parameters)

    def _add_imbalance_cost_terms(
        self,
        model: OptimisationModel,
        time: DateTime,
        imbalance_price_down: float,
        imbalance_price_up: float,
        large_imbalance_price_down: float,
        large_imbalance_price_up: float,
        timestep: Duration,
    ):
        """Get imbalance cost terms as OR-Tools expressions."""

        small_imbalance_up_var = model.get_variable(f"{self.name}_small_imbalance_up_{time}")
        small_imbalance_down_var = model.get_variable(f"{self.name}_small_imbalance_down_{time}")
        large_imbalance_up_var = model.get_variable(f"{self.name}_large_imbalance_up_{time}")
        large_imbalance_down_var = model.get_variable(f"{self.name}_large_imbalance_down_{time}")

        # Small imbalance costs
        if imbalance_price_up:
            model.add_objective(imbalance_price_up * small_imbalance_up_var * timestep)

        if imbalance_price_down:
            model.add_objective(-imbalance_price_down * small_imbalance_down_var * timestep)

        # Large imbalance costs
        if large_imbalance_price_up:
            model.add_objective(large_imbalance_price_up * large_imbalance_up_var * timestep)

        if large_imbalance_price_down:
            model.add_objective(-large_imbalance_price_down * large_imbalance_down_var * timestep)

    def _add_reserve_penalty_terms(
        self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters
    ):
        """Get reserve penalty terms as OR-Tools expressions."""

        contracted_diff_up = model.get_variable(f"contracted_diff_up_{self.name}_{time}")
        contracted_diff_down = model.get_variable(f"contracted_diff_down_{self.name}_{time}")
        auto_contracted_diff_up = model.get_variable(f"auto_contracted_diff_up_{self.name}_{time}")
        auto_contracted_diff_down = model.get_variable(f"auto_contracted_diff_down_{self.name}_{time}")

        # Manual reserve penalties
        model.add_objective(parameters.manual_unprocured_reserves_penalty * parameters.timestep * contracted_diff_up)
        model.add_objective(parameters.manual_unprocured_reserves_penalty * parameters.timestep * contracted_diff_down)

        # Automated reserve penalties
        model.add_objective(
            parameters.automated_unprocured_reserves_penalty * parameters.timestep * auto_contracted_diff_up
        )
        model.add_objective(
            parameters.automated_unprocured_reserves_penalty * parameters.timestep * auto_contracted_diff_down
        )

    def _add_imbalance_variables(
        self,
        model: OptimisationModel,
        time: DateTime,
        residual_energy: float,
        maximum_energy: float,
        parameters: PortfolioOptimisationParameters,
    ):
        """Add imbalance variables to the optimization model."""
        small_imbalance_limit = maximum_energy * parameters.small_imbalance_size
        max_overall_imbal = max(residual_energy * parameters.maximum_imbalance)

        model.add_continuous_variable(
            name=f"{self.name}_small_imbalance_up_{time}",
            lower_bound=0,
            upper_bound=small_imbalance_limit,
        )
        model.add_continuous_variable(
            name=f"{self.name}_small_imbalance_down_{time}",
            lower_bound=0,
            upper_bound=small_imbalance_limit,
        )
        model.add_continuous_variable(
            name=f"{self.name}_large_imbalance_up_{time}",
            lower_bound=0,
            upper_bound=max_overall_imbal,
        )
        model.add_continuous_variable(
            name=f"{self.name}_large_imbalance_down_{time}",
            lower_bound=0,
            upper_bound=max_overall_imbal,
        )

    def _add_contract_difference_variables(
        self,
        model: OptimisationModel,
        time: DateTime,
        maximum_power: float,
    ):
        """Add contract difference variables to the optimization model."""
        contract_vars = [
            "contracted_diff_up",
            "contracted_diff_down",
            "auto_contracted_diff_up",
            "auto_contracted_diff_down",
        ]

        for var_type in contract_vars:
            model.add_continuous_variable(
                name=f"{var_type}_{self.name}_{time}",
                lower_bound=0,
                upper_bound=maximum_power,
            )

    def _get_sum_power_level_variables(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> float:
        """Get the sum of all power level variables for a specific time."""
        total_power = 0

        # Hydro equipment - uses hydraulic_op_times and fragment variables
        if "hydro" in self.equipments and time in parameters.hydraulic_op_times:
            for obj in cast(list[HydroPO], self.equipments["hydro"]):
                fragment_data = _get_fragment_data(obj)
                for category in fragment_data.keys():
                    var = model.get_variable(f"{obj.name}_power_level_frag_{category}_at_{time}")
                    if var is not None:
                        total_power += var

        # Solar and Wind equipment - uses target_times
        if time in parameters.target_times:
            for equipment_type in ["solar", "wind"]:
                if equipment_type in self.equipments:
                    for obj in self.equipments[equipment_type]:
                        var = model.get_variable(f"{obj.name}_power_level_{time}")
                        if var is not None:
                            total_power += var

            # Load equipment - uses target_times
            if "load" in self.equipments:
                for obj in self.equipments["load"]:
                    var = model.get_variable(f"{obj.name}_power_level_{time}")
                    if var is not None:
                        total_power += var

        # Thermal equipment - uses thermal_op_times
        if "thermal" in self.equipments and time in parameters.thermal_op_times:
            for obj in self.equipments["thermal"]:
                var = model.get_variable(f"{obj.name}_power_level_{time}")
                if var is not None:
                    total_power += var

        if "storage" in self.equipments:
            for obj in cast(list[StoragePO], self.equipments["storage"]):
                optimisation_times = parameters.storage_mapping[obj.storage_type].get("optimisation_times", [])
                if time in optimisation_times:
                    # Storage has both sell and buy power levels
                    sell_var = model.get_variable(f"{obj.name}_power_level_sell_{time}")
                    buy_var = model.get_variable(f"{obj.name}_power_level_buy_{time}")

                    if sell_var is not None:
                        total_power += sell_var
                    if buy_var is not None:
                        total_power += buy_var

        return total_power

    def _compute_residual_energy(self, time: DateTime, parameters: PortfolioOptimisationParameters) -> float:
        """Compute residual energy metrics for all times."""

        return (
            self._compute_non_dispatchable_production_residual_energy(time, parameters)
            + self._compute_non_dispatchable_load_residual_energy(time, parameters)
            + self._compute_dispatchable_residual_energy(time, parameters)
        )

    def _compute_power_and_energy(
        self,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> tuple[float, float]:
        """Compute maximum power and energy metrics for all times."""
        sum_maximum_power: float = 0
        sum_max_energy: float = 0
        equipment_types = ["dispatchable_load", "wind", "solar", "thermal", "hydro", "storage"]

        for equipment_type in equipment_types:
            for obj in self.equipments.get(equipment_type, []):
                power = get_maximum_power(obj, time, parameters.execution_date)
                sum_maximum_power += power
                sum_max_energy += abs(power)

        return sum_maximum_power, sum_max_energy

    def _compute_dispatchable_residual_energy(
        self, time: DateTime, parameters: PortfolioOptimisationParameters
    ) -> float:
        """Compute residual energy for dispatchable equipment."""
        residual_energy = 0
        equipment_types = ["dispatchable_load", "wind", "solar", "thermal", "hydro", "storage"]

        for equipment_type in equipment_types:
            for obj in self.equipments.get(equipment_type, []):
                upstream_energy = get_upstream_energy(obj, time, parameters)
                residual_energy += upstream_energy

        return residual_energy

    def _compute_non_dispatchable_production_residual_energy(
        self,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> float:
        """Compute non-dispatchable production equipment residual energy"""
        residual_energy = 0

        for obj in cast(list[OtherNonDispatchablePO], self.equipments.get("non_dispatchable_production", [])):
            last_forecast_ti = obj.maximum_power_forecast.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ).get_value(time)

            upstream_sold_energy = get_upstream_energy(obj, time, parameters)
            optimal_dispatch = min(last_forecast_ti, upstream_sold_energy)
            residual_energy += upstream_sold_energy - optimal_dispatch

        return residual_energy

    def _compute_non_dispatchable_load_residual_energy(
        self,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> float:
        """Compute non-dispatchable load equipment residual energy"""
        residual_energy = 0

        for obj in cast(list[LoadPO], self.equipments.get("non_dispatchable_load", [])):
            last_forecast_ti = obj.maximum_power_forecast.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ).get_value(time)

            upstream_bought_energy = get_upstream_energy(obj, time, parameters)
            optimal_dispatch = min(last_forecast_ti, upstream_bought_energy)
            residual_energy += upstream_bought_energy - optimal_dispatch

        return residual_energy

    def _get_power_level_variables(
        self, time: DateTime, model: OptimisationModel, portfolio: dict[str, list[type[Equipment]]]
    ) -> list[Any]:
        power_level_variables: list[Any] = []

        for obj in portfolio["load"] + portfolio["wind"] + portfolio["solar"]:
            power_level_variables.append(model.get_variable(f"{obj.name}_power_level_{time}"))

        return power_level_variables

    def _compute_reserves_and_power_for_time(
        self, time: DateTime, parameters: PortfolioOptimisationParameters
    ) -> tuple[float, float, float, float, float, float]:
        """Compute reserves and power metrics for a specific time."""
        sum_reserves_up: float = 0
        sum_reserves_down: float = 0
        sum_automated_reserves_up: float = 0
        sum_automated_reserves_down: float = 0
        sum_maximum_power: float = 0
        sum_maximum_energy: float = 0

        equipment_types = ["dispatchable_load", "wind", "solar", "thermal", "hydro", "storage"]

        for equipment_type in equipment_types:
            for obj in self.equipments.get(equipment_type, []):
                sum_maximum_power += get_maximum_power(obj, time, parameters.execution_date)
                sum_maximum_energy += abs(get_maximum_power(obj, time, parameters.execution_date))

                (
                    sum_reserves_up,
                    sum_reserves_down,
                    sum_automated_reserves_up,
                    sum_automated_reserves_down,
                    sum_maximum_power,
                ) = get_reserve(
                    obj,
                    sum_reserves_up,
                    sum_reserves_down,
                    sum_automated_reserves_up,
                    sum_automated_reserves_down,
                    sum_maximum_power,
                    time,
                    parameters,
                )

        return (
            sum_reserves_up,
            sum_reserves_down,
            sum_automated_reserves_up,
            sum_automated_reserves_down,
            sum_maximum_power,
            sum_maximum_energy,
        )
