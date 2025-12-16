from atlas import (
    Equipment,
    Hydro,
    LazyMatrix,
    LazyTimeseries,
    Load,
    Logger,
    OtherNonDispatchable,
    Solar,
    Storage,
    Thermal,
    Timeseries,
    Wind,
)
from atlas.math.matrix import Matrix

logger = Logger().get_logger()


def equipment_properties_rounding(equipment: Equipment):
    if isinstance(equipment, Thermal):
        _process_powers_between_0_and_1(equipment.maximum_power)
        _process_powers_between_0_and_1(equipment.minimum_power)
    elif isinstance(equipment, Hydro | Storage | Thermal):
        _safe_round_timeseries(equipment.maximum_power, 0)
        _safe_round_timeseries(equipment.minimum_power, 0)
    elif isinstance(equipment, Load | OtherNonDispatchable | Solar | Wind):
        _safe_round_matrix(equipment.maximum_power_forecast)

    _safe_round_timeseries(equipment.startup_cost, 2)
    _safe_round_timeseries(equipment.variable_cost, 2)

    if isinstance(equipment, Hydro | Storage):
        _safe_round_timeseries(equipment.maximum_energy, 0)

    if isinstance(equipment, Hydro):
        _safe_round_timeseries(equipment.minimum_energy, 0)
        _safe_round_timeseries(equipment.initial_level, 0)
        _safe_round_matrix(equipment.storage_marginal_value)


def _process_powers_between_0_and_1(power_timeseries: Timeseries | LazyTimeseries | None):
    if power_timeseries is not None and len(power_timeseries) > 0:
        if 0 < power_timeseries.min() < 1:
            logger.warning(
                "Equipment of type Thermal has a maximum power between 0 and 1. A specific rounding process is applied."
            )
            for time, value in power_timeseries.iter_rows():
                # QUESTION: should we update timeseries even if it is lazy?
                power_timeseries.set_value(time, 1 if 0 < value < 1 else round(value))


def _safe_round_timeseries(timeseries: Timeseries | LazyTimeseries | None, rounding_precision: int):
    if timeseries is not None:
        timeseries.round(rounding_precision)


def _safe_round_matrix(matrix: Matrix | LazyMatrix | None):
    if matrix is not None:
        for execution_date in matrix.indexes:
            # QUESTION: converted matrix.select(execution_date) to Timeseries because of mypy, is it okay to rely on a Timeseries rather than a LazyTimeseries in the matrix?
            matrix.replace(execution_date, _get_as_timeseries(matrix.select(execution_date)).round(inplace=False))


def _get_as_timeseries(timeseries: Timeseries | LazyTimeseries) -> Timeseries:
    return timeseries if isinstance(timeseries, Timeseries) else timeseries.collect()
