"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas import Order, Timeseries, generate_datetimes
from atlas.abstract_class.module import AbstractModule
from atlas.enums import BusinessModelName, LoadType, OrderType, Product, ReservesTypes
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.balancing_markets_tso_orders.input_dataset import TSOOrdersInputDataset
from atlas.modules.balancing_markets_tso_orders.parameters import TSOOrdersParameters
from atlas.modules.balancing_markets_tso_orders.result import TSOOrdersResult


class TSOOrdersModule(AbstractModule[TSOOrdersParameters, TSOOrdersInputDataset, TSOOrdersResult]):
    @classmethod
    def get_parameters_class(cls) -> type[TSOOrdersParameters]:
        return TSOOrdersParameters

    def import_data(self, input_data: AtlasDataset, parameters: TSOOrdersParameters) -> TSOOrdersInputDataset:
        """Imports data using business objects and parameters."""
        return TSOOrdersInputDataset(
            input_data.set_frequency_all(parameters.temporal.timestep, inplace=True), parameters
        )

    def validate_data(self, parameters: TSOOrdersParameters, input_dataset: TSOOrdersInputDataset) -> bool:
        """Validates imported or generated data."""
        return True

    def validates_results(
        self,
        parameters: TSOOrdersParameters,
        input_dataset: TSOOrdersInputDataset,
        result: TSOOrdersResult,
    ) -> bool:
        """Validates results"""
        return True

    def export_results(
        self,
        parameters: TSOOrdersParameters,
        input_dataset: TSOOrdersInputDataset,
        result: TSOOrdersResult,
    ) -> None:
        """Exports results."""
        pass

    def execute(self, parameters: TSOOrdersParameters, input_dataset: TSOOrdersInputDataset) -> TSOOrdersResult:
        cfg.logger.info("Initialization of the Balancing market TSO orders module...")
        end_date = parameters.temporal.end_date - parameters.temporal.timestep

        balancing_time_frame = generate_datetimes(
            parameters.temporal.start_date, end_date, parameters.temporal.timestep
        )

        for control_block in input_dataset.control_block:
            if control_block.name in parameters.included_control_blocks:
                # TODO
                # Identify the TSO and MarketArea related to the ControlBlock.
                market_area = control_block.GetChildren("MarketArea")[0]
                market_area = input_dataset.market_area[0]

                if parameters.verbose:
                    cfg.logger.info("Studied ControlBlock: " + str(control_block))
                    cfg.logger.info("*** Needs computation phase ***")

                # TODO : cette timeseries était déclarée avec l'unit "MW"
                total_needs_timeseries = Timeseries.from_index(
                    parameters.temporal.start_date, parameters.temporal.timestep, end_date, default_value=0
                )

                for time in balancing_time_frame:
                    if parameters.apply_tso_volume_limit:
                        # Compute the sum of the Qmax of all BSP upward orders in the area. Repeat the process for BSP downward orders.
                        # This will define boundaries for the need that can be asked by the TSO on balancing markets
                        # Several exclusive orders may exist for the same equipment, on the same time.
                        # Only the highest Qmax is considered in that case
                        bsp_orders_upward_sum = 0
                        bsp_orders_downward_sum = 0
                        equipment_already_included_upward = {}
                        equipment_already_included_downward = {}

                        # First, get a list of all Orders included in Parent_Children couplings, to deal with startup orders
                        # In addition, create a dictionary storing them in a explicit manner
                        pc_orders = []
                        pc_orders_dict = {}
                        for coupling_instance in input_dataset.order_coupling:
                            if coupling_instance.coupling_type != "PARENT_CHILDREN":
                                continue

                            for order_enum, order in enumerate(coupling_instance.orders):
                                parent_order_name = order.name
                                if order_enum == 0:
                                    pc_orders.append(order)
                                    pc_orders_dict[parent_order_name] = []

                                else:
                                    pc_orders.append(order)
                                    pc_orders_dict[parent_order_name].append(order)

                        for bsp_order in input_dataset.bsp_order:
                            if bsp_order.is_agent_tso:
                                continue

                            if bsp_order.market_area.name != market_area.name:
                                continue

                            if bsp_order.product != parameters.market:
                                continue

                            if bsp_order.start_date != parameters.temporal.start_date:
                                continue

                            # First, deal with parent children orders, by spotting the parent
                            if bsp_order in pc_orders_dict.keys():
                                qmax_maximum_in_children = max(
                                    [child_order.qmax for child_order in pc_orders_dict[bsp_order.name]]
                                )

                                if bsp_order.order_type == OrderType.Sell:
                                    if bsp_order.equipment.name in equipment_already_included_upward.keys():
                                        bsp_orders_upward_sum += (
                                            bsp_order.qmax + qmax_maximum_in_children
                                        ) - equipment_already_included_upward[bsp_order.equipment.name]

                                    else:
                                        equipment_already_included_upward[bsp_order.equipment.name] = (
                                            bsp_order.qmax + qmax_maximum_in_children
                                        )
                                        bsp_orders_upward_sum += bsp_order.qmax + qmax_maximum_in_children

                                if bsp_order.order_type == OrderType.Buy:
                                    if bsp_order.equipment.name in equipment_already_included_downward.keys():
                                        bsp_orders_downward_sum += (
                                            bsp_order.qmax + qmax_maximum_in_children
                                        ) - equipment_already_included_downward[bsp_order.equipment.name]

                                    else:
                                        equipment_already_included_downward[bsp_order.equipment.name] = (
                                            bsp_order.qmax + qmax_maximum_in_children
                                        )
                                        bsp_orders_downward_sum += bsp_order.qmax + qmax_maximum_in_children

                            # Do not consider parent children orders anymore
                            if bsp_order in pc_orders:
                                continue
                            # For other orders
                            else:
                                if bsp_order.order_type == OrderType.Sell:
                                    if bsp_order.equipment.name in equipment_already_included_upward.keys():
                                        if bsp_order.qmax > equipment_already_included_upward[bsp_order.equipment.name]:
                                            bsp_orders_upward_sum += (
                                                bsp_order.qmax
                                                - equipment_already_included_upward[bsp_order.equipment.name]
                                            )
                                            equipment_already_included_upward[bsp_order.equipment.name] = bsp_order.qmax
                                    else:
                                        equipment_already_included_upward[bsp_order.equipment.name] = bsp_order.qmax
                                        bsp_orders_upward_sum += bsp_order.qmax

                                if bsp_order.order_type == OrderType.Buy:
                                    if bsp_order.equipment.name in equipment_already_included_downward.keys():
                                        if (
                                            bsp_order.qmax
                                            > equipment_already_included_downward[bsp_order.equipment.name]
                                        ):
                                            bsp_orders_downward_sum += (
                                                bsp_order.qmax
                                                - equipment_already_included_downward[bsp_order.equipment.name]
                                            )
                                            equipment_already_included_downward[bsp_order.equipment.name] = (
                                                bsp_order.qmax
                                            )
                                    else:
                                        equipment_already_included_downward[bsp_order.equipment.name] = bsp_order.qmax
                                        bsp_orders_downward_sum += bsp_order.qmax
                    # Creating empty variables to store the total load and total production of all Equipments in the ControlBlock
                    total_production = 0
                    total_load = 0

                    # Find all Nodes that are within the ControlBlock
                    # TODO
                    nodes_in_control_block = control_block.GetChildren("Node")

                    # Third loop, on Nodes, to identify the Equipments within the ControlBlock
                    for node in nodes_in_control_block:
                        # TODO
                        equipments_in_node = node.GetChildren("Equipment")

                        # Fourth loop, on Equipments within the node, to extract the forecasted power
                        for equipment in equipments_in_node:
                            # Compute the projected power of the equipment for the studied time
                            # The MaximumPowerForecast is only taken as reference for the main load equipment of each node
                            if equipment.Class == "Load":
                                if equipment.LoadType in [LoadType.POWER_TO_GAS, LoadType.OTHER_NON_DISPATCHABLE_LOAD]:
                                    forecasted_power = Timeseries.from_values(
                                        parameters.temporal.start_date, parameters.temporal.timestep, equipment.power
                                    ).get_value(time)
                                else:
                                    forecasted_power = equipment.maximum_power_forecast.get_forecast(
                                        parameters.temporal.execution_date,
                                        parameters.temporal.start_date,
                                        parameters.temporal.end_date,
                                    ).get_value(time)
                            else:
                                if equipment.Class in [BusinessModelName.WIND, "Photovoltaic"]:
                                    if parameters.use_res_forecasts:
                                        forecasted_power = equipment.maximum_power_forecast.get_forecast(
                                            parameters.temporal.execution_date,
                                            parameters.temporal.start_date,
                                            parameters.temporal.end_date,
                                        ).get_value(time)
                                    else:
                                        forecasted_power = equipment.power.get_forecast(
                                            parameters.temporal.execution_date,
                                            parameters.temporal.start_date,
                                            parameters.temporal.end_date,
                                        ).get_value(time)
                                else:
                                    forecasted_power = equipment.power.get_forecast(
                                        parameters.temporal.execution_date,
                                        parameters.temporal.start_date,
                                        parameters.temporal.end_date,
                                    ).get_value(time)

                            # Add the forecasted_power_timeseries to the corresponding total timeseries (that can either be load or production)
                            if str(equipment.Class) == "Load":
                                total_load = total_load + forecasted_power
                            else:
                                total_production = total_production + forecasted_power

                        # Compute the total need for the ControlBlock, and store it in the total timeseries
                        # Load is represented as negative production in ATLAS. Hence, we take its absolute value for the following computation
                        total_need = (
                            abs(total_load)
                            - total_production
                            + (
                                market_area.da_balance.get_value(time)
                                + market_area.total_id_balance.get_value(time)
                                + market_area.rr_activation_balance.get_value(time)
                                + market_area.mfrr_activation_balance.get_value(time)
                            )
                        )

                        # Set up demand volume limits, if requested by the user
                        if parameters.apply_tso_volume_limit:
                            if total_need >= 0:
                                total_need = min(total_need, bsp_orders_upward_sum)
                            else:
                                total_need = max(total_need, -bsp_orders_downward_sum)

                        total_needs_timeseries.set_value(time, total_need)

                # Store the total_needs_timeseries in the output_marker
                if parameters.market == Product.RRActivation:
                    control_block.rr_needs.add(total_needs_timeseries, parameters.temporal.execution_date)
                if parameters.market == Product.MFRRActivation:
                    control_block.mfrr_needs.add(total_needs_timeseries, parameters.temporal.execution_date)

                # ------ Price computation and Order instances creation
                # For each time of the balancing_time_frame, compute the price according to the pricing_type parameter
                # Then, store the results in Order instances in the output_marker
                if parameters.verbose:
                    cfg.logger.info("*** Pricing phase ***")

                # --- At all costs pricing
                if control_block.alternative_type == "None":
                    for time in balancing_time_frame:
                        # Extract the needs corresponding to the current time from total_needs_timeseries
                        total_need = total_needs_timeseries.get_value(time)

                        if total_need > 1:
                            # Identify the MarketArea and the Portfolio related with the ControlBlock.
                            # TODO
                            market_area = control_block.GetChildren("MarketArea")[0]
                            market_area = input_dataset.market_area[0]

                            # Compute the price and the order type, and other useful informations for the order
                            order_price = parameters.market_price_cap
                            order_type = "Buy"
                            order_qmax = round(total_need)
                            order_qmin = 0
                            if parameters.market == Product.RRActivation:
                                complete_market_type = "RR"
                            elif parameters.market == Product.MFRRActivation:
                                complete_market_type = "MFRR"
                            else:
                                complete_market_type = "Other"
                            is_agent_tso = True
                            order_name = (
                                str(control_block.name)
                                + "_"
                                + complete_market_type
                                + "_"
                                + self.datetime_to_instance_name_string(time)[11:16]
                                + "_"
                                + self.datetime_to_instance_name_string(time + parameters.temporal.timestep)[11:16]
                            )

                            # Store results in the output_marker
                            if order_qmax > parameters.allowed_round_off_error:
                                order = Order(
                                    name=order_name,
                                    execution_date=parameters.temporal.execution_date,
                                    start_date=time,
                                    end_date=time + parameters.temporal.timestep,
                                    product=parameters.market,
                                    order_type=order_type,
                                    price=order_price,
                                    qmin=order_qmin,
                                    qmax=order_qmax,
                                    is_agent_tso=is_agent_tso,
                                    market_area=market_area,  # TODO remove this part when the Clearing is adapted to balancing markets (i.e. with TSO orders)
                                )
                                input_dataset.bsp_order.append(order)

                        elif total_need < 0:
                            # Identify the MarketArea and the Portfolio related with the ControlBlock.
                            # TODO
                            market_area = control_block.GetChildren("MarketArea")[0]
                            market_area = input_dataset.market_area[0]

                            # Compute the price and the order type, and other useful informations for the order
                            order_price = -parameters.market_price_cap
                            order_type = "Sell"
                            order_qmax = abs(total_need)
                            order_qmin = 0
                            if parameters.market == Product.RRActivation:
                                complete_market_type = "RR"
                            elif parameters.market == Product.MFRRActivation:
                                complete_market_type = "MFRR"
                            else:
                                complete_market_type = "Other"

                            is_agent_tso = True
                            order_name = (
                                str(control_block.name)
                                + "_"
                                + complete_market_type
                                + "_"
                                + self.datetime_to_instance_name_string(time)[11:16]
                                + "_"
                                + self.datetime_to_instance_name_string(time + parameters.temporal.timestep)[11:16]
                            )

                            # Store results in the output_marker
                            if order_qmax > parameters.allowed_round_off_error:
                                order = Order(
                                    name=order_name,
                                    execution_date=parameters.temporal.execution_date,
                                    start_date=time,
                                    end_date=time + parameters.temporal.timestep,
                                    product=parameters.market,
                                    order_type=order_type,
                                    price=order_price,
                                    qmin=order_qmin,
                                    qmax=order_qmax,
                                    is_agent_tso=is_agent_tso,
                                    market_area=market_area,  # TODO remove this part when the Clearing is adapted to balancing markets (i.e. with TSO orders)
                                )
                                input_dataset.bsp_order.append(order)

                if control_block.alternative_type == ReservesTypes.mFRR:
                    # TODO
                    print("TODO")
                    # mfrr_alt_pricing.compute_mfrr_alt_pricing(output_marker, control_block, total_needs_timeseries, p)

                if control_block.alternative_type == ReservesTypes.aFRR:
                    cfg.logger.error("aFRR market alternative is not implemented yet")

    def datetime_to_instance_name_string(self, datetime):
        """
        Takes a DateTime as input and returns a string with no special character, that can be used within an instance name

        Example : If the input is DateTime(2028, 01, 01, 10, 30, 00), i.e. "01/01/2028 10:30:00", the string output will be 2028_01_01_10_30_00
        """
        return (
            str(datetime)[6:10]
            + "_"
            + str(datetime)[3:5]
            + "_"
            + str(datetime)[0:2]
            + "_"
            + str(datetime)[11:13]
            + "_"
            + str(datetime)[14:16]
            + "_"
            + str(datetime)[17:19]
        )
