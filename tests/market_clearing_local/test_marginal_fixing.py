import json
import tempfile
from pathlib import Path

import pytest

from atlas.io_utils.input_loader import InputLoader
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.market_clearing.phases.marginal_fixing import MarginalFixing


@pytest.mark.skip(reason="No data available")
@pytest.mark.parametrize(
    "dataset_name",
    [
        "MarketClearing input v1.3 FB_1",
        "MarketClearing input v1.3 FB_2",
        "MarketClearing input v1.3 ATC_1",
        "MarketClearing input v1.3 ATC_2",
    ],
)
def test_if_marginal_fixing_generated_lp_matches_reference(dataset_name):
    dataset_path = Path("data") / "market_clearing_prometheus" / dataset_name
    dataset_data_path = dataset_path / "atlas-dataset"
    parameters_path = dataset_path / "parameters.yml"
    clearing_accepted_powers_path = dataset_path / "expected_results" / "clearing_accepted_powers.json"
    market_prices_path = dataset_path / "expected_results" / "pricing_market_prices.json"
    marginal_fixing_accepted_powers_path = dataset_path / "expected_results" / "marginal_fixing_accepted_powers.json"

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_data = InputLoader.from_directory(dataset_data_path)

        try:
            mc_module = MarketClearingModule()
            parameters = mc_module.import_parameters(parameters_path)
            parameters.output_path = tmpdir
            input_dataset = mc_module.import_data(raw_data, parameters)
            with open(clearing_accepted_powers_path, "r") as f:
                accepted_powers = {(ma, t): val for ma, t, val in json.load(f)}
            with open(market_prices_path, "r") as f:
                market_prices = {(ma, t): val for ma, t, val in json.load(f)}

            marginal_fixing = MarginalFixing(input_dataset, parameters)
            marginal_fixing.run(accepted_powers, market_prices)
        except Exception as e:
            pytest.fail(f"Clearing failed for {dataset_name}: {e}")

    with open(marginal_fixing_accepted_powers_path, "r") as f:
        marginal_fixing_accepted_powers = {(ma, t): val for ma, t, val in json.load(f)}

    for (market_area_name, order_name), expected_value in marginal_fixing_accepted_powers.items():
        assert (market_area_name, order_name) in marginal_fixing.accepted_powers
        value = marginal_fixing.accepted_powers[market_area_name, order_name]
        old_value = accepted_powers[market_area_name, order_name]
        if abs(expected_value - value) > 1e-8:
            print(f"Movement '{str(order_name)}': {old_value}, {expected_value}, {value}")
        assert expected_value == pytest.approx(value, 1e-8)
