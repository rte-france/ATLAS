import sys

import API


def GetVariablesAndConstraints_Storage(
    time,
    equipments_DS,
    objFunction,
    constraintList,
    sum_power_level,
    reserveUpti,
    reserveDownti,
    automatedReserveUpti,
    automatedReserveDownti,
    priceForecast,
    p,
):
    # Preload useful variables to avoid excessive call to functions or method
    prev_time = time.AddMinutes(-p.time_step)

    for equipment_name, PO_DSj in equipments_DS.items():
        # Avoid equipments that have a MaximumEnergy of 0 (meaning that they are offline)
        if max(PO_DSj.MaximumEnergy.values()) <= 0:
            if p.debug:
                API.IO.Trace.Log(f"Equipment {equipment_name} avoided, as its MaximumEnergy is 0")
            continue

        if PO_DSj.StorageType == "Battery":
            local_op_times = p.battery_op_times
        elif PO_DSj.StorageType == "PumpedHydraulicStorage":
            local_op_times = p.phs_op_times
        elif PO_DSj.StorageType == "ElectricVehicle":
            local_op_times = p.ev_op_times
        if time not in local_op_times:
            continue

        # Get max and min power
        maxPowerti = PO_DSj.MaximumPower[time]
        minPowerti = PO_DSj.MinimumPower[time]

        # That part chek if those opti variable are usefull
        # contractedDifference
        reserveUpti.Add(PO_DSj.reservesUp[time])
        reserveDownti.Add(PO_DSj.reservesDown[time])

        # automatedContractedDifference
        automatedReserveUpti.Add(PO_DSj.automatedReservesUp[time])
        automatedReserveDownti.Add(PO_DSj.automatedReservesDown[time])

        # Add generation or consumption costs to objective function
        # FC: for storage units, the notion of costs should theoretically be managed by water values.
        # However, these values are not computed in ATLAS. To avoid weird arbitrages in the optim,
        # the variable cost of the unit is then set to the price of the studied market
        objFunction.Add(
            priceForecast[time] * (PO_DSj.PowerLevelBuy[time] + PO_DSj.PowerLevelSell[time]) * p.time_step / 60.0
        )

        # For additional period
        if time not in p.target_times:
            if PO_DSj.StorageType == "Battery":
                nbr_fragment = p.battery_nb_fragments
                smoothing_factor = p.battery_smoothing_factor

            elif PO_DSj.StorageType == "ElectricVehicle":
                nbr_fragment = p.ev_nb_fragments
                smoothing_factor = p.ev_smoothing_factor

            elif PO_DSj.StorageType == "PumpedHydraulicStorage":
                nbr_fragment = p.phs_nb_fragments
                smoothing_factor = p.phs_smoothing_factor

            else:
                try:
                    msg = f"The storage type: {PO_DSj.StorageType} don't exist"
                    API.IO.Trace.Log(msg, API.IO.LogTypeError)
                    sys.exit()
                except:
                    pass

            for n in range(0, nbr_fragment):
                # The objective function is the total profit over the optimisation period
                if nbr_fragment == 1 and n == 0:
                    objFunction.Add(
                        -PO_DSj.PowerLevelSell_n[n][time] * priceForecast[time]
                        - PO_DSj.PowerLevelBuy_n[n][time] * priceForecast[time]
                    )
                else:
                    objFunction.Add(
                        -PO_DSj.PowerLevelSell_n[n][time]
                        * priceForecast[time]
                        * (1 - n * smoothing_factor / (nbr_fragment - 1))
                        - PO_DSj.PowerLevelBuy_n[n][time]
                        * priceForecast[time]
                        * (1 + n * smoothing_factor / (nbr_fragment - 1))
                    )

                # Add constrain related to power fragment
                constraintList.Add(PO_DSj.PowerLevelBuy_n[n][time] >= minPowerti / nbr_fragment)
                constraintList.Add(PO_DSj.PowerLevelSell_n[n][time] <= maxPowerti / nbr_fragment)

            if nbr_fragment > 0:
                constraintList.Add(
                    PO_DSj.PowerLevelSell[time] == sum(PO_DSj.PowerLevelSell_n[n][time] for n in range(0, nbr_fragment))
                )
                constraintList.Add(
                    PO_DSj.PowerLevelBuy[time] == sum(PO_DSj.PowerLevelBuy_n[n][time] for n in range(0, nbr_fragment))
                )

        # get global constraints
        sum_power_level.Add(PO_DSj.PowerLevelBuy[time])
        sum_power_level.Add(PO_DSj.PowerLevelSell[time])

        # C. CONSTRAINTS ON THE CONTROL VARIABLE

        # Reserves requirements
        # We are in a case where there is no FLAT state, so manual reserves can be provided
        # as long as the unit is online.

        # relaxedReserve disabling condition (eq. (43))

        # impossible commitment and stable reserves constraints (eq. (44))
        constraintList.Add(PO_DSj.automatedReservesUp[time] <= PO_DSj.maximumAutomated)
        constraintList.Add(PO_DSj.automatedReservesDown[time] <= PO_DSj.maximumAutomated)
        constraintList.Add(PO_DSj.reservesUp[time] <= maxPowerti)
        constraintList.Add(PO_DSj.reservesDown[time] <= maxPowerti)

        # -- The power delivered by the equipment is between its maximum power and its minimum power
        # FC je modifie la suite, il me semble qu'il y a des confusions entre puissance et energie dans certains contraintes

        if PO_DSj.StorageType == "Battery" or PO_DSj.StorageType == "PumpedHydraulicStorage":
            ReserveStoredEnergyDown_ti = PO_DSj.reservesDown[time] * (
                p.battery_reserve_duration / 60.0
            ) + PO_DSj.automatedReservesDown[time] * (p.automated_battery_reserve_duration / 60.0)
            ReserveStoredEnergyUp_ti = PO_DSj.reservesUp[time] * (
                p.battery_reserve_duration / 60.0
            ) + PO_DSj.automatedReservesUp[time] * (p.automated_battery_reserve_duration / 60.0)

            constraintList.Add(
                PO_DSj.PowerLevelSell[time]
                + PO_DSj.reservesUp[time]
                + PO_DSj.automatedReservesUp[time]
                + PO_DSj.unprovidedReservesUp[time]
                <= maxPowerti * PO_DSj.DischargeEfficiency
            )
            constraintList.Add(
                PO_DSj.PowerLevelBuy[time]
                - PO_DSj.reservesDown[time]
                - PO_DSj.automatedReservesDown[time]
                - PO_DSj.unprovidedReservesDown[time]
                >= minPowerti * 1 / PO_DSj.ChargeEfficiency
            )

            constraintList.Add(
                PO_DSj.PowerLevelSell[time] <= maxPowerti * PO_DSj.DischargeEfficiency * PO_DSj.Is_Sell[time]
            )
            constraintList.Add(
                PO_DSj.PowerLevelBuy[time] >= minPowerti * 1 / PO_DSj.ChargeEfficiency * (1 - PO_DSj.Is_Sell[time])
            )

        if PO_DSj.StorageType == "ElectricVehicle":
            ReserveStoredEnergyDown_ti = PO_DSj.reservesDown[time] * (
                p.battery_reserve_duration / 60.0
            ) + PO_DSj.automatedReservesDown[time] * (p.automated_battery_reserve_duration / 60.0)
            ReserveStoredEnergyUp_ti = PO_DSj.reservesUp[time] * (
                p.battery_reserve_duration / 60.0
            ) + PO_DSj.automatedReservesUp[time] * (p.automated_battery_reserve_duration / 60.0)

            constraintList.Add(
                (
                    PO_DSj.PowerLevelSell[time]
                    + PO_DSj.reservesUp[time]
                    + PO_DSj.automatedReservesUp[time]
                    + PO_DSj.unprovidedReservesUp[time]
                )
                <= (PO_DSj.isV2G * maxPowerti * PO_DSj.DischargeEfficiency)
            )
            constraintList.Add(
                (
                    PO_DSj.PowerLevelBuy[time]
                    - PO_DSj.reservesDown[time]
                    - PO_DSj.automatedReservesDown[time]
                    - PO_DSj.unprovidedReservesDown[time]
                )
                >= minPowerti * 1 / PO_DSj.ChargeEfficiency
            )

        # FC : Ici on utilise les deltas entre t et t+1 pour DisplacementEnergy et MaximumEnergy parce qu'il y a un décalage dans les indexations,
        # Ca serait beaucoup plus clair si il n'y avait pas d'index mais simplement des TS.
        if time == p.start_date:
            constraintList.Add(
                PO_DSj.StoredEnergy[time]
                == PO_DSj.InitialStock * (PO_DSj.MaximumEnergy[time] / PO_DSj.MaximumEnergy[prev_time])
                - PO_DSj.PowerLevelBuy[time] * PO_DSj.ChargeEfficiency * p.time_step / 60.0
                - PO_DSj.PowerLevelSell[time] * p.time_step / (60.0 * PO_DSj.DischargeEfficiency)
                + (PO_DSj.DisplacementEnergy[time] - PO_DSj.DisplacementEnergy[prev_time])
            )

            if p.verbose:
                msg = f"The energy stock at t1: {PO_DSj.InitialStock + (PO_DSj.MaximumEnergy[time] - PO_DSj.MaximumEnergy[prev_time])} MWh"
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

        elif time in local_op_times:
            constraintList.Add(
                PO_DSj.StoredEnergy[time]
                == PO_DSj.StoredEnergy[prev_time] * (PO_DSj.MaximumEnergy[time] / PO_DSj.MaximumEnergy[prev_time])
                - PO_DSj.PowerLevelBuy[time] * PO_DSj.ChargeEfficiency * p.time_step / 60.0
                - PO_DSj.PowerLevelSell[time] * p.time_step / (60.0 * PO_DSj.DischargeEfficiency)
                + (PO_DSj.DisplacementEnergy[time] - PO_DSj.DisplacementEnergy[prev_time])
            )

        # For any time steps:
        # Respect of minimum and maximum stock constraints
        constraintList.Add(
            PO_DSj.StoredEnergy[time]
            >= PO_DSj.MaximumEnergy[time] * PO_DSj.MinimumStateOfCharge[time] + ReserveStoredEnergyUp_ti
        )
        constraintList.Add(PO_DSj.StoredEnergy[time] <= PO_DSj.MaximumEnergy[time] - ReserveStoredEnergyDown_ti)

        # Global cycle balance (the reservoir level of the equipment remains
        # identical between the first and last dates of the optimization period)
        if time == p.start_date:
            constraintList.Add(
                sum(-PO_DSj.PowerLevelBuy[time] for time in local_op_times) * PO_DSj.ChargeEfficiency
                == sum(PO_DSj.PowerLevelSell[time] for time in local_op_times) / PO_DSj.DischargeEfficiency
            )
