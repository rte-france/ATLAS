def estimate_imbalance_prices(
    time,
    portfolio,
    market_area,
    controlBlock,
    ImbalPriceUp,
    LargeImbalPriceUp,
    ImbalPriceDown,
    LargeImbalPriceDown,
    p,
):
    """
    Estimates Imbalance Settlement Prices (ISP) at 'time' in 'portfolio', in both upward and downward directions,
    for both small and large imbalances. These estimations are then stored in ImbalPriceUp,
    LargeImbalPriceUp, ImbalPriceDown, LargeImbalPriceDown of the given portfolio.
    NB: Upward and downward ISPs can also be directly given in the input dataset (PositiveImbalancePrice and NegativeImbalancePrice).
    """
    # Retrieve the price timeseries used as reference for the ISP computation
    if p.use_forecast:
        if p.market == "DayAhead":
            price = market_area.PriceForecastMedium.GetForecast(p.execution_date, time, time).GetValue(time)
        elif p.market == "Intraday":
            price = market_area.IDPriceForecast.GetForecast(p.execution_date, time, time).GetValue(time)
    else:
        if p.market == "DayAhead":
            price = get_time_series_value(market_area.DAPrice, time)
        elif p.market == "Intraday":
            price_da = get_time_series_value(market_area.DAPrice, time)
            price_id = market_area.IDPrice.GetForecast(p.execution_date, time, time).GetValue(time)

            # price = (price_da + price_id)/2
            price = price_id

        elif p.market == "RRActivation":
            price = get_time_series_value(market_area.RRActivationPrice, time)
        elif p.market == "MFRRActivation":
            price = get_time_series_value(market_area.MFRRActivationPrice, time)

    # Estimation of ISPs
    # Default case, ISP indicated in input marker
    if controlBlock.NegativeImbalancePrice.Length > 0:
        ImbalPriceUp[time] = get_time_series_value(controlBlock.NegativeImbalancePrice, time) * (
            1 + p.small_imbalance_penalty
        )
        LargeImbalPriceUp[time] = get_time_series_value(controlBlock.NegativeImbalancePrice, time) * (
            1 + p.large_imbalance_penalty
        )
    else:
        """
        # FC: Estimation according to an affine function
        ImbalPriceUp[time] = (1.0 + p.small_imbalance_penalty ) * price + p.imbalance_penalty_offset
        LargeImbalPriceUp[time] = (1.0 + p.large_imbalance_penalty ) * price + p.imbalance_penalty_offset

        """
        # FC: Estimation according to the French process
        # Specific case when the reference price is null, add an arbitrarily small value to avoid side effects
        # (e.g. shutting down all renewable units as it is equivalent for them to produce or not in the optimization)
        if abs(price) < p.isp_forecast_lower_bound:
            if price >= 0:
                ImbalPriceUp[time] = (1 + p.small_imbalance_penalty) * p.isp_forecast_lower_bound
                LargeImbalPriceUp[time] = (1 + p.large_imbalance_penalty) * p.isp_forecast_lower_bound
            else:
                ImbalPriceUp[time] = (1 - p.small_imbalance_penalty) * (-p.isp_forecast_lower_bound)
                LargeImbalPriceUp[time] = (1 - p.large_imbalance_penalty) * (-p.isp_forecast_lower_bound)

        else:
            if price >= 0:
                ImbalPriceUp[time] = (1 + p.small_imbalance_penalty) * price
                LargeImbalPriceUp[time] = (1 + p.large_imbalance_penalty) * price
            else:
                ImbalPriceUp[time] = (1 - p.small_imbalance_penalty) * price
                LargeImbalPriceUp[time] = (1 - p.large_imbalance_penalty) * price

    # Default case, ISP indicated in input marker
    if controlBlock.PositiveImbalancePrice.Length > 0:
        ImbalPriceDown[time] = get_time_series_value(controlBlock.PositiveImbalancePrice, time) * (
            1 - p.small_imbalance_penalty
        )
        LargeImbalPriceDown[time] = get_time_series_value(controlBlock.PositiveImbalancePrice, time) * (
            1 - p.large_imbalance_penalty
        )
    else:
        """
        # FC: Estimation according to an affine function
        ImbalPriceDown[time] = (1.0 - p.small_imbalance_penalty ) * price + p.imbalance_penalty_offset
        LargeImbalPriceDown[time] = (1.0 - p.large_imbalance_penalty ) * price + p.imbalance_penalty_offset

        """
        # FC: Estimation according to the French process
        # Specific case when the reference price is null
        if abs(price) < p.isp_forecast_lower_bound:
            if price >= 0:
                ImbalPriceDown[time] = (1 - p.small_imbalance_penalty) * p.isp_forecast_lower_bound
                LargeImbalPriceDown[time] = (1 - p.large_imbalance_penalty) * p.isp_forecast_lower_bound
            else:
                ImbalPriceDown[time] = (1 + p.small_imbalance_penalty) * (-p.isp_forecast_lower_bound)
                LargeImbalPriceDown[time] = (1 + p.large_imbalance_penalty) * (-p.isp_forecast_lower_bound)

        else:
            if price >= 0:
                ImbalPriceDown[time] = (1 - p.small_imbalance_penalty) * price
                LargeImbalPriceDown[time] = (1 - p.large_imbalance_penalty) * price
            else:
                ImbalPriceDown[time] = (1 + p.small_imbalance_penalty) * price
                LargeImbalPriceDown[time] = (1 + p.large_imbalance_penalty) * price


import API


# Function
def set_manual_activation(equipment_list, p):
    # Directly update the power matrix and the possible stored energy matrix, if it exists, for all equipments in the portfolio
    for equipment in equipment_list:
        if p.market == "DayAhead":
            new_power = equipment.DAClearedQuantity.Extract("LocalDACleared", p.target_times)
            activated_power = new_power

        if p.market == "Intraday":
            new_power = equipment.DAClearedQuantity.Extract(
                "LocalDACleared", p.target_times
            ) + equipment.TotalIDClearedQuantity.Extract("LocalIDCleared", p.target_times)
            activated_power = equipment.IDClearedQuantity.GetForecast(
                p.execution_date, p.start_date, p.end_date
            ).Extract("LocalIDCleared", p.target_times)

        # Before updating Power, check if all activated powers are not equal to 0
        # If it's the case, skip the equipment to not overload the Power matrix with useless data
        # Exceptions: PV and Wind, and Thermic because of the initialization timeseries
        if not p.use_forecast:
            if equipment.Class not in ["Wind", "Photovoltaic", "Thermic"]:
                if (
                    activated_power.Max() <= p.allowed_round_off_error
                    and abs(activated_power.Min()) <= p.allowed_round_off_error
                ):
                    continue

        # Correct cases when previous rounding leads to power out of bounds
        # Preload MaximumPowerForecast in the case of Load and other equipments to avoid excessive computational time
        if equipment.Class in ["Load", "Wind", "Photovoltaic", "OtherNonDispatchable"]:
            max_power = equipment.MaximumPowerForecast.GetForecast(p.execution_date, p.start_date, p.end_date)

        for time in new_power.Index:
            # _ Any case where Power is greater than MaximumPower (set to 0 for Load equipemnts)
            if equipment.Class == "Load":
                local_max_power = 0
            elif equipment.Class in ["Wind", "Photovoltaic", "OtherNonDispatchable"]:
                local_max_power = max_power.GetValue(time)
            else:
                local_max_power = equipment.MaximumPower.GetValue(time)

            if new_power.GetValue(time) > local_max_power:
                new_power.SetValue(time, local_max_power)

            # _ Any case where Power is negative for Thermic, Hydraulic, Wind and PV equipments
            if equipment.Class in ["Thermic", "Hydraulic", "Wind", "Photovoltaic"]:
                if new_power.GetValue(time) < 0:
                    new_power.SetValue(time, 0)

            # _ Any case where Power is below MinimumPower for any unit type other than Thermic
            if equipment.Class != "Thermic":
                if equipment.Class == "Load":
                    local_min_power = max_power.GetValue(time)
                elif equipment.Class in ["Wind", "Photovoltaic"]:
                    local_min_power = max_power.GetValue(time) * (1 - equipment.MaximumCurtailmentRatio.GetValue(time))
                elif equipment.Class in ["Storage", "Hydraulic"]:
                    local_min_power = equipment.MinimumPower.GetValue(time)
                elif equipment.Class == "OtherNonDispatchable":
                    local_min_power = local_max_power

                if new_power.GetValue(time) < local_min_power:
                    new_power.SetValue(time, local_min_power)

        # 3)
        if equipment.Class in ["Hydraulic", "Storage"]:
            new_stored_energy = API.TimeSeries.NewTimeSeries(
                "StoredEnergy", API.TimeSeries.Constant, "MWh", p.target_times, 0
            )
            # First, retrieve the initial storage level
            stored_energy_matrix = equipment.StoredEnergy
            if stored_energy_matrix.Index:
                local_stored_energy = stored_energy_matrix.GetForecast(
                    p.execution_date, p.start_date.AddMinutes(-p.time_step), p.start_date
                )
                if local_stored_energy.FirstDate <= p.start_date.AddMinutes(-p.time_step):
                    initial_stored_energy = local_stored_energy.GetValue(p.start_date.AddMinutes(-p.time_step))

                else:
                    if equipment.Class == "Hydraulic":
                        initial_stored_energy = equipment.InitialLevel.GetValue(p.start_date.AddMinutes(-p.time_step))

                    else:
                        initial_stored_energy = equipment.StorageInitialLevel * equipment.MaximumEnergy.GetValue(
                            p.start_date.AddMinutes(-p.time_step)
                        )

            else:
                if equipment.Class == "Hydraulic":
                    initial_stored_energy = equipment.InitialLevel.GetValue(p.start_date.AddMinutes(-p.time_step))

                else:
                    initial_stored_energy = equipment.StorageInitialLevel * equipment.MaximumEnergy.GetValue(
                        p.start_date.AddMinutes(-p.time_step)
                    )

            # Update the StoredEnergy matrix
            # If the stored energy goes above MaximumEnergy or below MinimumEnergy, the power output is changed to respect boundaries
            out_of_bounds_dict = {}
            for time_enum, time in enumerate(p.target_times):
                max_energy = equipment.MaximumEnergy.GetValue(time)
                if equipment.Class == "Storage":
                    min_energy = max_energy * equipment.MinimumStateOfCharge.GetValue(time)
                else:
                    min_energy = equipment.MinimumEnergy.GetValue(time)

                if time_enum == 0:
                    previous_value = initial_stored_energy
                else:
                    previous_value = new_stored_energy.GetValue(time.AddMinutes(-p.time_step))

                if equipment.Class == "Storage":
                    if new_power.GetValue(time) > 0:
                        # Special case for ElectricVehicle
                        if equipment.StorageType == "ElectricVehicle":
                            new_energy_value = (
                                previous_value
                                * (
                                    equipment.MaximumEnergy.GetValue(time)
                                    / equipment.MaximumEnergy.GetValue(time.AddMinutes(-p.time_step))
                                )
                                - new_power.GetValue(time) * p.time_step / 60.0 * 1 / equipment.DischargeEfficiency
                            )
                        else:
                            new_energy_value = (
                                previous_value
                                - new_power.GetValue(time) * p.time_step / 60.0 * 1 / equipment.DischargeEfficiency
                            )
                    else:
                        # Special case for ElectricVehicle
                        if equipment.StorageType == "ElectricVehicle":
                            new_energy_value = (
                                previous_value
                                * (
                                    equipment.MaximumEnergy.GetValue(time)
                                    / equipment.MaximumEnergy.GetValue(time.AddMinutes(-p.time_step))
                                )
                                - new_power.GetValue(time) * p.time_step / 60.0 * equipment.ChargeEfficiency
                            )
                        else:
                            new_energy_value = (
                                previous_value
                                - new_power.GetValue(time) * p.time_step / 60.0 * equipment.ChargeEfficiency
                            )
                else:
                    new_energy_value = previous_value - new_power.GetValue(time) * p.time_step / 60.0

                if new_energy_value <= max_energy:
                    if new_energy_value >= min_energy:
                        new_stored_energy.SetValue(time, new_energy_value)
                    else:
                        # Value below low bound
                        if p.debug:
                            API.IO.Trace.Log(
                                f"Stored energy below low bound and corrected for equipment {equipment.Name} at time {str(time)}"
                            )
                        new_stored_energy.SetValue(time, min_energy)
                        out_of_bounds_dict[time] = (min_energy - new_energy_value) * p.time_step / 60.0

                else:
                    # Value above high bound
                    if p.debug:
                        API.IO.Trace.Log(
                            f"Stored energy above high bound and corrected for equipment {equipment.Name} at time {str(time)}"
                        )
                    new_stored_energy.SetValue(time, max_energy)
                    out_of_bounds_dict[time] = (max_energy - new_energy_value) * p.time_step / 60.0

            # Correct the power output when needed
            for time in out_of_bounds_dict.keys():
                if equipment.Class == "Storage":
                    if new_power.GetValue(time) > 0:
                        new_power.SetValue(
                            time,
                            new_power.GetValue(time) - out_of_bounds_dict[time] * equipment.DischargeEfficiency,
                        )
                    else:
                        new_power.SetValue(
                            time,
                            new_power.GetValue(time) - out_of_bounds_dict[time] * 1 / equipment.ChargeEfficiency,
                        )
                else:
                    new_power.SetValue(time, new_power.GetValue(time) - out_of_bounds_dict[time])

            # Add an extra timestep to StoredEnergy for interpolation purposes
            new_stored_energy.SetValue(p.end_date.AddMinutes(p.time_step), new_stored_energy.GetValue(p.end_date))

            if not p.use_forecast:
                if p.execution_date in stored_energy_matrix.Index:
                    equipment.StoredEnergy.DeleteTimeSeries(p.execution_date)

                equipment.StoredEnergy.AddTimeSeries(p.execution_date, new_stored_energy)

        # Export the new power level
        # Add extra time step to Power for interpolation purposes
        new_power.SetValue(
            p.end_date.AddMinutes(p.time_step),
            equipment.Power.GetForecast(
                p.execution_date,
                p.end_date.AddMinutes(p.time_step),
                p.end_date.AddMinutes(p.time_step),
            ).GetValue(p.end_date.AddMinutes(p.time_step)),
        )

        if p.use_forecast:
            equipment.IDPOForOrders.AddTimeSeries(p.execution_date, new_power)
        else:
            if p.execution_date in equipment.Power.Index:
                equipment.Power.DeleteTimeSeries(p.execution_date)
            equipment.Power.AddTimeSeries(p.execution_date, new_power)

    if p.verbose:
        if len(equipment_list) > 1:
            API.IO.Trace.Log(
                f"Manual activation of portfolio {equipment_list[0].Portfolio.Name} completed",
                API.IO.LogTypeWarn,
            )
        else:
            API.IO.Trace.Log(
                f"Manual activation of equipment {equipment_list[0].Name} completed",
                API.IO.LogTypeWarn,
            )
