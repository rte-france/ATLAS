from pendulum import DateTime

from atlas.enum import StorageType
from atlas.models.equipment.storage import Storage
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


def get_variables_and_constraints_storage(
    time: DateTime,
    storage_equipments: list[Storage],
    model: OptimisationModel,
    sum_power_level,
    price_forecast,
    parameters: PortfolioOptimisationParameters,
):
    """
    This function adds constraints and elements in the objective function related to storage equipments.

    Arguments:
    - time: current time step
    - storage_equipments: dictionary of storage equipments
    - obj_function: objective function to optimize
    - constraint_list: list of constraints
    - sum_power_level: sum of power levels
    - reserve_up_ti: upward reserves at time t
    - reserve_down_ti: downward reserves at time t
    - automated_reserve_up_ti: automated upward reserves at time t
    - automated_reserve_down_ti: automated downward reserves at time t
    - price_forecast: price forecast data
    - parameters: parameters object
    """
    # Preload useful variables to avoid excessive call to functions or method
    prev_time = time - parameters.timestep

    for obj in storage_equipments:
        # Avoid equipments that have a maximum_energy of 0 (meaning that they are offline)
        if max(obj.maximum_energy.values()) <= 0:
            continue

        if obj.storage_type == StorageType.BATTERY:
            local_op_times = parameters.battery_op_times
        elif obj.storage_type == StorageType.PUMPED_HYDRAULIC_STORAGE:
            local_op_times = parameters.phs_op_times
        elif obj.storage_type == StorageType.ELECTRIC_VEHICLE:
            local_op_times = parameters.ev_op_times
        if time not in local_op_times:
            continue

        # Get max and min power
        max_power_ti = obj.maximum_power[time]
        min_power_ti = obj.minimum_power[time]

        # Check if those optimization variables are useful
        # contracted_difference
        reserve_up_ti.add(obj.reserves_up[time])
        reserve_down_ti.add(obj.reserves_down[time])

        # automated_contracted_difference
        automated_reserve_up_ti.add(obj.automated_reserves_up[time])
        automated_reserve_down_ti.add(obj.automated_reserves_down[time])

        # Add generation or consumption costs to objective function
        # FC: for storage units, the notion of costs should theoretically be managed by water values.
        # However, these values are not computed in ATLAS. To avoid weird arbitrages in the optim,
        # the variable cost of the unit is then set to the price of the studied market
        model.add_objective(
            price_forecast[time] * (obj.power_level_buy[time] + obj.power_level_sell[time]) * parameters.timestep
        )

        # For additional period
        if time not in parameters.target_times:
            if obj.storage_type == StorageType.BATTERY:
                nbr_fragment = parameters.battery_nb_fragments
                smoothing_factor = parameters.battery_smoothing_factor

            elif obj.storage_type == StorageType.ELECTRIC_VEHICLE:
                nbr_fragment = parameters.ev_nb_fragments
                smoothing_factor = parameters.ev_smoothing_factor

            else:
                nbr_fragment = parameters.phs_nb_fragments
                smoothing_factor = parameters.phs_smoothing_factor

            for n in range(0, nbr_fragment):
                # The objective function is the total profit over the optimisation period
                if nbr_fragment == 1 and n == 0:
                    model.add_objective(
                        -obj.power_level_sell_n[n][time] * price_forecast[time]
                        - obj.power_level_buy_n[n][time] * price_forecast[time]
                    )
                else:
                    model.add_objective(
                        -obj.power_level_sell_n[n][time]
                        * price_forecast[time]
                        * (1 - n * smoothing_factor / (nbr_fragment - 1))
                        - obj.power_level_buy_n[n][time]
                        * price_forecast[time]
                        * (1 + n * smoothing_factor / (nbr_fragment - 1))
                    )

                # Add constraint related to power fragment
                model.add_constraint(obj.power_level_buy_n[n][time] >= min_power_ti / nbr_fragment)
                model.add_constraint(obj.power_level_sell_n[n][time] <= max_power_ti / nbr_fragment)

            if nbr_fragment > 0:
                model.add_constraint(
                    obj.power_level_sell[time] == sum(obj.power_level_sell_n[n][time] for n in range(0, nbr_fragment))
                )
                model.add_constraint(
                    obj.power_level_buy[time] == sum(obj.power_level_buy_n[n][time] for n in range(0, nbr_fragment))
                )

        # Get global constraints
        sum_power_level.add(obj.power_level_buy[time])
        sum_power_level.add(obj.power_level_sell[time])

        # C. CONSTRAINTS ON THE CONTROL VARIABLE

        # Reserves requirements
        # We are in a case where there is no FLAT state, so manual reserves can be provided
        # as long as the unit is online.

        # relaxed_reserve disabling condition (eq. (43))

        # Impossible commitment and stable reserves constraints (eq. (44))
        model.add_constraint(obj.automated_reserves_up[time] <= obj.maximum_automated)
        model.add_constraint(obj.automated_reserves_down[time] <= obj.maximum_automated)
        model.add_constraint(obj.reserves_up[time] <= max_power_ti)
        model.add_constraint(obj.reserves_down[time] <= max_power_ti)

        # The power delivered by the equipment is between its maximum power and its minimum power
        # FC: I modify the following, it seems to me that there are confusions between power and energy in some constraints

        if obj.storage_type == StorageType.BATTERY or obj.storage_type == StorageType.PUMPED_HYDRAULIC_STORAGE:
            reserve_stored_energy_down_ti = obj.reserves_down[time] * (
                parameters.battery_reserve_duration
            ) + obj.automated_reserves_down[time] * (parameters.automated_battery_reserve_duration)
            reserve_stored_energy_up_ti = obj.reserves_up[time] * (
                parameters.battery_reserve_duration
            ) + obj.automated_reserves_up[time] * (parameters.automated_battery_reserve_duration)

            model.add_constraint(
                obj.power_level_sell[time]
                + obj.reserves_up[time]
                + obj.automated_reserves_up[time]
                + obj.unprovided_reserves_up[time]
                <= max_power_ti * obj.discharge_efficiency
            )
            model.add_constraint(
                obj.power_level_buy[time]
                - obj.reserves_down[time]
                - obj.automated_reserves_down[time]
                - obj.unprovided_reserves_down[time]
                >= min_power_ti * 1 / obj.charge_efficiency
            )

            model.add_constraint(
                obj.power_level_sell[time] <= max_power_ti * obj.discharge_efficiency * obj.is_sell[time]
            )
            model.add_constraint(
                obj.power_level_buy[time] >= min_power_ti * 1 / obj.charge_efficiency * (1 - obj.is_sell[time])
            )

        if obj.storage_type == StorageType.ELECTRIC_VEHICLE:
            reserve_stored_energy_down_ti = obj.reserves_down[time] * (
                parameters.battery_reserve_duration
            ) + obj.automated_reserves_down[time] * (parameters.automated_battery_reserve_duration)
            reserve_stored_energy_up_ti = obj.reserves_up[time] * (
                parameters.battery_reserve_duration
            ) + obj.automated_reserves_up[time] * (parameters.automated_battery_reserve_duration)

            model.add_constraint(
                (
                    obj.power_level_sell[time]
                    + obj.reserves_up[time]
                    + obj.automated_reserves_up[time]
                    + obj.unprovided_reserves_up[time]
                )
                <= (obj.is_v2g * max_power_ti * obj.discharge_efficiency)
            )
            model.add_constraint(
                (
                    obj.power_level_buy[time]
                    - obj.reserves_down[time]
                    - obj.automated_reserves_down[time]
                    - obj.unprovided_reserves_down[time]
                )
                >= min_power_ti * 1 / obj.charge_efficiency
            )

        # FC: Here we use the deltas between t and t+1 for displacement_energy and maximum_energy because there is a shift in indexing,
        # It would be much clearer if there were no indexes but simply time series.
        if time == parameters.start_date:
            model.add_constraint(
                obj.stored_energy[time]
                == obj.initial_stock * (obj.maximum_energy[time] / obj.maximum_energy[prev_time])
                - obj.power_level_buy[time] * obj.charge_efficiency * parameters.timestep
                - obj.power_level_sell[time] * parameters.timestep / (60.0 * obj.discharge_efficiency)
                + (obj.displacement_energy[time] - obj.displacement_energy[prev_time])
            )

            if parameters.verbose:
                msg = f"The energy stock at t1: {obj.initial_stock + (obj.maximum_energy[time] - obj.maximum_energy[prev_time])} MWh"
                api.io.trace.log(msg, api.io.log_type_info)

        elif time in local_op_times:
            model.add_constraint(
                obj.stored_energy[time]
                == obj.stored_energy[prev_time] * (obj.maximum_energy[time] / obj.maximum_energy[prev_time])
                - obj.power_level_buy[time] * obj.charge_efficiency * parameters.timestep
                - obj.power_level_sell[time] * parameters.timestep / (60.0 * obj.discharge_efficiency)
                + (obj.displacement_energy[time] - obj.displacement_energy[prev_time])
            )

        # For any time steps:
        # Respect of minimum and maximum stock constraints
        model.add_constraint(
            obj.stored_energy[time]
            >= obj.maximum_energy[time] * obj.minimum_state_of_charge[time] + reserve_stored_energy_up_ti
        )
        model.add_constraint(obj.stored_energy[time] <= obj.maximum_energy[time] - reserve_stored_energy_down_ti)

        # Global cycle balance (the reservoir level of the equipment remains
        # identical between the first and last dates of the optimization period)
        if time == parameters.start_date:
            model.add_constraint(
                sum(-obj.power_level_buy[time] for time in local_op_times) * obj.charge_efficiency
                == sum(obj.power_level_sell[time] for time in local_op_times) / obj.discharge_efficiency
            )
