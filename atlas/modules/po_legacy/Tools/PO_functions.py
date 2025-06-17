# coding: utf-8

import sys
import API
import os


def get_parameter_date(date_parameter_name):
    """
    try to Get date parameter
    """
    date_parameter = API.IO.GetParameterByIdentifier(date_parameter_name).Value
    try:
        result_date = API.DatetimeIndex.ParseDate(date_parameter)
    except SystemError:
        msg = "The parameter {parameter_name} has an invalid format : {parameter_values}".format(
            parameter_name=date_parameter_name, parameter_values=date_parameter
        )
        API.IO.Trace.Log(msg, API.IO.LogTypeError)
        sys.exit()
    return result_date


def get_deltaT_to_string(deltaT_in_hour):
    """
    Get string from deltaT by example, if deltaT = 0.5h, strDeltaT = 30m
    """
    # deltaT is in hour
    iTime = int(deltaT_in_hour * 60)
    sTime = "{0}m".format(iTime)

    return sTime


def get_time_series_value(timeSeries, date):
    """
    Try to get timeseries value, if time series is empty, return 0
    """
    value = 0
    if timeSeries is not None:
        if timeSeries.Length > 0:
            value = timeSeries.GetValue(date)
    return value


def estimate_imbalance_prices(
    time, portfolio, market_area, controlBlock, ImbalPriceUp, LargeImbalPriceUp, ImbalPriceDown, LargeImbalPriceDown, p
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


def get_date_to_clean_string(date):
    """
    Converts a datetime object to a string without special characters
    """
    string = str(date)
    string = string.replace("/", "_").replace(":", "_").replace(" ", "_")
    return string


# Helper used to manage the output path of debug data
def check_output_path(output_path):
    """
    Takes as input a path (in our case, in the SAMBA output folder of the user),
    and checks if this path exists.
    If not, a folder is created and the user is notified with a message in the console
    """

    if not os.path.exists(output_path):
        os.mkdir(output_path)
        API.IO.Trace.Log("Output folder for debug created at {}".format(output_path), API.IO.LogTypeInfo)

    return None
