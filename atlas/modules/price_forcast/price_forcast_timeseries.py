from datetime import datetime

from atlas import Timeseries


class PriceForcastTimeseries(Timeseries):
    """wrapper class for Timeseries in order to add utilities functions"""

    def get_value_zero_if_empty(self, time: datetime | str, value: float) -> float:
        '''
            Try to get timeseries value, if time series is empty, return 0
        '''
        value = 0
        if self is not None:
            if self.Length > 0:
                value = self.get_value(time)
        return value