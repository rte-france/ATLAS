"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from loguru import logger
from pendulum import Duration

from atlas import BusinessModel
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.output_dataset import PortfolioOptimisationOutputDataset
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.portfolio_orchestrator import PortfolioOptimisationOrchestrator
from atlas.timing import infer_frequency


class PortfolioOptimisationModule(
    AbstractModule[
        PortfolioOptimisationParameters,
        PortfolioOptimisationInputDataset,
        PortfolioOptimisationOutputDataset,
    ]
):
    def get_parameters_class(self):
        """Returns the concrete Parameters class for this module."""
        return PortfolioOptimisationParameters

    def import_data(
        self,
        raw_data: dict[str, list[BusinessModel]],
        parameters: PortfolioOptimisationParameters,
    ) -> PortfolioOptimisationInputDataset:
        """Imports data using business objects and parameters."""
        logger.info("Building Portfolio Optimisation input dataset ..")
        return PortfolioOptimisationInputDataset(raw_data, parameters)

    def validate_data(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
    ) -> bool:
        """Validates imported or generated data."""
        logger.debug("Validating timeseries timestep consistency for portfolio optimization")

        try:
            self._validate_timeseries_timestep_consistency(parameters, input_dataset)
            logger.debug("Timestep validation passed successfully")
            return True
        except ValueError as e:
            logger.error(f"Timestep validation failed: {e}")
            return False

    def validates_results(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
        output_dataset: PortfolioOptimisationOutputDataset,
    ) -> bool:
        """Validates results"""
        return True

    def export_results(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
        output_dataset: PortfolioOptimisationOutputDataset,
    ) -> None:
        """Exports results."""
        logger.debug("Exporting Portfolio Optimisation results ..")

    def execute(
        self,
        parameters: PortfolioOptimisationParameters,
        dataset: PortfolioOptimisationInputDataset,
    ) -> PortfolioOptimisationOutputDataset:
        """Executes the module's main logic."""
        model = PortfolioOptimisationOrchestrator(parameters)
        optimisation_results = model.run(dataset)
        output_dataset = PortfolioOptimisationOutputDataset(
            parameters=parameters, optimisation_results=optimisation_results, input_dataset=dataset
        )
        output_dataset.build()

        return output_dataset

    def _validate_timeseries_timestep_consistency(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
    ) -> None:
        """Validate that all timeseries data have timesteps consistent with the optimization parameters."""
        expected_timestep = parameters.timestep
        logger.debug(f"Expected timestep: {expected_timestep}")

        validation_errors = []

        for equipment_type, equipment_list in input_dataset.equipments.iter_by_type():
            for equipment in equipment_list:
                equipment_errors = self._validate_equipment_timeseries(equipment, expected_timestep, equipment_type)
                validation_errors.extend(equipment_errors)

        for portfolio in input_dataset.portfolios + input_dataset.portfolios_manual_activation:
            portfolio_errors = self._validate_portfolio_timeseries(portfolio, expected_timestep)
            validation_errors.extend(portfolio_errors)

        if validation_errors:
            error_message = "Timestep validation failed:\n" + "\n".join(validation_errors)
            raise ValueError(error_message)

    def _validate_equipment_timeseries(self, equipment, expected_timestep: Duration, equipment_type: str) -> list[str]:
        """Validate timeseries timestep consistency for a single equipment using dynamic attribute discovery."""
        errors = []
        equipment_name = getattr(equipment, "name", f"unknown_{equipment_type}")

        # Dynamically discover all attributes that are timeseries types
        for attr_name in dir(equipment):
            if attr_name.startswith("_"):  # Skip private attributes
                continue

            attr_value = getattr(equipment, attr_name, None)
            if attr_value is not None and self._is_timeseries_type(attr_value):
                validation_result = self._validate_and_fix_timeseries(
                    attr_value, expected_timestep, f"{equipment_name}.{attr_name}"
                )
                if validation_result["error"]:
                    errors.append(validation_result["error"])
                elif validation_result["fixed"]:
                    # Update the equipment attribute with the corrected timeseries
                    setattr(equipment, attr_name, validation_result["timeseries"])
                    logger.debug(f"Auto-corrected timestep for {equipment_name}.{attr_name}")

        return errors

    def _validate_portfolio_timeseries(self, portfolio, expected_timestep: Duration) -> list[str]:
        """Validate timeseries timestep consistency for a portfolio using dynamic attribute discovery."""
        errors = []
        portfolio_name = getattr(portfolio, "name", "unknown_portfolio")

        # Check portfolio direct attributes
        for attr_name in dir(portfolio):
            if attr_name.startswith("_"):
                continue

            attr_value = getattr(portfolio, attr_name, None)
            if attr_value is not None and self._is_timeseries_type(attr_value):
                validation_result = self._validate_and_fix_timeseries(
                    attr_value, expected_timestep, f"{portfolio_name}.{attr_name}"
                )
                if validation_result["error"]:
                    errors.append(validation_result["error"])
                elif validation_result["fixed"]:
                    setattr(portfolio, attr_name, validation_result["timeseries"])
                    logger.debug(f"Auto-corrected timestep for {portfolio_name}.{attr_name}")

        # Check market area attributes
        if hasattr(portfolio, "market_area") and portfolio.market_area:
            market_area = portfolio.market_area
            for attr_name in dir(market_area):
                if attr_name.startswith("_"):
                    continue

                attr_value = getattr(market_area, attr_name, None)
                if attr_value is not None and self._is_timeseries_type(attr_value):
                    validation_result = self._validate_and_fix_timeseries(
                        attr_value, expected_timestep, f"{portfolio_name}.market_area.{attr_name}"
                    )
                    if validation_result["error"]:
                        errors.append(validation_result["error"])
                    elif validation_result["fixed"]:
                        setattr(market_area, attr_name, validation_result["timeseries"])
                        logger.debug(f"Auto-corrected timestep for {portfolio_name}.market_area.{attr_name}")

        return errors

    def _is_timeseries_type(self, obj) -> bool:
        """Check if an object is a timeseries-like type that can have frequency adjusted."""
        return isinstance(
            obj,
            Timeseries | LazyTimeseries | ScenarioMatrix | LazyScenarioMatrix,
        )

    def _validate_and_fix_timeseries(self, timeseries_obj, expected_timestep: Duration, context: str) -> dict:
        """
        Validate and potentially fix a timeseries object's timestep.
        Returns dict with keys: 'error', 'fixed', 'timeseries'
        """
        result = {"error": None, "fixed": False, "timeseries": timeseries_obj}

        try:
            actual_timestep = self._get_timeseries_timestep(timeseries_obj)
            if actual_timestep is None:
                return result  # Skip validation for empty/small timeseries

            if actual_timestep != expected_timestep:
                logger.debug(
                    f"{context}: Timestep mismatch - expected {expected_timestep}, found {actual_timestep}. Attempting to fix..."
                )

                # Try to fix the timestep using set_frequency
                try:
                    if hasattr(timeseries_obj, "set_frequency"):
                        fixed_ts = timeseries_obj.set_frequency(expected_timestep, inplace=False)
                        result["timeseries"] = fixed_ts
                        result["fixed"] = True
                        logger.debug(f"{context}: Successfully adjusted timestep to {expected_timestep}")
                    else:
                        result["error"] = f"{context}: Cannot adjust timestep - object lacks set_frequency method"
                except Exception as e:
                    result["error"] = f"{context}: Failed to adjust timestep - {str(e)}"

        except ValueError as e:
            result["error"] = f"{context}: Could not validate timestep - {str(e)}"

        return result

    def _get_timeseries_timestep(self, timeseries_obj) -> Duration | None:
        """Extract the timestep from a timeseries object."""
        if isinstance(timeseries_obj, LazyTimeseries):
            collected_ts = timeseries_obj.collect()
            if len(collected_ts.dataframe) < 2:
                return None
            return infer_frequency(collected_ts.dataframe)
        elif isinstance(timeseries_obj, Timeseries):
            if len(timeseries_obj.dataframe) < 2:
                return None
            return infer_frequency(timeseries_obj.dataframe)
        elif isinstance(timeseries_obj, ScenarioMatrix | LazyScenarioMatrix):
            # For ScenarioMatrix and LazyScenarioMatrix, get frequency from matrix
            if isinstance(timeseries_obj, LazyScenarioMatrix):
                matrix_df = timeseries_obj.matrix.collect()
            else:
                matrix_df = timeseries_obj.matrix
            if len(matrix_df) < 2:
                return None
            return infer_frequency(matrix_df)
        elif hasattr(timeseries_obj, "timeseries") and hasattr(timeseries_obj.timeseries, "dataframe"):
            # For matrix types that might have a timeseries attribute
            if len(timeseries_obj.timeseries.dataframe) < 2:
                return None
            return infer_frequency(timeseries_obj.timeseries.dataframe)
        else:
            # For other matrix types, try to get frequency information if available
            try:
                if hasattr(timeseries_obj, "frequency"):
                    return timeseries_obj.frequency
                elif hasattr(timeseries_obj, "timestep"):
                    return timeseries_obj.timestep
            except Exception:
                pass

        return None
