"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
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
        # try:
        #     sc_hydro = antares_node.HydroReservoir.HydroSelectedScenario[parameters.scenario - 1]
        # except SystemError:
        #     msg = f"Error with scenario {parameters.scenario} for unit {antares_node.Name}_hydro, potentially out of bounds"
        #     raise SystemError(msg)

        # if antares_node.HydroReservoir.ROR.Count > sc_hydro - 1:
        #     ror = antares_node.HydroReservoir.ROR.TimeSeries[sc_hydro - 1]
        ror = areas[area_name].hydro.get_ror_series()  # TODO antares_node.HydroReservoir.ROR.TimeSeries[sc_hydro - 1]
        if ror.abs().max().item() > 0:
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
                        parameters.execution_date, ror
                    ),  # TODO : ror is not a timeseries-like dataframe
                )
            )

            # for source in antares_node.MiscGenProduction.Index: # TODO
            #     prod = antares_node.MiscGenProduction[source]
            #     if prod.Abs().Max() > 0:

            non_disp_units.append(
                OtherNonDispatchable(
                    name=f"{area_name}_{source}",
                    portfolio=atlas_dataset.get(
                        "portfolio",
                        f"generator_{area_name}"
                        if parameters.consumption_production_separation
                        else f"portfolio_{area_name}",
                    ),
                    node=atlas_dataset.get("node", area_name),
                    maximum_power_forecast=ForecastingMatrix().add(parameters.execution_date, prod),
                )
            )  # TODO : prod is not a timeseries-like dataframe + i don't know where to get

    atlas_dataset.other_non_dispatchable.add(non_disp_units)

    return atlas_dataset
