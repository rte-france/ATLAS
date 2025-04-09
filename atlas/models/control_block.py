from typing import Any


class ControlBlock:
    alternative_type: str # possibles values : FrBM, mFRR, aFRR, None
    volume_uncertainty: bool
    affr_down_required: Any # ForecastMatrix
    affr_up_required: Any # ForecastMatrix
    balancing_mechanism_needs: Any # ForecastMatrix
    mfrr_down_required: Any # ForecastMatrix
    mfrr_needs: Any # ForecastMatrix
    mfrr_up_required: Any # ForecastMatrix
    rr_down_required: Any # ForecastMatrix
    rr_needs: Any # ForecastMatrix
    rr_up_required: Any # ForecastMatrix
    spilled_energy: Any # ForecastMatrix
    unsupplied_energy: Any # ForecastMatrix
    afrr_activation_costs: Any # Timeseries
    fcr_activation_costs: Any # Timeseries
    mfrr_activated: Any # Timeseries
    mfrr_activation_costs: Any # Timeseries
    negative_imbalance_price: Any # Timeseries
    positive_imbalance_price: Any # Timeseries
    rr_activated: Any # Timeseries
    rr_activation_costs: Any # Timeseries
    specific_activated: Any # Timeseries
    specific_activation_costs: Any # Timeseries
    weighted_balance_price_down: Any # Timeseries
    weighted_balance_price_up: Any # Timeseries

    def test(self):
        return