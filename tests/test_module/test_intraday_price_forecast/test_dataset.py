"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.intraday_price_forecast.input_dataset import IntradayPriceForecastInputDataset
from atlas.modules.intraday_price_forecast.module import IntradayPriceForecastModule
from atlas.modules.intraday_price_forecast.output_dataset import IntradayPriceForecastOutputDataset
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters
from atlas.timing import generate_datetimes

IDPF_INPUT_DIR = Path("data/atlas-dataset/id-price-forecast-input")
IDPF_OUTPUT_REFERENCE_DIR = Path("data/atlas-dataset/id-portfolio-optimisation-1-input")

PARAMS_DICT = {
    "temporal": {
        "start_date": "2028-09-26 00:00:00",
        "execution_date": "2028-09-26 22:00:00",
        "end_date": "2028-09-28 00:00:00",
        "timestep": "PT1H",
    },
    "execution_date_day_ahead": "2028-09-26 12:00:00",
    "execution_date_scenarios": "2028-07-01 00:00:00",
    "intraday_negative_price_cap": -500,
    "intraday_positive_price_cap": 4000,
}


@pytest.fixture(scope="module")
def idpf_parameters() -> IntradayPriceForecastParameters:
    return IntradayPriceForecastParameters.model_validate(PARAMS_DICT)


@pytest.fixture(scope="module")
def idpf_output_dataset(idpf_parameters) -> IntradayPriceForecastOutputDataset:
    if not IDPF_INPUT_DIR.exists():
        pytest.skip(f"IDPF input dataset not found: {IDPF_INPUT_DIR}")
    input_data = AtlasDataset.from_directory(IDPF_INPUT_DIR)
    input_dataset = IntradayPriceForecastInputDataset(input_data, idpf_parameters)
    return IntradayPriceForecastModule().execute(idpf_parameters, input_dataset)


@pytest.fixture(scope="module")
def idpf_reference_dataset() -> AtlasDataset:
    if not IDPF_OUTPUT_REFERENCE_DIR.exists():
        pytest.skip(f"IDPF reference dataset not found: {IDPF_OUTPUT_REFERENCE_DIR}")
    return AtlasDataset.from_directory(IDPF_OUTPUT_REFERENCE_DIR)


def test_id_price_forecast_matches_reference(idpf_parameters, idpf_output_dataset, idpf_reference_dataset):
    """Check that id_price_forecast by market_area matches the output dataset."""
    time_window = generate_datetimes(
        idpf_parameters.temporal.start_date,
        idpf_parameters.penultimate_date,
        idpf_parameters.temporal.timestep,
    )

    for market_area in idpf_output_dataset.market_area:
        assert market_area.id_price_forecast is not None, (
            f"id_price_forecast missing for market area '{market_area.name}'"
        )
        assert idpf_parameters.temporal.execution_date in market_area.id_price_forecast, (
            f"execution_date not found in id_price_forecast for market area '{market_area.name}'"
        )

        ts_computed = market_area.id_price_forecast[idpf_parameters.temporal.execution_date]
        ref_market_area = idpf_reference_dataset.market_area.get(market_area.name)
        ts_expected = ref_market_area.id_price_forecast[idpf_parameters.temporal.execution_date]

        for t in time_window:
            computed_value = ts_computed.get_value(t)
            expected_value = ts_expected.get_value(t)
            assert computed_value == pytest.approx(expected_value, abs=1e-3), (
                f"id_price_forecast mismatch for market area '{market_area.name}' at {t}: "
                f"computed={computed_value}, expected={expected_value}"
            )
