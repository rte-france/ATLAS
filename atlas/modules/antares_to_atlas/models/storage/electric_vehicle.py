"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import LoadType, StorageType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_weight_for_cluster
from atlas.objects.equipment.load import Load
from atlas.objects.equipment.storage import Storage


def convert_electric_vehicle_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert Electric Vehicle technologies from Antares to Atlas Storage equipment.

    EV units are modeled as Storage equipment with V2G capabilities:
    - Standard EVs for most areas
    - Special handling for France with two EV types (night-only and regular)
    - France also includes heavy vehicles as Load equipment

    Requires displacement energy and node-specific parameters from CSV files.
    """
    logger.info("Converting Electric Vehicle units")

    # TODO: Load displacement energy baseline from CSV
    # In old code: reads from p.baseline_displacement_energy CSV file
    # and creates a timeseries with it
    baseline_displacement_energy_ts = _load_baseline_displacement_energy(parameters)

    # TODO: Load node-specific parameters from CSV
    # In old code: reads from p.disp_energy_node_parameters CSV file
    # Contains shift and scale factors per node
    specific_node_parameters = _load_specific_node_parameters(parameters)

    # Convert standard EVs
    ev_units = _convert_standard_evs(
        study=study,
        parameters=parameters,
        atlas_dataset=atlas_dataset,
        baseline_displacement_energy_ts=baseline_displacement_energy_ts,
        specific_node_parameters=specific_node_parameters,
    )

    # Convert France EVs (special case)
    if "fr" in parameters.market_areas:
        ev_units += _convert_france_evs(
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            baseline_displacement_energy_ts=baseline_displacement_energy_ts,
            specific_node_parameters=specific_node_parameters,
        )

        # Convert France heavy vehicles
        hv_units = _convert_france_heavy_vehicles(
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
        )
        atlas_dataset.load.add(hv_units)

    atlas_dataset.storage.add(ev_units)

    return atlas_dataset


def _load_baseline_displacement_energy(parameters: AntaresToAtlasParameters) -> Timeseries | None:
    """Load baseline displacement energy from CSV file.

    TODO: Implement CSV reading logic
    In old code: reads from p.baseline_displacement_energy file
    """
    # TODO: Check if file exists and read it
    # if os.path.isfile(parameters.baseline_displacement_energy):
    #     Read CSV and create timeseries
    # For now, return None with a TODO
    logger.debug("TODO: Load baseline displacement energy from CSV")
    return None


def _load_specific_node_parameters(parameters: AntaresToAtlasParameters) -> dict:
    """Load node-specific EV parameters from CSV file.

    Returns dict with node names as keys and [shift, scale] as values.

    TODO: Implement CSV reading logic
    In old code: reads from p.disp_energy_node_parameters file
    """
    # TODO: Check if file exists and read it
    # if os.path.isfile(parameters.disp_energy_node_parameters):
    #     Read CSV and create dictionary
    logger.debug("TODO: Load node-specific parameters from CSV")
    return {}


def _convert_standard_evs(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    baseline_displacement_energy_ts: Timeseries | None,
    specific_node_parameters: dict,
) -> list[Storage]:
    """Convert standard EV units for all areas (except France)."""
    logger.info("Converting standard EV units")

    areas = study.get_areas()
    links = study.get_links()
    binding_constraints = study.get_binding_constraints()
    ev_units: list[Storage] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        # France is handled separately
        if area_name.lower() == "fr":
            continue

        area = areas[area_name]
        thermals = area.get_thermals()
        logger.debug(f"Processing EV for area {area.id}")

        ev_inj_thermal = thermals.get(f"{area_name}_ve_inj", None)

        if not ev_inj_thermal:
            logger.debug(f"No EV injection thermal found for area {area.id}")
            continue

        ev_link = links.get(f"{area_name}_ve_eu", None)

        if not ev_link:
            logger.debug(f"No EV link found for area {area.id}")
            continue

        ev_stock_bc = binding_constraints.get(f"ve_stock_{area_name}", None)

        if not ev_stock_bc:
            logger.debug(f"No binding constraint found for EV in area {area.id}")
            continue

        ev_stor_thermal = thermals.get(f"ve_vhr_storage_ve_vhr_storage_ve_{area_name}_1", None)

        if not ev_stor_thermal:
            continue

        # TODO: Get time series data
        # - Maximum power from ev_inj.Disponibility[scenario]
        # - Minimum power from ev_link.DirectTransferCapacity["1"]
        # - Maximum energy from ev_stor.Disponibility[scenario]
        # - Efficiencies from binding constraint weights
        try:
            maximum_power_ts = Timeseries.from_index(
                start_date=parameters.start_date,
                frequency="1h",
                end_date=parameters.start_date + duration(years=1),
                default_value=0.0,
            )
            minimum_power_ts = Timeseries.from_index(
                start_date=parameters.start_date,
                frequency="1h",
                end_date=parameters.start_date + duration(years=1),
                default_value=0.0,
            )
            maximum_energy_ts = Timeseries.from_index(
                start_date=parameters.start_date,
                frequency="1h",
                end_date=parameters.start_date + duration(years=1),
                default_value=0.0,
            )

            if maximum_power_ts.max() == 0.0 or maximum_energy_ts.max() == 0.0:
                continue

        except Exception as e:
            logger.warning(f"Could not get time series for EV in area {area.id}: {e}")
            continue

        charge_weight = get_weight_for_cluster(study, area_name, "ve_vhr_inj")  # TODO verify cluster name
        discharge_weight = get_weight_for_cluster(study, area_name, "ve_vhr_turb")  # TODO verify cluster name
        charge_efficiency = charge_weight if charge_weight is not None else 1.0
        discharge_efficiency = 1.0 / discharge_weight if discharge_weight is not None and discharge_weight != 0 else 1.0

        # TODO: Calculate displacement energy
        # Uses baseline_displacement_energy_ts * scale factor, then shifted by time offset
        # Both from specific_node_parameters[area.id]
        displacement_energy_ts = None
        if baseline_displacement_energy_ts and area.id in specific_node_parameters:
            # TODO: Apply scale and shift from specific_node_parameters
            pass

        # Create EV equipment
        ev = Storage(
            name=f"{area.id}_ev",
            node=atlas_dataset.get("node", area.id),
            portfolio=atlas_dataset.get(
                "portfolio",
                f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
            ),
            storage_type=StorageType.ELECTRIC_VEHICLE,
            is_v2g=True,
            maximum_power=maximum_power_ts,
            minimum_power=minimum_power_ts,
            maximum_energy=maximum_energy_ts,
            minimum_state_of_charge=Timeseries.from_index(
                start_date=parameters.start_date,
                frequency="1h",
                end_date=parameters.start_date + duration(years=1),
                default_value=0.3,
            ),
            charge_efficiency=charge_efficiency,
            discharge_efficiency=discharge_efficiency,
            storage_initial_level=parameters.storage.ev_initial_level,
            displacement_energy=displacement_energy_ts,
        )

        ev_units.append(ev)
        logger.debug(f"Created EV for area: {area.id}")

    logger.info("Standard EV conversion done")
    return ev_units


def _convert_france_evs(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    baseline_displacement_energy_ts: Timeseries | None,
    specific_node_parameters: dict,
) -> list[Storage]:
    """Convert France EV units (night-only and regular).

    France has special EV modeling with:
    - Night-only EVs: connected only during night hours
    - Regular EVs: connected during day and night
    The split is calculated from binding constraints.
    """
    logger.info("Converting FR EV units")

    areas = study.get_areas()
    links = study.get_links()
    ev_units: list[Storage] = []

    if "fr" not in areas:
        return ev_units

    area = areas["fr"]

    # TODO: This is complex and requires:
    # 1. Getting thermal clusters for FR_VE_inj and VE_VHR_storage_VE_FR_1
    # 2. Getting links to ve_fr_load_total
    # 3. Getting multiple binding constraints:
    #    - ve_fr_load_min
    #    - ve_fr_night_load_min
    #    - ve_stock_fr
    # 4. Calculating night-only ratio from binding constraints
    # 5. Creating two EV instances with split capacities

    # For now, leaving detailed TODOs
    logger.debug("TODO: Implement France EV conversion with night-only and regular EVs")
    logger.debug("TODO: Calculate night-only ratio from ve_fr_load_min and ve_fr_night_load_min binding constraints")
    logger.debug("TODO: Create fr_ev_night with capacities multiplied by night ratio")
    logger.debug("TODO: Create fr_ev_regular with remaining capacities")

    logger.info("FR EV conversion done (TODO)")
    return ev_units


def _convert_france_heavy_vehicles(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> list[Load]:
    """Convert France heavy vehicles (mobilite lourde) as Load equipment."""
    logger.info("Converting FR heavy vehicles")

    areas = study.get_areas()
    links = study.get_links()

    if "fr" not in areas:
        return []

    hv_link = links.get("fr_ve_fr_mobilite_lourde", None)

    if not hv_link:
        logger.debug("No heavy vehicle link found for FR")
        return []

    try:
        transit_df = hv_link.get_capacity_direct()[
            parameters.scenario
        ]  # TODO HV_link.CalculatedTransit.GetTimeSeriesByName(str(p.scenario))
        maximum_power_ts = Timeseries(transit_df * -1.0)
    except Exception as e:
        logger.warning(f"Could not get transit data for FR heavy vehicles: {e}")
        return []

    hv = Load(
        name="fr_heavy_vehicles",
        node=atlas_dataset.get("node", "fr"),
        portfolio=atlas_dataset.get(
            "portfolio",
            "supplier_fr" if parameters.consumption_production_separation else "portfolio_fr",
        ),
        load_type=LoadType.OTHER_NON_DISPATCHABLE_LOAD,
        maximum_power_forecast=ForecastingMatrix().add(parameters.execution_date, maximum_power_ts),
    )

    logger.info("FR heavy vehicles conversion done")
    return [hv]
