"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import Duration
from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import BusinessModel, LazyScenarioMatrix, LazyTimeseries, ScenarioMatrix, Timeseries
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.abstract_class.abstract_parameters import module_parameters_type_var
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_output_dataset import DayAheadOrdersOutputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.orders_formulation.dao_load import DAOLoad
from atlas.modules.day_ahead_orders.orders_formulation.dao_storage import DAOStorage
from atlas.modules.day_ahead_orders.orders_formulation.hydraulic import Hydraulic
from atlas.modules.day_ahead_orders.orders_formulation.non_dispatchable import NonDispatchable
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_bidding import ThermalBidding
from atlas.modules.day_ahead_orders.orders_formulation.wind_pv import WindPV
from atlas.timing import generate_datetimes, infer_frequency


class DayAheadOrdersModule(
    AbstractModule[DayAheadOrdersParameters, DayAheadOrdersInputDataset, DayAheadOrdersOutputDataset]
):
    def get_parameters_class(self) -> type[module_parameters_type_var]:
        return DayAheadOrdersParameters

    def import_data(
        self, raw_data: dict[str, list[type[BusinessModel]]], parameters: DayAheadOrdersParameters
    ) -> DayAheadOrdersInputDataset:
        """Imports data using business objects and parameters."""
        return DayAheadOrdersInputDataset(raw_data, parameters)

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
        """Validate that all timeseries data have timesteps consistent with the optimization parameters."""
        expected_timestep = parameters.time_step
        cfg.logger.debug(f"Expected timestep: {expected_timestep}")

        validation_errors = []

        equipments = {
            "control_block": input_dataset.control_block,
            "market_area": input_dataset.market_area,
            "market_border": input_dataset.market_border,
            "node": input_dataset.node,
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

    def validates_results(
        self,
        parameters: DayAheadOrdersParameters,
        input_dataset: DayAheadOrdersInputDataset,
        output_dataset: DayAheadOrdersOutputDataset,
    ) -> bool:
        """Validates results"""
        return True

    def export_results(
        self,
        parameters: DayAheadOrdersParameters,
        input_dataset: DayAheadOrdersInputDataset,
        output_dataset: DayAheadOrdersOutputDataset,
    ) -> None:
        """Exports results."""
        pass

    def execute(
        self, parameters: DayAheadOrdersParameters, dataset: DayAheadOrdersInputDataset
    ) -> DayAheadOrdersOutputDataset:
        """Executes the module's main logic."""

        # Formulation of bids and orders on the day-ahead market.
        # In practice, several functions are run. Each function extract data from the input marker
        # and formulates bids or offers in the output marker. The latter is of class "Offer".

        #### STEP 0 - INITIALIZATION ####
        cfg.logger.info("Initialization of the Day-Ahead Orders module...")

        # Create the sequence of orders times. In particular, this sequence is such that the endDate of the last order will be before
        # the endDate of the overall time frame.
        orders_time = self._define_orders_time(parameters)
        if len(orders_time) > 0:
            cfg.logger.info("Extraction completed, now starting the formulation of orders...")

            #### STEP 1 - CONSUMPTION ####
            cfg.logger.info("Formulation of the load orders...")
            DAOLoad.formulate_load_orders(dataset, orders_time, parameters)
            cfg.logger.info("Consumption orders formulated.")

            #### STEP 2 - NON DISPATCHABLE UNITS ####
            cfg.logger.info("Formulation of the non-dispatchable orders...")
            NonDispatchable.formulate_non_dispatchable_orders(dataset, orders_time, parameters)
            cfg.logger.info("Non-dispatchable orders formulated.")

            #### STEP 3 - STORAGE UNITS ####
            cfg.logger.info("Formulation of the storage orders...")
            DAOStorage.formulate_storage_orders(dataset, parameters)
            cfg.logger.info("Storage orders formulated.")

            #### STEP 4 - LAKES UNITS ####
            cfg.logger.info("Formulation of the hydraulic orders...")
            Hydraulic.formulate_hydraulic_orders(dataset, orders_time, parameters)
            cfg.logger.info("Hydraulic orders formulated.")

            #### STEP 5 - WIND AND PV UNITS ####
            cfg.logger.info("Formulation of the wind/pv orders...")
            WindPV.formulate_wind_and_pv_orders(dataset, orders_time, parameters)
            cfg.logger.info("wind/pv orders formulated.")

            #### STEP 6 - THERMIC UNITS ####
            cfg.logger.info("Formulation of the thermic orders...")
            ThermalBidding.formulate_thermal_orders(dataset, orders_time, parameters)
            cfg.logger.info("Thermic orders formulated.")

            #### STEP - INDICATE TO THE USER THAT THE FORMULATION OF ORDERS IS COMPLETED.
            cfg.logger.info("Formulation of orders successfully completed.")

            # return output_dataset
        else:
            cfg.logger.error("orders_time is empty.")
        return DayAheadOrdersOutputDataset(dataset)

    def _define_orders_time(self, parameters: DayAheadOrdersParameters) -> list[DateTime]:
        """
        This function creates a sequence of timestamps between a start_date and a end_date
        with step deltaTime. It returns a list of DateTime objects.
        In particular, it makes sure that no time step crosses the end_date boundary.

        Arguments:
        - `parameters` an instance of DayAheadOrdersParameters.
        """
        orders_time = []
        if parameters.start_date < parameters.end_date:
            orders_time = generate_datetimes(parameters.start_date, parameters.penultimate_date, parameters.time_step)
        else:
            msg = "The end_date parameter must be posterior to the start_date parameter."
            cfg.logger.error(msg)
        return orders_time
