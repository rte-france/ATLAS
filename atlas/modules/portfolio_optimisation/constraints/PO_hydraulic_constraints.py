# coding: utf-8

import API


def GetVariablesAndConstraints_Hydraulics(
    time,
    equipments_DH,
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
    """
    This function formulates the hydraulic reservoir offers.

    Arguments:
    - `InputMarker`: an input marker
    - `outputMarker`: an output marker
    - `orders_time`: a list of dates at which orders must be formulated.
    """

    for equipment_name, PO_DHj in equipments_DH.items():
        # That part chek if those opti variable are usefull
        # contractedDifference
        reserveUpti.Add(PO_DHj.reservesUp[time])
        reserveDownti.Add(PO_DHj.reservesDown[time])
        # automatedContractedDifference
        automatedReserveUpti.Add(PO_DHj.automatedReservesUp[time])
        automatedReserveDownti.Add(PO_DHj.automatedReservesDown[time])

        # --- Objective function
        for k in range(0, len(PO_DHj.PowerLevelFragment.keys())):
            if time in p.target_times:
                # create an offer for each element in volumes
                # Add objective function for the specif fragment
                objFunction.Add(PO_DHj.PriceFragment[k][time] * PO_DHj.PowerLevelFragment[k][time] * p.time_step / 60.0)
                sum_power_level.Add(PO_DHj.PowerLevelFragment[k][time])

            else:
                objFunction.Add(
                    -(priceForecast[time] - PO_DHj.PriceFragment[k][time])
                    * PO_DHj.PowerLevelFragment[k][time]
                    * p.time_step
                    / 60.0
                )

                # FC : La suite est pas necessaire ?
                sum_power_level.Add(PO_DHj.PowerLevelFragment[k][time])

        # --- Reserves constraints

        # relaxedReserve disabling condition (eq. (43))
        if time in p.hydraulic_op_times:
            constraintList.Add(PO_DHj.relaxedReserves[time] <= PO_DHj.MinimumPower[time])

            # impossible commitment and stable reserves constraints (eq. (44))
            constraintList.Add(PO_DHj.automatedReservesUp[time] <= PO_DHj.maximumAutomated)
            constraintList.Add(PO_DHj.automatedReservesDown[time] <= PO_DHj.maximumAutomated)
            constraintList.Add(PO_DHj.reservesUp[time] <= PO_DHj.MaximumPower[time])
            constraintList.Add(PO_DHj.reservesDown[time] <= PO_DHj.MaximumPower[time])

        # --- Reservoir constraints

        # Ca serait beaucoup plus clair si il n'y avait pas d'index mais simplement des TS.
        if time == p.start_date:
            constraintList.Add(
                PO_DHj.StoredEnergy[time]
                == PO_DHj.InitialLevel.GetValue(p.start_date.AddMinutes(-p.time_step))
                - PO_DHj.PowerLevelFragmentSum[time] * p.time_step / 60.0
            )

            if p.debug:
                msg = "The energy stock at StartDate: {} MWh".format(
                    PO_DHj.InitialLevel.GetValue(p.start_date.AddMinutes(-p.time_step))
                )
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

        elif time in p.target_times:
            constraintList.Add(
                PO_DHj.StoredEnergy[time]
                == PO_DHj.StoredEnergy[time.AddMinutes(-p.time_step)]
                - PO_DHj.PowerLevelFragmentSum[time] * p.time_step / 60.0
            )

        # For any time steps:
        # Respect of minimum and maximum stock constraints-
        if time in p.target_times:
            ReserveStoredEnergyUp_ti = PO_DHj.automatedReservesUp[time] + PO_DHj.reservesUp[time]
            ReserveStoredEnergyDown_ti = PO_DHj.automatedReservesDown[time] + PO_DHj.reservesDown[time]

            constraintList.Add(PO_DHj.StoredEnergy[time] >= PO_DHj.MinimumEnergy[time] + ReserveStoredEnergyUp_ti)
            constraintList.Add(PO_DHj.StoredEnergy[time] <= PO_DHj.MaximumEnergy[time] - ReserveStoredEnergyDown_ti)
