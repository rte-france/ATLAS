"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft import Frequency, MCIndAreasDataType
from antares.craft.model.study import Study
from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.other_non_dispatchable import OtherNonDispatchable


def convert_other_non_dispatchable_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert other non-dispatchable generation units from Antares to Atlas."""
    logger.info("Converting non-dispatchable generation units")

    areas = study.get_areas()
    non_disp_units = []
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        ror = areas[area_name].hydro.get_ror_series()
        scenario = (
            study.get_output(parameters.output_name).get_hydro_ts_numbers(area_name).get(parameters.scenario, None)
        )
        if scenario is not None:
            ror = ror[parameters.scenario - 1]
            if ror.abs().max().item() > 0:
                ror_ts = Timeseries.from_values(
                    start_date=parameters.execution_date,
                    frequency="1h",
                    values=ror,
                )
                non_disp_units.append(
                    OtherNonDispatchable(
                        name=f"{area_name}_ror",
                        portfolio=atlas_dataset.get(
                            "portfolio",
                            f"generator_{area_name}"
                            if parameters.consumption_production_separation
                            else f"portfolio_{area_name}",
                        ),
                        node=atlas_dataset.get("node", area_name),
                        maximum_power_forecast=ForecastingMatrix().add(
                            ror_ts, parameters.execution_date, inplace=False
                        ),
                    )
                )

            prod = Timeseries.from_values(
                start_date=parameters.start_date,
                frequency="1h",
                values=study.get_output(parameters.output_name).get_mc_ind_area(
                    parameters.scenario, frequency=Frequency.HOURLY, data_type=MCIndAreasDataType.VALUES, area=area_name
                )[(parameters.output.misc_ndg_column, "MWh")],
            )

            if prod.abs().max() > 0:
                non_disp_units.append(
                    OtherNonDispatchable(
                        name=f"{area_name}_{scenario}",
                        portfolio=atlas_dataset.get(
                            "portfolio",
                            f"generator_{area_name}"
                            if parameters.consumption_production_separation
                            else f"portfolio_{area_name}",
                        ),
                        node=atlas_dataset.get("node", area_name),
                        maximum_power_forecast=ForecastingMatrix().add(prod, parameters.execution_date, inplace=False),
                    )
                )

    atlas_dataset.other_non_dispatchable.add(non_disp_units)

    return atlas_dataset
