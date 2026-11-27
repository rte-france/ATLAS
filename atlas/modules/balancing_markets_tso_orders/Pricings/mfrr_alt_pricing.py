"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import need_slices_creation

import atlas.config as cfg
from atlas import AbstractTimeseries, ControlBlock, Order, Timeseries
from atlas.enums import OrderType, Product
from atlas.modules.balancing_markets_tso_orders import utils
from atlas.modules.balancing_markets_tso_orders.input_dataset import TSOOrdersInputDataset
from atlas.modules.balancing_markets_tso_orders.parameters import TSOOrdersParameters


def find_current_price_range(balancing_needs, spread_dict, max_bound):
    """Return the range within the spread_dict, associated with the indicated balancing_needs"""
    ranges_list = sorted(spread_dict.keys())

    for range_enum, studied_range in enumerate(ranges_list):
        if studied_range == max_bound:
            return max_bound

        if (abs(balancing_needs) >= studied_range) and (abs(balancing_needs) <= ranges_list[range_enum + 1]):
            return studied_range


def compute_mfrr_alt_pricing(
    dataset: TSOOrdersInputDataset,
    control_block: ControlBlock,
    total_needs_timeseries: AbstractTimeseries,
    parameters: TSOOrdersParameters,
):

    stack_costs_dictionary = {}
    slices_prices_dictionary = {}
    stack_energy_dictionary = {}

    volume_uncertainty = control_block.volume_uncertainty

    # --- First, divide the balancing needs into slices according to the volume risk aversion parameter

    # Volume risk aversion is not taken into account
    if not volume_uncertainty:
        (balancing_needs_dictionary, stack_energy_dictionary, slices_sizes_dictionary, extremum_times_dictionary) = (
            need_slices_creation.basic_slice_creation(total_needs_timeseries, parameters)
        )

    # Volume risk aversion is considered
    if volume_uncertainty:
        quantiles_dictionary, slices_sizes_dictionary = need_slices_creation.volume_uncertainty_slice_creation(
            total_needs_timeseries, parameters
        )

    # --- Compute the price of each slice according to the mfrr_alternative_prices_spread csv
    market_area = dataset.get_market_area_from_control_block(control_block)

    # Extract price spreads from the aforementioned csv
    f = open(parameters.mfrr_alternative_prices_spread)
    csv_lines = f.readlines()
    f.close()

    up_spread_dict = {}
    down_spread_dict = {}

    for line_enum, line in enumerate(csv_lines):
        if line_enum == 0:
            continue

        line_values = line.split(";")
        down_spread_dict[float(line_values[0])] = float(line_values[1])
        up_spread_dict[float(line_values[0])] = float(line_values[2])

    price_max_bound = max(up_spread_dict.keys())

    # Separate both cases of risk aversion
    if not volume_uncertainty:
        for slice_number in balancing_needs_dictionary.keys():
            # Initialize slices_prices_dictionary, stack_costs_dictionary and stack_energy_dictionary (correct that later)
            slices_prices_dictionary[slice_number] = Timeseries.from_timeseries(total_needs_timeseries)
            for time in slices_prices_dictionary[slice_number]:
                slices_prices_dictionary[slice_number].set_value(time, 0)

            stack_costs_dictionary[slice_number] = Timeseries.from_timeseries(total_needs_timeseries)
            for time in stack_costs_dictionary[slice_number]:
                stack_costs_dictionary[slice_number].set_value(time, 0)

            stack_energy_dictionary[slice_number] = Timeseries.from_timeseries(total_needs_timeseries)
            for time in stack_energy_dictionary[slice_number]:
                stack_energy_dictionary[slice_number].set_value(time, 0)

            local_balancing_needs = Timeseries.from_timeseries(balancing_needs_dictionary[slice_number])

            for time in local_balancing_needs:
                # Retrieve the studied_needs, and the DA price
                studied_needs = local_balancing_needs.get_value(time)
                da_price = market_area.da_price.get_value(time)

                stack_energy_dictionary[slice_number].set_value(
                    time, studied_needs * parameters.temporal.timestep.hours
                )

                local_slice_size = slices_sizes_dictionary[slice_number].get_value(time)

                # Skip the current slice if its size is null
                if local_slice_size == 0:
                    continue

                # New method: Simply compute the cost of the current stack of need, don't take into account slices
                # If the price is outside of the mFRR prices abacus
                if abs(studied_needs) >= price_max_bound:
                    if studied_needs < 0:
                        stack_costs_dictionary[slice_number].set_value(
                            time,
                            da_price
                            * down_spread_dict[price_max_bound]
                            * studied_needs
                            * parameters.temporal.timestep.hours,
                        )

                    else:
                        stack_costs_dictionary[slice_number].set_value(
                            time,
                            da_price
                            * up_spread_dict[price_max_bound]
                            * studied_needs
                            * parameters.temporal.timestep.hours,
                        )

                    continue

                # Regular case, separate upward and downward needs
                if studied_needs < 0:
                    price_range = find_current_price_range(abs(studied_needs), down_spread_dict, price_max_bound)
                    stack_costs_dictionary[slice_number].set_value(
                        time,
                        da_price * down_spread_dict[price_range] * studied_needs * parameters.temporal.timestep.hours,
                    )

                if studied_needs >= 0:
                    price_range = find_current_price_range(abs(studied_needs), up_spread_dict, price_max_bound)
                    stack_costs_dictionary[slice_number].set_value(
                        time,
                        da_price * up_spread_dict[price_range] * studied_needs * parameters.temporal.timestep.hours,
                    )

    # With risk aversion the price computation takes into account the probability of occurrence of each slice
    if volume_uncertainty:
        # Retrieve the ordered list of alpha values
        alpha_list = sorted(slices_sizes_dictionary.keys())

        for alpha in alpha_list:
            # Pass alpha == 0.01 and alpha == 0.99 as they only corresponds to bounds and not actual slices
            if alpha in [0.01, 0.99]:
                continue

            # Initialize slices_prices_dictionary, stack_costs_dictionary and stack_energy_dictionary
            slices_prices_ts = Timeseries.from_timeseries(total_needs_timeseries)
            for time in slices_prices_ts:
                slices_prices_ts.set_value(time, 0)
            slices_prices_dictionary[alpha] = slices_prices_ts

            stack_costs_dictionary[alpha] = Timeseries.from_timeseries(total_needs_timeseries)
            for time in stack_costs_dictionary[alpha]:
                stack_costs_dictionary[alpha].set_value(time, 0)

            stack_energy_dictionary[alpha] = Timeseries.from_timeseries(total_needs_timeseries)
            for time in stack_energy_dictionary[alpha]:
                stack_energy_dictionary[alpha].set_value(time, 0)

            for time in total_needs_timeseries:
                # Retrieve the DA price
                da_price = market_area.da_price.get_value(time)

                # Compute needs corresponding to the current slice
                if slices_sizes_dictionary[alpha].get_value(time) >= 0:
                    current_priced_needs = sum(
                        [
                            max(slices_sizes_dictionary[local_alpha].get_value(time), 0)
                            for local_alpha in alpha_list
                            if local_alpha <= alpha
                        ]
                    )
                else:
                    current_priced_needs = sum(
                        [
                            min(slices_sizes_dictionary[local_alpha].get_value(time), 0)
                            for local_alpha in alpha_list
                            if local_alpha >= alpha
                        ]
                    )

                stack_energy_dictionary[alpha].set_value(
                    time, current_priced_needs * parameters.temporal.timestep.hours
                )

                # Compute the price of current_priced_needs
                if current_priced_needs >= 0:
                    current_needs_range = find_current_price_range(
                        current_priced_needs, up_spread_dict, price_max_bound
                    )
                    current_costs = (
                        da_price
                        * up_spread_dict[current_needs_range]
                        * current_priced_needs
                        * parameters.temporal.timestep.hours
                    )
                else:
                    current_needs_range = find_current_price_range(
                        current_priced_needs, down_spread_dict, price_max_bound
                    )
                    current_costs = (
                        da_price
                        * down_spread_dict[current_needs_range]
                        * current_priced_needs
                        * parameters.temporal.timestep.hours
                    )

                # Compute the costs of future downward balancing (all alphas below current alpha)
                downward_costs = 0
                for alpha_index, alpha_below in enumerate(alpha_list):
                    if alpha_below >= alpha:
                        continue

                    next_alpha = alpha_list[alpha_index + 1]

                    downward_priced_needs = quantiles_dictionary[alpha_below].get_value(time) - quantiles_dictionary[
                        next_alpha
                    ].get_value(time)
                    downward_needs_range = find_current_price_range(
                        quantiles_dictionary[alpha_below].get_value(time) - quantiles_dictionary[alpha].get_value(time),
                        down_spread_dict,
                        price_max_bound,
                    )
                    downward_costs += (
                        0.1
                        * da_price
                        * down_spread_dict[downward_needs_range]
                        * downward_priced_needs
                        * parameters.temporal.timestep.hours
                    )

                # Compute the costs of future upward balancing (for all alphas above current alpha)
                upward_costs = 0
                for alpha_index, alpha_above in enumerate(alpha_list):
                    if alpha_above <= alpha:
                        continue

                    prev_alpha = alpha_list[alpha_index - 1]

                    upward_priced_needs = quantiles_dictionary[alpha_above].get_value(time) - quantiles_dictionary[
                        prev_alpha
                    ].get_value(time)
                    upward_needs_range = find_current_price_range(
                        quantiles_dictionary[alpha_above].get_value(time) - quantiles_dictionary[alpha].get_value(time),
                        up_spread_dict,
                        price_max_bound,
                    )
                    upward_costs += (
                        0.1
                        * da_price
                        * up_spread_dict[upward_needs_range]
                        * upward_priced_needs
                        * parameters.temporal.timestep.hours
                    )

                if parameters.debug:
                    cfg.logger.info(
                        f"mFRR alt pricing information for alpha {str(alpha)} at time {str(time)}: \n"
                        f"Volume of current stack = {str(current_priced_needs)} \n"
                        f"Costs of current stack = {str(current_costs)} \n"
                        f"Downward costs = {str(downward_costs)} \n"
                        f"Upward costs = {str(upward_costs)} \n"
                    )

                stack_costs_dictionary[alpha].set_value(time, (current_costs + downward_costs + upward_costs))

    # --- Formulate all market orders
    for time in total_needs_timeseries:
        # Separate both cases of risk aversion
        if not volume_uncertainty:
            for slice_number in slices_sizes_dictionary.keys():
                # Skip if the slice size is 0
                if slices_sizes_dictionary[slice_number].get_value(time) == 0:
                    continue

                # Set all information required in the market order
                if slices_sizes_dictionary[slice_number].get_value(time) > 0:
                    order_type = OrderType.Buy
                else:
                    order_type = OrderType.Sell

                order_price = round(
                    stack_costs_dictionary[slice_number].get_value(time)
                    / stack_energy_dictionary[slice_number].get_value(time),
                    2,
                )

                # Born the order price between market price caps
                order_price = min(order_price, parameters.market_price_cap)
                order_price = max(order_price, -parameters.market_price_cap)

                order_qmax = round(abs(slices_sizes_dictionary[slice_number].get_value(time)))
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
                    + utils.datetime_to_instance_name_string(time)[11:16]
                    + "_"
                    + utils.datetime_to_instance_name_string(time + parameters.temporal.timestep)[11:16]
                    + "_mFRR_alt_"
                    + str(slice_number)
                )

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
                dataset.bsp_order.append(order)

        if volume_uncertainty:
            for alpha in alpha_list:
                # Skip extreme alpha values
                if alpha in [0.01, 0.99]:
                    continue

                # Skip if the slice size is 0 (here taken less than 1, in absolute value)
                if abs(slices_sizes_dictionary[alpha].get_value(time)) < 1:
                    continue

                # Set all information required in the market order
                if slices_sizes_dictionary[alpha].get_value(time) > 0:
                    order_type = OrderType.Buy
                else:
                    order_type = OrderType.Sell

                # Order price
                order_price = round(
                    stack_costs_dictionary[alpha].get_value(time) / stack_energy_dictionary[alpha].get_value(time), 2
                )

                # Born the order price between market price caps
                order_price = min(order_price, parameters.market_price_cap)
                order_price = max(order_price, -parameters.market_price_cap)

                # Store the price in the corresponding dictionary
                slices_prices_dictionary[alpha].set_value(time, order_price)

                order_qmax = round(abs(slices_sizes_dictionary[alpha].get_value(time)))
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
                    + utils.datetime_to_instance_name_string(time)[11:16]
                    + "_"
                    + utils.datetime_to_instance_name_string(time + parameters.temporal.timestep)[11:16]
                    + "_mFRR_alt_"
                    + str(alpha)
                )

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
                dataset.bsp_order.append(order)
