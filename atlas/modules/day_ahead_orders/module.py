"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Iterable

from pendulum import Duration

import atlas.config as cfg
from atlas import AtlasDataset, LazyScenarioMatrix, LazyTimeseries, ScenarioMatrix, Timeseries
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.enums import BusinessModelName
from atlas.modules.day_ahead_orders.input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.hydraulic_step import HydraulicStep
from atlas.modules.day_ahead_orders.steps.load_step import LoadStep
from atlas.modules.day_ahead_orders.steps.non_dispatchable_step import NonDispatchableStep
from atlas.modules.day_ahead_orders.steps.storage.storage_step import StorageStep
from atlas.modules.day_ahead_orders.steps.thermal.thermal_bidding_step import ThermalBiddingStep
from atlas.modules.day_ahead_orders.steps.wind_pv_step import WindPVStep
from atlas.timing import generate_datetimes, infer_frequency


class DayAheadOrdersModule(AbstractModule[DayAheadOrdersParameters, DayAheadOrdersInputDataset, DayAheadOrdersOutput]):
    def get_parameters_class(self):
        return DayAheadOrdersParameters

    def import_data(self, input_data: AtlasDataset, parameters: DayAheadOrdersParameters) -> DayAheadOrdersInputDataset:
        """Imports data using business objects and parameters."""
        return DayAheadOrdersInputDataset(input_data, parameters)

    def validate_data(self, parameters: DayAheadOrdersParameters, input_dataset: DayAheadOrdersInputDataset) -> bool:
        """Validates imported or generated data."""
        cfg.logger.debug("Validating timeseries timestep consistency for portfolio optimization")

        try:
            self._validate_timeseries_timestep_consistency(parameters, input_dataset)
            cfg.logger.debug("Timestep validation passed successfully")
            return True
        except ValueError as e:
            cfg.logger.error(f"Timestep validation failed: {e}")
            return False

    def _validate_timeseries_timestep_consistency(
        self,
        parameters: DayAheadOrdersParameters,
        input_dataset: DayAheadOrdersInputDataset,
    ) -> None:
        """Validate that all timeseries data have timestamps consistent with the optimization parameters."""
        expected_timestep = parameters.temporal.timestep
        cfg.logger.debug(f"Expected timestep: {expected_timestep}")

        validation_errors = []

        equipments: dict[str, list] = {
            "control_block": input_dataset.control_block,
            "market_area": input_dataset.market_area,
            "portfolio": input_dataset.portfolio,
            "wind": input_dataset.wind,
            "storage": input_dataset.storage,
            "hydro": input_dataset.hydro,
            "solar": input_dataset.solar,
            "thermal": input_dataset.thermal,
            "other_non_dispatchable": input_dataset.other_non_dispatchable,
            "load": input_dataset.load,
        }
        for equipment_type, equipment_list in equipments.items():
            for equipment in equipment_list:
                equipment_errors = self._validate_equipment_timeseries(equipment, expected_timestep, equipment_type)
                validation_errors.extend(equipment_errors)

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
                    cfg.logger.debug(f"Auto-corrected timestep for {equipment_name}.{attr_name}")

        return errors

    @staticmethod
    def _is_timeseries_type(obj) -> bool:
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
                cfg.logger.debug(
                    f"{context}: Timestep mismatch - expected {expected_timestep}, found {actual_timestep}. Attempting to fix..."
                )

                # Try to fix the timestep using set_frequency
                try:
                    if hasattr(timeseries_obj, "set_frequency"):
                        fixed_ts = timeseries_obj.set_frequency(expected_timestep, inplace=False)
                        result["timeseries"] = fixed_ts
                        result["fixed"] = True
                        cfg.logger.debug(f"{context}: Successfully adjusted timestep to {expected_timestep}")
                    else:
                        result["error"] = f"{context}: Cannot adjust timestep - object lacks set_frequency method"
                except Exception as e:
                    result["error"] = f"{context}: Failed to adjust timestep - {str(e)}"

        except ValueError as e:
            result["error"] = f"{context}: Could not validate timestep - {str(e)}"

        return result

    @staticmethod
    def _get_timeseries_timestep(timeseries_obj) -> Duration | None:
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

    def validates_results(
        self,
        parameters: DayAheadOrdersParameters,
        input_dataset: DayAheadOrdersInputDataset,
        output_dataset: DayAheadOrdersOutput,
    ) -> bool:
        """Validates results"""
        return True

    def export_results(
        self,
        parameters: DayAheadOrdersParameters,
        input_dataset: DayAheadOrdersInputDataset,
        output_dataset: DayAheadOrdersOutput,
    ) -> None:
        """Exports results."""
        pass

    def execute(
        self, parameters: DayAheadOrdersParameters, dataset: DayAheadOrdersInputDataset
    ) -> DayAheadOrdersOutput:
        """Executes the module's main logic."""
        cfg.logger.info("Initialization of the Day-Ahead Orders module...")
        output_dataset = DayAheadOrdersOutput(dataset)

        orders_time = generate_datetimes(
            parameters.temporal.start_date, parameters.penultimate_date, parameters.temporal.timestep
        )

        # ensure output folder exists
        if parameters.solver.export_lp:
            output_path = parameters.get_output_dir() / "lp_export"
            output_path.mkdir(parents=True, exist_ok=True)

        if len(orders_time) > 0:
            cfg.logger.info("Extraction completed, now starting the formulation of orders...")

            cfg.logger.info("Formulation of the load orders...")
            LoadStep.formulate_load_orders(output_dataset, orders_time, parameters)
            cfg.logger.info("Consumption orders formulated.")

            cfg.logger.info("Formulation of the non-dispatchable orders...")
            NonDispatchableStep.formulate_non_dispatchable_orders(output_dataset, orders_time, parameters)
            cfg.logger.info("Non-dispatchable orders formulated.")

            cfg.logger.info("Formulation of the storage orders...")
            storage = StorageStep(output_dataset, parameters)
            storage.formulate_storage_orders()
            cfg.logger.info("Storage orders formulated.")

            cfg.logger.info("Formulation of the hydraulic orders...")
            HydraulicStep.formulate_hydraulic_orders(output_dataset, orders_time, parameters)
            cfg.logger.info("Hydraulic orders formulated.")

            cfg.logger.info("Formulation of the wind/pv orders...")
            WindPVStep.formulate_wind_and_pv_orders(output_dataset, orders_time, parameters)
            cfg.logger.info("wind/pv orders formulated.")

            cfg.logger.info("Formulation of the thermic orders...")
            thermal_bidding = ThermalBiddingStep(output_dataset, orders_time, parameters)
            thermal_bidding.formulate_thermal_orders()
            cfg.logger.info("Thermic orders formulated.")

            cfg.logger.info("Formulation of orders successfully completed.")
        else:
            cfg.logger.warning("The time window to formulate orders is empty.")

        return output_dataset

    @staticmethod
    def get_business_model_class_used() -> Iterable[BusinessModelName]:
        return [
            BusinessModelName.CONTROL_BLOCK,
            BusinessModelName.MARKET_AREA,
            BusinessModelName.MARKET_BORDER,
            BusinessModelName.NODE,
            BusinessModelName.PORTFOLIO,
            BusinessModelName.WIND,
            BusinessModelName.STORAGE,
            BusinessModelName.HYDRO,
            BusinessModelName.SOLAR,
            BusinessModelName.THERMAL,
            BusinessModelName.LOAD,
            BusinessModelName.ORDER,
            BusinessModelName.ORDER_COUPLING,
        ]
