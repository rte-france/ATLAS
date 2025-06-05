def GetVariablesAndConstraints_wind_pv(
    time,
    equipments_wind_pv,
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
    This function formulates the wind and photovoltaic equipments orders.

    Arguments:
    - 'equipments_wind_pv': a list of wind or photovoltaic equipments
    - `InputMarker`: an input marker
    - `outputMarker`: an output marker
    - `orders_time`: a list of dates at which orders must be formulated.
    """

    for equipment_name, equipment_wind_pvj in equipments_wind_pv.items():
        if time in p.target_times:
            # That part chek if those opti variable are usefull

            reserveUpti.Add(equipment_wind_pvj.reservesUp[time])
            reserveDownti.Add(equipment_wind_pvj.reservesDown[time])
            # automatedContractedDifference
            automatedReserveUpti.Add(equipment_wind_pvj.automatedReservesUp[time])
            automatedReserveDownti.Add(equipment_wind_pvj.automatedReservesDown[time])

            maxPowerti = equipment_wind_pvj.MaximumPower[time]
            minPowerti = equipment_wind_pvj.MinimumPower[time]

            # Objective function
            objFunction.Add(equipment_wind_pvj.Price[time] * equipment_wind_pvj.PowerLevel[time] * p.time_step / 60.0)

            # Maximum and Minimum Power
            constraintList.Add(equipment_wind_pvj.PowerLevel[time] <= maxPowerti)
            constraintList.Add(equipment_wind_pvj.PowerLevel[time] >= minPowerti)

            # relaxedReserve disabling condition (eq. (43))
            # constraintList.Add(equipment_wind_pvj.relaxedReserves[time] <= minPowerti)

            # impossible commitment and stable reserves constraints (eq. (44))
            constraintList.Add(equipment_wind_pvj.automatedReservesUp[time] <= equipment_wind_pvj.maximumAutomated)
            constraintList.Add(equipment_wind_pvj.automatedReservesDown[time] <= equipment_wind_pvj.maximumAutomated)
            constraintList.Add(equipment_wind_pvj.reservesUp[time] <= maxPowerti)
            constraintList.Add(equipment_wind_pvj.reservesDown[time] <= maxPowerti)

            sum_power_level.Add(equipment_wind_pvj.PowerLevel[time])
