"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger
from pandas import Series
from pendulum import duration

from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.math.forecasting_matrix import ForecastingMatrix
from atlas.core.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_portfolio
from atlas.objects.equipment.other_non_dispatchable import OtherNonDispatchable


def _make_unit(
    name: str,
    values: list[float] | Series,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    area_name: str,
) -> OtherNonDispatchable:
    ts = Timeseries.from_values(
        start_date=parameters.execution_date,
        frequency="1h",
        values=values,
    )
    return OtherNonDispatchable(
        name=name,
        portfolio=get_portfolio(atlas_dataset, parameters, area_name),
        node=atlas_dataset.get("node", area_name),
        maximum_power_forecast=ForecastingMatrix().add(ts, parameters.execution_date, inplace=False),
        co2_emission_factor=0.0,
        has_daily_energy_constraint=False,
        maximum_afrr=0.0,
        maximum_fcr=0.0,
        maximum_gradient=0.0,
        setup_delay=0.0,
        unit_count=0,
        additional_hours=duration(),
    )


def convert_other_non_dispatchable_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert other non-dispatchable generation units from Antares to Atlas.

    Creates one :class:`OtherNonDispatchable` per area for each non-zero column
    in the Antares misc-gen matrix (bio_mass, waste, other by default) and one
    for run-of-river hydro when the RoR series is non-zero.
    """
    logger.info("Converting non-dispatchable generation units")

    areas = study.get_areas()
    study_output = study.get_output(parameters.output_name)
    col_names = parameters.output.misc_gen_column_names
    non_disp_units = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        misc_gen = area.get_misc_gen_matrix()
        for col_idx in range(misc_gen.shape[1]):
            values = misc_gen.iloc[:, col_idx]
            if not values.abs().max() > 0:
                continue
            suffix = col_names.get(col_idx, str(col_idx))
            non_disp_units.append(
                _make_unit(
                    name=f"{area_name}_{suffix}",
                    values=values,
                    parameters=parameters,
                    atlas_dataset=atlas_dataset,
                    area_name=area_name,
                )
            )

        ror = area.hydro.get_ror_series()
        scenario = study_output.get_hydro_ts_numbers(area_name).get(parameters.scenario, None)
        if scenario is not None:
            ror_series = ror[scenario - 1]
            if ror_series.abs().max().item() > 0:
                non_disp_units.append(
                    _make_unit(
                        name=f"{area_name}_ror",
                        values=ror_series.tolist(),
                        parameters=parameters,
                        atlas_dataset=atlas_dataset,
                        area_name=area_name,
                    )
                )

    atlas_dataset.other_non_dispatchable.add(non_disp_units)
    return atlas_dataset
