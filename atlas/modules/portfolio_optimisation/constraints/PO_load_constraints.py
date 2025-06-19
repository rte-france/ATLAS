# coding: utf-8


def GetVariablesAndConstraints_load(
    time,
    equipments_load,
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
    This function adds constraints and elements in the objective function related to load equipments.

    Arguments:
    - 'equipments_load': a list of load equipments
    - `InputMarker`: an input marker
    - `outputMarker`: an output marker
    - `orders_time`: a list of dates at which orders must be formulated.
    """

    for equipment_name, equipment_loadj in equipments_load.items():
        if time in p.target_times:
            maxPowerti = equipment_loadj.MaximumPower[time]
            minPowerti = equipment_loadj.MinimumPower[time]

            if equipment_loadj.LoadType == "PowerToGas":
                # Objective function
                objFunction.Add(
                    (equipment_loadj.Price[time] - priceForecast[time])
                    * equipment_loadj.PowerLevel[time]
                    * p.time_step
                    / 60.0
                )
            else:
                # Objective function
                objFunction.Add(equipment_loadj.Price[time] * -equipment_loadj.PowerLevel[time] * p.time_step / 60.0)

            # Maximum and Minimum Power (opposite direction compared to generation units)
            constraintList.Add(equipment_loadj.PowerLevel[time] >= maxPowerti)
            constraintList.Add(equipment_loadj.PowerLevel[time] <= minPowerti)

            # No reserve allowed on Load equipments for now
            """
            # contractedDifference
            reserveUpti.Add(equipment_loadj.reservesUp[time])
            reserveDownti.Add(equipment_loadj.reservesDown[time])
            # automatedContractedDifference
            automatedReserveUpti.Add(equipment_loadj.automatedReservesUp[time])
            automatedReserveDownti.Add(equipment_loadj.automatedReservesDown[time])


            #relaxedReserve disabling condition (eq. (43))
            #constraintList.Add(equipment_loadj.relaxedReserves[time] <= minPowerti)

            # impossible commitment and stable reserves constraints (eq. (44))
            constraintList.Add(equipment_loadj.automatedReservesUp[time] <= equipment_loadj.maximumAutomated)
            constraintList.Add(equipment_loadj.automatedReservesDown[time] <= equipment_loadj.maximumAutomated)
            constraintList.Add(equipment_loadj.reservesUp[time] >= maxPowerti)
            constraintList.Add(equipment_loadj.reservesDown[time] >= maxPowerti)
            """

            sum_power_level.Add(equipment_loadj.PowerLevel[time])
