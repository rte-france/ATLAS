from typing import cast

from pendulum import DateTime

from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.models.solar import SolarPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class ConstraintBuilder:
    """Builds optimization constraints."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def build_constraints(
        self,
        portfolio: PortfolioPO,
        max_optimisation_times: list[DateTime],
        optimisation_times: dict[str, list[DateTime]],
        model: OptimisationModel,
    ) -> None:
        """Build all constraints for the optimization problem."""

        for time in max_optimisation_times:
            self._build_time_constraints(time, portfolio, portfolio.name, model, optimisation_times)

    def _build_time_constraints(
        self,
        time: DateTime,
        portfolio: PortfolioPO,
        model: OptimisationModel,
        optimisation_times: dict[str, list[DateTime]],
    ):
        """Build constraints for a specific time period."""
        portfolio.add_constraints(time, model, self.parameters)
        self._add_equipment_constraints(
            time,
            portfolio,
            model,
            optimisation_times,
        )

    def _add_equipment_constraints(
        self,
        time: DateTime,
        portfolio: PortfolioPO,
        model: OptimisationModel,
        optimisation_times: dict[str, list[DateTime]],
    ):
        """Add constraints for different equipment types."""

        # Wind and PV constraints
        if time in optimisation_times.get("op_times", []):
            for obj in cast(
                list[WindPO | SolarPO], portfolio.equipments.get("wind", []) + portfolio.equipments.get("solar", [])
            ):
                obj.add_constraints(time, model, self.parameters)

        # Thermal constraints
        # if time in optimisation_times.get("thermal_op_times", []):
        #     for thermal in cast(list[ThermalPO],  portfolio.equipments.get("thermal", [])):
        #         thermal.add_constraints(time, model, self.parameters)

        # Hydraulic constraints
        if time in optimisation_times.get("hydraulic_op_times", []):
            for hydro in cast(list[HydroPO], portfolio.equipments.get("hydro", [])):
                hydro.add_constraints(time, model, self.parameters)

        # Storage constraints
        storage_times = ["battery_op_times", "phs_op_times", "ev_op_times"]
        if any(time in optimisation_times.get(st, []) for st in storage_times):
            for storage in cast(list[StoragePO], portfolio.equipments.get("storage", [])):
                storage.add_contraints(time, model, self.parameters)

        # Load constraints
        if time in optimisation_times.get("op_times", []):
            for load in cast(list[LoadPO], portfolio.equipments.get("load", [])):
                load.add_constraints(time, model)
