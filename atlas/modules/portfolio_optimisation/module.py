"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Iterable

from loguru import logger
from pendulum import Duration

from atlas.abstract_class.abstract_module import AbstractModule
from atlas.enums import BusinessModelName
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_matrix import LazyScenarioMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
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
        """
        Returns the concrete Parameters class for this module.

        :return: The PortfolioOptimisationParameters class
        :rtype: type[PortfolioOptimisationParameters]
        """
        return PortfolioOptimisationParameters

    def import_data(
        self,
        raw_data: AtlasDataset,
        parameters: PortfolioOptimisationParameters,
    ) -> PortfolioOptimisationInputDataset:
        """
        Imports data using business objects and parameters.

        :param raw_data: Dictionary of business model objects
        :type raw_data: dict[str, list[BusinessModel]]
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Input dataset for portfolio optimization
        :rtype: PortfolioOptimisationInputDataset
        """
        return PortfolioOptimisationInputDataset(raw_data, parameters)

    def validate_data(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
    ) -> bool:
        """
        Validates imported or generated data.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :param input_dataset: Input dataset to validate
        :type input_dataset: PortfolioOptimisationInputDataset
        :return: True if validation passes, False otherwise
        :rtype: bool
        """
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
        """
        Validates results.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :param input_dataset: Input dataset
        :type input_dataset: PortfolioOptimisationInputDataset
        :param output_dataset: Output dataset to validate
        :type output_dataset: PortfolioOptimisationOutputDataset
        :return: True if validation passes
        :rtype: bool
        """
        return True

    def export_results(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
        output_dataset: PortfolioOptimisationOutputDataset,
    ) -> None:
        """
        Exports results.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :param input_dataset: Input dataset
        :type input_dataset: PortfolioOptimisationInputDataset
        :param output_dataset: Output dataset to export
        :type output_dataset: PortfolioOptimisationOutputDataset
        """
        logger.debug("Exporting Portfolio Optimisation results ..")

    def execute(
        self,
        parameters: PortfolioOptimisationParameters,
        dataset: PortfolioOptimisationInputDataset,
    ) -> PortfolioOptimisationOutputDataset:
        """
        Executes the module's main logic.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :param dataset: Input dataset
        :type dataset: PortfolioOptimisationInputDataset
        :return: Output dataset containing optimization results
        :rtype: PortfolioOptimisationOutputDataset
        """
        model = PortfolioOptimisationOrchestrator(parameters)
        optimisation_results = model.run(dataset)
        output_dataset = PortfolioOptimisationOutputDataset(
            parameters=parameters, optimisation_results=optimisation_results, input_dataset=dataset
        )

        return output_dataset

    def _validate_timeseries_timestep_consistency(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
    ) -> None:
        """
        Validate that all timeseries data have timesteps consistent with the optimization parameters.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :param input_dataset: Input dataset to validate
        :type input_dataset: PortfolioOptimisationInputDataset
        :raises ValueError: If timestep validation fails
        """
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
        """
        Validate timeseries timestep consistency for a single equipment using dynamic attribute discovery.

        :param equipment: Equipment object to validate
        :type equipment: Any
        :param expected_timestep: Expected timestep duration
        :type expected_timestep: Duration
        :param equipment_type: Type of equipment
        :type equipment_type: str
        :return: List of validation error messages
        :rtype: list[str]
        """
        errors = []
        equipment_name = getattr(equipment, "name", f"unknown_{equipment_type}")

        # Dynamically discover all attributes that are timeseries types
        for attr_name in dir(equipment):
            if attr_name.startswith("_"):  # Skip private attributes
                continue

            attr_value = getattr(equipment, attr_name, None)
            if attr_value is not None and self._is_timeseries_type(attr_value):
                validation_result = self._validate_and_fix_timeseries(
                    attr_value, expected_timestep, context=f"{equipment_name}.{attr_name}"
                )
                if validation_result["error"]:
                    errors.append(validation_result["error"])
                elif validation_result["fixed"]:
                    # Update the equipment attribute with the corrected timeseries
                    setattr(equipment, attr_name, validation_result["timeseries"])
                    logger.debug(f"Auto-corrected timestep for {equipment_name}.{attr_name}")

        return errors

    def _validate_portfolio_timeseries(self, portfolio, expected_timestep: Duration) -> list[str]:
        """
        Validate timeseries timestep consistency for a portfolio using dynamic attribute discovery.

        :param portfolio: Portfolio object to validate
        :type portfolio: Any
        :param expected_timestep: Expected timestep duration
        :type expected_timestep: Duration
        :return: List of validation error messages
        :rtype: list[str]
        """
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
        """
        Check if an object is a timeseries-like type that can have frequency adjusted.

        :param obj: Object to check
        :type obj: Any
        :return: True if object is a timeseries type
        :rtype: bool
        """
        return isinstance(
            obj,
            AbstractTimeseries | AbstractScenarioMatrix | ForecastingMatrix | LazyForecastingMatrix,
        )

    def _validate_and_fix_timeseries(
        self,
        timeseries_obj: AbstractTimeseries | AbstractScenarioMatrix | ForecastingMatrix | LazyForecastingMatrix,
        expected_timestep: Duration,
        context: str,
    ) -> dict:
        """
        Validate and potentially fix a timeseries object's timestep.

        :param timeseries_obj: Timeseries object to validate and fix
        :type timeseries_obj: Any
        :param expected_timestep: Expected timestep duration
        :type expected_timestep: Duration
        :param context: Context string for error messages
        :type context: str
        :return: Dictionary with keys 'error', 'fixed', 'timeseries'
        :rtype: dict
        """
        result = {"error": None, "fixed": False, "timeseries": timeseries_obj}

        actual_timestep = self._get_timeseries_timestep(timeseries_obj)
        if actual_timestep is None:
            return result  # Skip validation for empty/small timeseries

        if actual_timestep != expected_timestep:
            logger.debug(
                f"{context}: Timestep mismatch - expected {expected_timestep}, found {actual_timestep}. Attempting to fix..."
            )

            fixed_ts = timeseries_obj.set_frequency(expected_timestep, inplace=False)
            result["timeseries"] = fixed_ts
            result["fixed"] = True
            logger.debug(f"{context}: Successfully adjusted timestep to {expected_timestep}")

        return result

    def _get_timeseries_timestep(
        self, timeseries_obj: AbstractTimeseries | AbstractScenarioMatrix | ForecastingMatrix | LazyForecastingMatrix
    ) -> Duration | None:
        """
        Extract the timestep from a timeseries object.

        :param timeseries_obj: Timeseries object
        :type timeseries_obj: Any
        :return: Timestep duration or None if cannot be determined
        :rtype: Duration | None
        """
        if isinstance(timeseries_obj, LazyTimeseries):
            collected_ts = timeseries_obj.collect()
            if len(collected_ts.dataframe) < 2:
                return None
            return infer_frequency(collected_ts.dataframe)
        elif isinstance(timeseries_obj, Timeseries):
            if len(timeseries_obj.dataframe) < 2:
                return None
            return infer_frequency(timeseries_obj.dataframe)
        elif isinstance(timeseries_obj, AbstractScenarioMatrix | LazyForecastingMatrix | ForecastingMatrix):
            # For ScenarioMatrix and LazyScenarioMatrix, get frequency from matrix
            if isinstance(timeseries_obj, LazyScenarioMatrix | LazyForecastingMatrix):
                matrix_df = timeseries_obj.dataframe.collect()
            else:
                matrix_df = timeseries_obj.dataframe  # type: ignore [assignment]
            if len(matrix_df) < 2:
                return None
            return infer_frequency(matrix_df)

        return None

    @staticmethod
    def get_business_model_class_used() -> Iterable[BusinessModelName]:
        """Return list of business model classes used in this dataset."""
        return [
            BusinessModelName.MARKET_AREA,
            BusinessModelName.CONTROL_BLOCK,
            BusinessModelName.PORTFOLIO,
            BusinessModelName.THERMAL,
            BusinessModelName.LOAD,
            BusinessModelName.HYDRO,
            BusinessModelName.STORAGE,
            BusinessModelName.WIND,
            BusinessModelName.SOLAR,
            BusinessModelName.OTHER_NON_DISPATCHABLE,
        ]
