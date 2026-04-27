# Running the Module

## Basic Usage

See [Running Modules](../../running-modules.md) for the standard ATLAS module execution pattern and parameter formats.

For common parameters (dates, timestep, etc.), see [Common Parameters](../../common-parameters.md). For module-specific parameters, see [Parameters](input-data.md).

## Example Configuration

```python
from atlas import AtlasDataset, IntradayPriceForecastModule

params = {
    "temporal": {
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2024-01-02T00:00:00",
        "execution_date": "2024-01-01T12:00:00",
        "timestep": "PT1H",
    },
    "output": {
        "export_result": True,
    },
    # Module-specific parameters
    "intraday_negative_price_cap": -500,
    "intraday_positive_price_cap": 4000,
    "execution_date_day_ahead": "2024-01-01T06:00:00",
    "execution_date_scenarios": "2024-01-01T00:00:00",
}

module = IntradayPriceForecastModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, params)
```
