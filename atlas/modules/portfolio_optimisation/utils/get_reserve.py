from ast import Load

from pendulum import DateTime

from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.wind import Wind
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


def _get_reserve(
    opt,
    reserve_up_ti,
    reserve_down_ti,
    automated_reserve_up_ti,
    automated_reserve_down_ti,
    max_power_ti,
    time: DateTime,
    parameters: PortfolioOptimisationParameters,
):
    maximum_afrr = opt.maximum_afrr
    maximum_fcr = opt.maximum_fcr

    if isinstance(opt, Wind | Solar | Load | OtherNonDispatchable):
        max_power_ti += abs(
            opt.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(
                time,
            )
        )

    else:
        max_power_ti += opt.maximum_power.abs().get_value(time)

    afrr_up = opt.afrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
    afrr_down = opt.afrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
    mfrr_up = opt.mfrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)

    mfrr_down = opt.mfrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
    rr_up = opt.rr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
    rr_down = opt.rr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
    fcr_up = opt.fcr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
    fcr_down = opt.fcr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)

    reserve_up_ti += rr_up + mfrr_up
    reserve_down_ti += rr_down + mfrr_down
    automated_reserve_up_ti += min(afrr_up, maximum_afrr) + min(fcr_up, maximum_fcr)
    automated_reserve_down_ti += min(afrr_down, maximum_afrr) + min(fcr_down, maximum_fcr)

    return (
        reserve_up_ti,
        reserve_down_ti,
        automated_reserve_up_ti,
        automated_reserve_down_ti,
        max_power_ti,
    )
