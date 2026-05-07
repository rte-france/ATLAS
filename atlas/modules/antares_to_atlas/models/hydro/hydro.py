"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft import Frequency, MCIndAreasDataType
from antares.craft.model.area import Area
from antares.craft.model.output import Output
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import InflowFrequency
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.models.hydro.inflows import add_inflows_from_csv
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.hydro import Hydro


def convert_hydro_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert Hydraulic reservoir units from Antares to Atlas."""
    logger.info("Converting Hydraulic units")

    hydro_reservoirs = parameters.hydro.reservoirs
    areas = study.get_areas()
    hydro_units: list[Hydro] = []
    study_output = study.get_output(parameters.output_name)

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        mapping_mc_ts = study_output.get_hydro_ts_numbers(area.name)
        if parameters.scenario not in mapping_mc_ts:
            continue
        scenario = mapping_mc_ts[parameters.scenario]
        if area.hydro.get_maxpower()[scenario - 1].abs().max() == 0:
            logger.debug(f"Skipping hydraulic unit for area {area.id} (max power is 0)")
            continue
        if area_name in hydro_reservoirs and area.hydro.properties.reservoir_capacity == 0:
            logger.debug(f"Skipping hydraulic unit for area {area.id} (reservoir capacity is 0)")
            continue

        hydro = _create_hydraulic_equipment(
            area=area,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            scenario=scenario,
            study_output=study_output,
            mapping_mc_ts=mapping_mc_ts,
        )

        if hydro:
            hydro_units.append(hydro)

    logger.info(f"Converted {len(hydro_units)} hydro units")
    atlas_dataset.hydro.add(hydro_units)
    return atlas_dataset


def _create_hydraulic_equipment(
    area: Area,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    scenario: int,
    study_output: Output,
    mapping_mc_ts: dict[int, int],
) -> Hydro | None:
    """Create a Hydraulic equipment for an area."""

    maximum_power_ts = Timeseries.from_values(
        parameters.start_date, frequency="1d", values=area.hydro.get_maxpower()[scenario - 1]
    )

    fragment = parameters.hydro.get_fragment(area.id)

    hydro = Hydro(
        name=f"{area.id}_hydro",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        maximum_power=maximum_power_ts,
        minimum_power=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        maximum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=area.hydro.properties.reservoir_capacity,
        ),
        minimum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        energy_target_frequency=InflowFrequency.Daily,
        inflow_frequency=InflowFrequency.Daily,
        has_daily_energy_constraint=True,
        minimum_daily_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1d",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        maximum_daily_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1d",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        fragment_prices=fragment.prices,
        fragment_volumes=fragment.volumes,
    )

    if (parameters.hydro.use_heuristic or area.hydro.properties.reservoir) and parameters.hydro.use_water_value:
        if area.hydro.properties.reservoir:
            hydro.inflows = Timeseries.from_values(
                parameters.start_date, frequency="1d", values=area.hydro.get_mod_series()[scenario - 1].to_list()
            )
        else:
            add_inflows_from_csv(area, hydro, area.hydro.get_mod_series(), parameters, mapping_mc_ts)
    else:
        hydro.energy_target = Timeseries.from_values(
            parameters.start_date, frequency="1d", values=area.hydro.get_mod_series()[scenario - 1].to_list()
        )

    daily_energy = Timeseries.from_values(
        parameters.start_date,
        frequency="1h",
        values=study_output.get_mc_ind_area(
            mc_year=scenario, frequency=Frequency.HOURLY, data_type=MCIndAreasDataType.VALUES, area=area.name
        )[(parameters.output.ror_column, "MWh")],
    ).groupby("1d", agg="sum")

    hydro.minimum_daily_energy = daily_energy * parameters.hydro.min_energy_coeff
    hydro.maximum_daily_energy = daily_energy * parameters.hydro.max_energy_coeff

    return hydro
